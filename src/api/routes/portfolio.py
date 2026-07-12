"""Portfolio-related API endpoints for the AlphaCore system.

Exposes portfolio snapshots, performance metrics, cycle summaries,
and current open positions via a FastAPI ``APIRouter``.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc

from src.api.schemas import (
    ClosedTradeResponse,
    CycleRunResponse,
    HoldingResponse,
    PerformanceMetricsResponse,
    PortfolioSnapshotResponse,
    WalletResponse,
)
from src.data.binance_client import BinanceClient
from src.database.connection import get_db
from src.database.crud import (
    _compute_cash_from_trades,
    check_strategy_decay,
    get_performance_metrics,
    get_portfolio_history,
    get_sentiment_trade_performance,
)
from src.database.models import CycleRun, Position, Trade
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance, send_alert
from src.utils.logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get(
    "/history",
    response_model=list[PortfolioSnapshotResponse],
    summary="Retrieve portfolio snapshot history",
    description="Return the most recent portfolio snapshots ordered by creation time descending.",
)
def list_portfolio_history(limit: int = 50) -> list[PortfolioSnapshotResponse]:
    _logger.info("GET /portfolio/history (limit=%d)", limit)
    try:
        snapshots = get_portfolio_history(limit=limit)
        _logger.info("GET /portfolio/history -> %d snapshot(s)", len(snapshots))
        return [PortfolioSnapshotResponse(**s) for s in snapshots]
    except Exception:
        _logger.exception("GET /portfolio/history failed")
        raise HTTPException(status_code=500, detail="Failed to fetch portfolio history")


@router.get(
    "/metrics",
    response_model=PerformanceMetricsResponse,
    summary="Compute aggregate performance metrics",
    description="Return total trades, win rate, average PnL, best/worst trade, total realised PnL, and current drawdown.",
)
def portfolio_metrics() -> PerformanceMetricsResponse:
    _logger.info("GET /portfolio/metrics")
    try:
        metrics = get_performance_metrics()
        resp = PerformanceMetricsResponse(
            total_trades=metrics["total_trades"],
            win_rate=metrics["win_rate"],
            avg_pnl_per_trade=metrics["avg_pnl"],
            best_trade=metrics["best_trade"],
            worst_trade=metrics["worst_trade"],
            total_realised_pnl=metrics["total_realised_pnl"],
            current_drawdown=metrics["current_drawdown_pct"],
        )
        _logger.info("GET /portfolio/metrics -> %d trades", resp.total_trades)
        return resp
    except Exception:
        _logger.exception("GET /portfolio/metrics failed")
        raise HTTPException(status_code=500, detail="Failed to compute performance metrics")


@router.get(
    "/cycles",
    response_model=list[CycleRunResponse],
    summary="List recent agent cycles",
    description="Return the last N cycle runs ordered by start time descending.",
)
def list_cycles(limit: int = 20) -> list[CycleRunResponse]:
    _logger.info("GET /portfolio/cycles (limit=%d)", limit)
    try:
        result: list[CycleRunResponse] = []
        with get_db() as db:
            rows = (
                db.query(CycleRun)
                .order_by(desc(CycleRun.started_at))
                .limit(limit)
                .all()
            )
            for r in rows:
                result.append(CycleRunResponse.model_validate(r))
        _logger.info("GET /portfolio/cycles -> %d cycle(s)", len(result))
        return result
    except Exception:
        _logger.exception("GET /portfolio/cycles failed")
        raise HTTPException(status_code=500, detail="Failed to fetch cycle runs")


@router.get(
    "/positions",
    response_model=list[dict[str, Any]],
    summary="List current open positions",
    description="Return all rows from the Position table representing actively held positions.",
)
def list_positions() -> list[dict[str, Any]]:
    _logger.info("GET /portfolio/positions")
    try:
        result: list[dict[str, Any]] = []
        with get_db() as db:
            rows = db.query(Position).all()
            for r in rows:
                result.append({
                    "symbol": r.symbol,
                    "quantity": float(r.quantity) if r.quantity else 0.0,
                    "avg_entry_price": float(r.avg_entry_price) if r.avg_entry_price else 0.0,
                    "current_price": float(r.current_price) if r.current_price else 0.0,
                    "unrealised_pnl": float(r.unrealised_pnl) if r.unrealised_pnl else 0.0,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                })
        _logger.info("GET /portfolio/positions -> %d position(s)", len(result))
        return result
    except Exception:
        _logger.exception("GET /portfolio/positions failed")
        raise HTTPException(status_code=500, detail="Failed to fetch positions")


@router.get(
    "/wallet",
    response_model=WalletResponse,
    summary="Full portfolio wallet snapshot",
    description="Return cash balance, current open holdings with live prices, "
    "and every completed BUY→SELL pairing reconstructed from trade history. "
    "Trades flagged as pre-fix artifacts are listed individually but excluded "
    "from aggregate realised P&L.",
)
def wallet() -> WalletResponse:
    _logger.info("GET /portfolio/wallet")
    try:
        binance = BinanceClient()

        # --- Cash balance ---
        cash = _compute_cash_from_trades(Decimal(str(settings.PORTFOLIO_INITIAL_CAPITAL)))

        # --- Holdings from Position table with live prices ---
        holdings_list: list[dict[str, Any]] = []
        total_holdings_value = Decimal("0")
        total_unrealised_pnl = Decimal("0")

        with get_db() as db:
            positions = db.query(Position).all()
            for p in positions:
                if p.quantity <= 0:
                    continue
                try:
                    live_price = Decimal(str(binance.get_current_price(p.symbol)))
                except Exception:
                    live_price = Decimal(str(p.current_price)) if p.current_price else Decimal("0")
                qty = Decimal(str(p.quantity))
                avg_entry = Decimal(str(p.avg_entry_price)) if p.avg_entry_price else Decimal("0")
                current_value = qty * live_price
                unrealised = (live_price - avg_entry) * qty if avg_entry > 0 else Decimal("0")
                unrealised_pct = ((live_price - avg_entry) / avg_entry * 100) if avg_entry > 0 else Decimal("0")

                total_holdings_value += current_value
                total_unrealised_pnl += unrealised

                holdings_list.append(HoldingResponse(
                    symbol=p.symbol,
                    quantity=float(qty),
                    avg_entry_price=float(avg_entry),
                    current_price=float(live_price),
                    current_value=float(current_value),
                    unrealized_pnl=float(unrealised),
                    unrealized_pnl_pct=float(unrealised_pct),
                ))

            # --- Closed positions: FIFO BUY→SELL pairing from Trade history ---
            all_trades_raw = (
                db.query(Trade)
                .filter(Trade.status == "FILLED")
                .order_by(Trade.created_at)
                .all()
            )
            # Materialise trade data inside the session to avoid DetachedInstanceError
            trade_rows: list[dict[str, Any]] = [
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "executed_quantity": Decimal(str(t.executed_quantity or 0)),
                    "executed_price": Decimal(str(t.executed_price or 0)),
                    "pnl": Decimal(str(t.pnl)) if t.pnl is not None else None,
                    "created_at": t.created_at,
                    "is_pre_fix_artifact": t.is_pre_fix_artifact if hasattr(t, "is_pre_fix_artifact") else False,
                }
                for t in all_trades_raw
            ]

        closed_list: list[dict[str, Any]] = []
        buy_queue: dict[str, list[dict[str, Any]]] = {}

        for row in trade_rows:
            sym = row["symbol"]
            qty = row["executed_quantity"]
            price = row["executed_price"]
            side = row["side"]

            if side == "BUY":
                # Skip dust BUYs: quantity * price < $1 USD (consistent with
                # reconcile_positions() dust filter).  These tiny residuals
                # from rounding create nonsensical weighted buy prices when
                # matched against large SELLs.
                usd_value = qty * price
                if usd_value < Decimal("1"):
                    _logger.debug(
                        "Skipping dust BUY %s qty=%s price=%s (USD=%.4f)",
                        sym, qty, price, usd_value,
                    )
                    continue
                if sym not in buy_queue:
                    buy_queue[sym] = []
                buy_queue[sym].append({
                    "remaining": qty,
                    "price": price,
                    "opened_at": row["created_at"],
                    "is_artifact": row["is_pre_fix_artifact"],
                })

            elif side == "SELL":
                remaining_sell = qty
                buy_prices: list[tuple[Decimal, Decimal, datetime, bool]] = []
                buys_for_sym = buy_queue.get(sym, [])

                while remaining_sell > 0 and buys_for_sym:
                    buy = buys_for_sym[0]
                    used = min(remaining_sell, buy["remaining"])
                    buy_prices.append((
                        used,
                        buy["price"],
                        buy["opened_at"],
                        buy["is_artifact"],
                    ))
                    buy["remaining"] -= used
                    remaining_sell -= used
                    if buy["remaining"] <= Decimal("0"):
                        buys_for_sym.pop(0)

                if not buy_prices:
                    # Intentional skip — this SELL closed a position whose cost basis
                    # predates the tracking system (e.g. trade 10, the post-fix BTC
                    # SELL that was acquired before W08 was deployed).  The wallet is
                    # scoped to matched closed positions only; for a portfolio-wide
                    # total that includes every fill regardless of BUY history, use
                    # get_total_realised_pnl() in crud.py (which sums Trade.pnl
                    # across ALL FILLED SELLs, including unmatched ones).
                    _logger.warning("No matching BUY found for SELL %s qty=%s", sym, qty)
                    continue

                weighted_buy_price = (
                    sum(u * p for u, p, _, _ in buy_prices) / qty
                    if qty > 0 else Decimal("0")
                )

                # Sanity check: if weighted buy price is >50% different from
                # sell price, this match is nonsensical (likely from a partial
                # FIFO match where dust remained).  Log warning and skip.
                if weighted_buy_price > 0 and price > 0:
                    pct_diff = abs(weighted_buy_price - price) / price
                    if pct_diff > Decimal("0.5"):
                        _logger.warning(
                            "FIFO sanity check failed for %s: weighted_buy=%.2f "
                            "sell=%.2f (diff=%.1f%%) — skipping match",
                            sym, weighted_buy_price, price, pct_diff * 100,
                        )
                        continue

                earliest_open = min(oa for _, _, oa, _ in buy_prices)
                is_any_artifact = any(ia for _, _, _, ia in buy_prices)

                realized_pnl = row["pnl"] if row["pnl"] is not None else Decimal("0")
                realized_pnl_pct = ((price - weighted_buy_price) / weighted_buy_price * 100) if weighted_buy_price > 0 else Decimal("0")

                # Flag as artifact if either the matched buys or the sell itself is marked
                is_artifact = is_any_artifact or row["is_pre_fix_artifact"]

                closed_list.append({
                    "symbol": sym,
                    "buy_price": float(weighted_buy_price),
                    "sell_price": float(price),
                    "quantity": float(qty),
                    "realized_pnl": float(realized_pnl),
                    "realized_pnl_pct": float(realized_pnl_pct),
                    "opened_at": earliest_open,
                    "closed_at": row["created_at"],
                    "is_pre_fix_artifact": is_artifact,
                })

        # Aggregate realised PnL excluding pre-fix artifacts
        total_realised_excl_artifacts = sum(
            Decimal(str(c["realized_pnl"]))
            for c in closed_list
            if not c["is_pre_fix_artifact"]
        )

        closed_responses = [ClosedTradeResponse(**c) for c in closed_list]

        resp = WalletResponse(
            cash_balance=float(cash),
            total_holdings_value=float(total_holdings_value),
            total_unrealized_pnl=float(total_unrealised_pnl),
            total_realized_pnl=float(total_realised_excl_artifacts),
            holdings=holdings_list,
            closed_positions=closed_responses,
        )
        _logger.info(
            "GET /portfolio/wallet -> cash=%.2f, %d holding(s), %d closed trade(s)",
            resp.cash_balance, len(resp.holdings), len(resp.closed_positions),
        )
        return resp
    except Exception:
        _logger.exception("GET /portfolio/wallet failed")
        raise HTTPException(status_code=500, detail="Failed to fetch portfolio wallet")


@router.get(
    "/sentiment-validation",
    summary="Validate sentiment trading edge",
    description="Validates whether sentiment-driven trading has real edge. "
    "Requires minimum 30 trades for statistical reliability. "
    "Use this before risking real capital.",
)
def sentiment_validation(days: int = 30) -> dict[str, Any]:
    _logger.info("GET /portfolio/sentiment-validation (days=%d)", days)
    try:
        result = get_sentiment_trade_performance(days=days)
        result["strategy_decay"] = check_strategy_decay()
        _logger.info(
            "GET /portfolio/sentiment-validation -> %d trades, win_rate=%.2f%%",
            result["total_sentiment_trades"],
            result["win_rate_pct"],
        )
        return result
    except Exception:
        _logger.exception("GET /portfolio/sentiment-validation failed")
        raise HTTPException(
            status_code=500,
            detail="Failed to compute sentiment validation metrics",
        )


_PAUSE_FLAG = Path("data_cache/.trading_paused")


@router.post(
    "/pause-trading",
    summary="Pause all new trading",
    description="Writes a flag file to disk. The Manager Agent checks for this "
    "file and skips generating new entry trades when it exists. "
    "Auto-exit trades (SL/TP) are NOT blocked.",
)
def pause_trading() -> dict[str, Any]:
    _logger.info("POST /portfolio/pause-trading")
    try:
        _PAUSE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        _PAUSE_FLAG.touch()
        _logger.info("Trading paused — flag file created at %s", _PAUSE_FLAG)
        return {"status": "paused", "message": "Trading paused. New entry trades will be skipped."}
    except Exception as exc:
        _logger.exception("POST /portfolio/pause-trading failed")
        raise HTTPException(status_code=500, detail=f"Failed to pause trading: {exc}")


@router.post(
    "/resume-trading",
    summary="Resume normal trading",
    description="Deletes the pause flag file. The next cycle will generate new entry trades normally.",
)
def resume_trading() -> dict[str, Any]:
    _logger.info("POST /portfolio/resume-trading")
    try:
        if _PAUSE_FLAG.exists():
            _PAUSE_FLAG.unlink()
            _logger.info("Trading resumed — flag file deleted from %s", _PAUSE_FLAG)
            return {"status": "resumed", "message": "Trading resumed. New entry trades will be generated."}
        return {"status": "already_active", "message": "Trading was not paused."}
    except Exception as exc:
        _logger.exception("POST /portfolio/resume-trading failed")
        raise HTTPException(status_code=500, detail=f"Failed to resume trading: {exc}")


@router.get(
    "/trading-status",
    summary="Check whether trading is currently paused",
    description="Returns ``is_paused: bool`` based on the presence of the pause flag file on disk.",
)
def trading_status() -> dict[str, Any]:
    _logger.info("GET /portfolio/trading-status")
    is_paused = _PAUSE_FLAG.exists()
    return {"is_paused": is_paused, "status": "paused" if is_paused else "active"}


class ManualSellRequest(BaseModel):
    """Request body for manually selling a position."""

    symbol: str
    quantity: float | None = None


@router.post(
    "/sell",
    summary="Manually sell a position",
    description="Execute a market SELL on Binance Testnet for the given symbol. "
    "If quantity is omitted, the full position is sold. Logs the trade and "
    "updates the Position table. Does not interfere with the automated scheduler.",
)
def manual_sell(req: ManualSellRequest) -> dict[str, Any]:
    _logger.info("POST /portfolio/sell — symbol=%s, quantity=%s", req.symbol, req.quantity)
    try:
        from binance.exceptions import BinanceAPIException

        binance = BinanceClient()
        sym_clean = format_pair_for_binance(req.symbol)

        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == req.symbol).first()
            if not pos or pos.quantity <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"No open position for {req.symbol}",
                )

            sell_qty = Decimal(str(req.quantity)) if req.quantity else Decimal(str(pos.quantity))

            if sell_qty > Decimal(str(pos.quantity)):
                raise HTTPException(
                    status_code=400,
                    detail=f"Requested qty {sell_qty} exceeds held qty {pos.quantity}",
                )

            # Apply LOT_SIZE rounding
            filters = binance.get_symbol_filters(req.symbol)
            step_size = filters.get("lot_size", {}).get("stepSize")
            if step_size and step_size > Decimal("0"):
                sell_qty = (sell_qty // step_size) * step_size

            if sell_qty <= Decimal("0"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Quantity too small after LOT_SIZE rounding for {req.symbol}",
                )

            avg_entry = Decimal(str(pos.avg_entry_price)) if pos.avg_entry_price else Decimal("0")

        # Place market SELL on Binance
        try:
            order = binance._client.create_order(
                symbol=sym_clean,
                side="SELL",
                type="MARKET",
                quantity=float(sell_qty),
            )
            order_id = order.get("orderId", "unknown")
            executed_qty = Decimal(str(order.get("executedQty", sell_qty)))
            cum_quote = Decimal(str(order.get("cummulativeQuoteQty", "0")))
            if executed_qty > Decimal("0"):
                actual_fill = (cum_quote / executed_qty).quantize(Decimal("0.01"))
            else:
                actual_fill = binance.get_current_price(req.symbol)
        except BinanceAPIException as exc:
            _logger.error("Binance API error on manual SELL %s: %s", sym_clean, exc)
            raise HTTPException(status_code=500, detail=f"Binance order failed: {exc}")
        except Exception as exc:
            _logger.error("Unexpected error on manual SELL %s: %s", sym_clean, exc)
            raise HTTPException(status_code=500, detail=f"Order failed: {exc}")

        # Compute PnL
        fee_amount = executed_qty * actual_fill * Decimal(str(settings.TRADING_FEE_PCT))
        pnl = None
        if avg_entry > 0 and executed_qty > 0:
            pnl = (actual_fill - avg_entry) * executed_qty - fee_amount

        # Record trade in DB
        import uuid

        trade_id = str(uuid.uuid4())
        with get_db() as db:
            # Use the latest cycle_id so the FK constraint is satisfied
            latest_cycle = db.query(CycleRun).order_by(desc(CycleRun.started_at)).first()
            cycle_id = latest_cycle.cycle_id if latest_cycle else "unknown"

            trade = Trade(
                id=trade_id,
                cycle_id=cycle_id,
                symbol=req.symbol,
                side="SELL",
                proposed_quantity=float(sell_qty),
                executed_quantity=float(executed_qty),
                entry_price=float(avg_entry),
                executed_price=float(actual_fill),
                stop_loss_price=0,
                take_profit_price=0,
                order_id=str(order_id),
                status="FILLED",
                reasoning=f"Manual SELL from wallet — user-initiated",
                pnl=float(pnl) if pnl is not None else None,
            )
            db.add(trade)

            # Update position
            pos = db.query(Position).filter(Position.symbol == req.symbol).first()
            if pos:
                remaining = Decimal(str(pos.quantity)) - executed_qty
                if remaining <= Decimal("0"):
                    db.delete(pos)
                else:
                    pos.quantity = remaining
                    pos.current_price = float(actual_fill)
            db.commit()

        _logger.info(
            "Manual SELL filled: %s %s @ %s (pnl=%s, id=%s)",
            executed_qty, sym_clean, actual_fill, pnl, trade_id,
        )
        send_alert(
            f"Manual SELL: {executed_qty} {req.symbol} @ ${actual_fill} | PnL: ${pnl}",
            level="info",
        )

        return {
            "status": "filled",
            "symbol": req.symbol,
            "quantity": float(executed_qty),
            "fill_price": float(actual_fill),
            "pnl": float(pnl) if pnl is not None else None,
            "order_id": str(order_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        _logger.exception("POST /portfolio/sell failed")
        raise HTTPException(status_code=500, detail=f"Manual sell failed: {exc}")
