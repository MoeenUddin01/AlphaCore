"""Create, read, and update operations for the AlphaCore database.

Provides high-level functions that persist and query the full agent
cycle — cycle runs, signals, trades, positions, and portfolio snapshots
— using the SQLAlchemy ORM models.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, func

from src.agents.agent_state import AgentState
from src.database.connection import get_db
from src.database.models import CycleRun, PortfolioSnapshot, PortfolioState, Position, Signal, Trade
from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)


def is_cycle_already_processed(cycle_id: str) -> bool:
    """Return ``True`` if a ``CycleRun`` with *cycle_id* exists in the DB.

    Args:
        cycle_id: The cycle identifier to check.

    Returns:
        ``True`` if a matching row exists, ``False`` otherwise.
    """
    with get_db() as db:
        exists = (
            db.query(CycleRun.cycle_id)
            .filter(CycleRun.cycle_id == cycle_id)
            .first()
        )
        return exists is not None


def save_cycle(state: AgentState) -> str:
    """Persist an entire agent cycle in a single transaction.

    Creates a ``CycleRun`` row, all ``Signal`` rows, all ``Trade`` rows
    (from executed trades), and a ``PortfolioSnapshot`` row. All writes
    share one database session and are committed together.

    Args:
        state: The completed ``AgentState`` from a pipeline run.

    Returns:
        The ``cycle_id`` that was saved.
    """
    cycle_id = state["cycle_id"]
    ps = state.get("portfolio_summary", {})
    now = datetime.utcnow()

    with get_db() as db:
        cycle = CycleRun(
            cycle_id=cycle_id,
            started_at=state["timestamp"],
            completed_at=now,
            signals_count=len(state.get("signals", [])),
            proposed_count=len(state.get("proposed_trades", [])),
            approved_count=len(state.get("approved_trades", [])),
            executed_count=len(state.get("executed_trades", [])),
            portfolio_value=Decimal(str(ps.get("total_value", 0))),
            pnl_unrealised=Decimal(str(ps.get("total_unrealized_pnl", 0))),
            pnl_realised=Decimal(str(ps.get("total_realised_pnl", 0))),
            drawdown_pct=Decimal(str(ps.get("drawdown_pct", 0))),
            cycle_log=state.get("cycle_log", []),
        )
        db.add(cycle)

        for sig in state.get("signals", []):
            db.add(
                Signal(
                    cycle_id=cycle_id,
                    symbol=sig.symbol,
                    predicted_return=Decimal(str(sig.predicted_return)),
                    direction=sig.direction,
                    confidence=Decimal(str(sig.confidence)),
                    sentiment_score=Decimal(str(sig.sentiment_score)),
                    sentiment_label=sig.sentiment_label,
                    fear_greed_value=sig.fear_greed_value,
                    created_at=sig.timestamp,
                )
            )

        for et in state.get("executed_trades", []):
            p = et.proposal
            db.add(
                Trade(
                    cycle_id=cycle_id,
                    symbol=p.symbol,
                    side=p.side,
                    proposed_quantity=p.quantity,
                    executed_quantity=et.executed_quantity,
                    entry_price=p.entry_price,
                    executed_price=et.executed_price,
                    stop_loss_price=p.stop_loss_price,
                    take_profit_price=p.take_profit_price,
                    order_id=et.order_id,
                    status=et.status,
                    is_sentiment_driven=getattr(p, "is_sentiment_driven", True),
                    signal_confidence=getattr(p, "signal_confidence", None),
                    reasoning=p.reasoning,
                    pnl=et.pnl,
                    fee_paid=getattr(et, "fee_paid", None),
                    created_at=et.timestamp,
                )
            )

        db.add(
            PortfolioSnapshot(
                cycle_id=cycle_id,
                total_value=Decimal(str(ps.get("total_value", 0))),
                cash=Decimal(str(ps.get("cash", 0))),
                positions_value=Decimal(str(ps.get("total_position_value", 0))),
                unrealised_pnl=Decimal(str(ps.get("total_unrealized_pnl", 0))),
                realised_pnl=Decimal(str(ps.get("total_realised_pnl", 0))),
                peak_value=Decimal(str(ps.get("peak_value", 0))),
                drawdown_pct=Decimal(str(ps.get("drawdown_pct", 0))),
                created_at=now,
            )
        )

    _logger.info("Cycle %s saved — %d signals, %d trades", cycle_id, len(state.get("signals", [])), len(state.get("executed_trades", [])))
    return cycle_id


def update_positions(state: AgentState) -> None:
    """Update the ``Position`` table from executed trades and portfolio metadata.

    Quantity changes are sourced from ``executed_trades`` directly — BUY
    increments, SELL decrements — ensuring the Position table always
    reflects the system's actual fills regardless of the pipeline path
    that produced them.  Metadata (current_price, unrealized_pnl) is
    sourced from ``portfolio_summary.positions`` when available.

    .. warning::

       This function reads quantity changes from ``state["executed_trades"]``,
       **not** from the ``Trade`` table.  Any trade that lands in the Trade
       table outside the normal scheduled cycle (e.g. a manually-placed order,
       a backfilled row, or a direct DB insert) will **never** be reconciled
       into the Position table by this function.  There is no periodic
       reconciliation that syncs Trade → Position.

       **Rule**: trades executed outside the pipeline must be manually
       reconciled into the Position table immediately after execution.
       Do not assume they will self-correct on the next cycle.

    Args:
        state: The ``AgentState`` with ``executed_trades`` populated.
    """
    executed_trades = state.get("executed_trades", [])
    ps = state.get("portfolio_summary", {})
    positions_list: list[dict[str, Any]] = ps.get("positions", [])
    now = datetime.utcnow()

    if not executed_trades and not positions_list:
        _logger.debug("No executed trades or positions to update")
        return

    with get_db() as db:
        # 1. Apply metadata from portfolio_summary.positions
        for pos in positions_list:
            symbol = pos.get("symbol", "")
            existing = db.query(Position).filter(Position.symbol == symbol).first()
            if existing:
                existing.current_price = Decimal(str(pos.get("current_price", 0)))
                existing.unrealised_pnl = Decimal(str(pos.get("unrealized_pnl", 0)))
                existing.updated_at = now

        # 2. Apply quantity changes from executed_trades
        trades_applied = 0
        for et in executed_trades:
            if et.status != "FILLED":
                continue
            trade = et.proposal
            symbol = trade.symbol
            side = trade.side
            qty = et.executed_quantity
            price = et.executed_price

            existing = db.query(Position).filter(Position.symbol == symbol).first()

            if side == "BUY":
                if existing:
                    total_qty = existing.quantity + qty
                    total_cost = (existing.quantity * existing.avg_entry_price) + (qty * price)
                    existing.quantity = total_qty
                    existing.avg_entry_price = total_cost / total_qty if total_qty > 0 else existing.avg_entry_price
                    existing.updated_at = now
                else:
                    position = Position(
                        symbol=symbol,
                        quantity=qty,
                        avg_entry_price=price,
                        current_price=price,
                        unrealised_pnl=Decimal("0"),
                        updated_at=now,
                    )
                    db.add(position)
                trades_applied += 1
                _logger.info("Position added/updated: %s qty=%s avg_entry=%s", symbol, qty, price)

            elif side == "SELL":
                if existing:
                    existing.quantity -= qty
                    if existing.quantity <= Decimal("0"):
                        db.delete(existing)
                        _logger.info("Position fully closed (SELL): %s", symbol)
                    else:
                        existing.updated_at = now
                        _logger.info("Position reduced (SELL): %s qty=%s", symbol, existing.quantity)
                    trades_applied += 1
                else:
                    _logger.warning("SELL executed for %s but no open Position row found", symbol)

    _logger.info("Updated positions from %d executed trade(s) and %d portfolio position(s)",
                 trades_applied, len(positions_list))


def _compute_cash_from_trades(initial_capital: Decimal) -> Decimal:
    """Compute available cash from all-time filled trade history.

    Args:
        initial_capital: The starting portfolio capital.

    Returns:
        Cash balance = initial_capital - total_spent_on_buys + total_received_from_sells.
    """
    total_spent = Decimal("0")
    total_received = Decimal("0")
    with get_db() as db:
        trades = db.query(Trade).filter(Trade.status == "FILLED").all()
        for t in trades:
            qty = Decimal(str(t.executed_quantity or 0))
            price = Decimal(str(t.executed_price or 0))
            fee = Decimal(str(t.fee_paid or 0))
            amount = qty * price
            if t.side == "BUY":
                total_spent += amount + fee
            elif t.side == "SELL":
                total_received += amount - fee
    return initial_capital - total_spent + total_received


def get_total_realised_pnl() -> Decimal:
    """Sum of Trade.pnl for every FILLED SELL — the portfolio-wide ledger.

    .. important::

       **Artifact-inclusion is deliberate.**  This function does *not*
       filter ``is_pre_fix_artifact``.  It was built as the single source
       of truth for portfolio-wide realised P&L — the ledger that answers
       "what actually happened to this portfolio's cash balance?"  Every
       fill that touched the exchange, including pre-fix trades with zero
       PnL (W07 artifacts), contributed to the real cash flow and must be
       counted here so that ``SUM(Trade.pnl)`` always agrees with
       ``PortfolioSnapshot.realised_pnl`` (see T01 check #6).  Two ledgers
       disagreeing was the original R08 bug; this function exists to
       prevent that class of bug from recurring.

    .. note::

       **Contrast with scoped consumers that exclude artifacts:**

       - :func:`get_performance_metrics` — filters ``is_pre_fix_artifact``
         because it answers "how well does the current strategy perform on
         trustworthy data?"  Including zero-PnL artifact SELLs would drag
         win rate and average PnL down, creating a misleading impression
         of strategy performance.
       - :func:`get_sentiment_trade_performance` — also filters artifacts,
         and further filters by ``validation_start_date``, because it
         answers "are recent sentiment-driven trades generating alpha?"
         Pre-fix noise would poison that statistical signal.

       All three functions are correct within their scope.  The portfolio-
       wide counter (this function) must include everything.  The strategy-
       evaluation counters must exclude noise.  The distinction is
       intentional, not an inconsistency.

    Returns:
        Total realised P&L across the entire trade history (including
        pre-fix artifact trades).
    """
    with get_db() as db:
        result = (
            db.query(func.sum(Trade.pnl))
            .filter(
                Trade.status == "FILLED",
                Trade.side == "SELL",
                Trade.pnl.isnot(None),
            )
            .scalar()
        )
        return Decimal(str(result)) if result is not None else Decimal("0")


def get_current_portfolio_state() -> dict[str, Any]:
    """Build a complete portfolio summary from database state and live prices.

    Queries the Position table for open positions, fetches live prices,
    retrieves SL/TP from the most recent trade per symbol, and computes
    total_value, cash, holdings, peak_value, and drawdown_pct.  Realised
    P&L is derived fresh from ``Trade.pnl`` every call — no cumulative
    in-memory tracking.

    Returns:
        Dict with keys: total_value, cash, holdings, peak_value, drawdown_pct.
    """
    from src.data.binance_client import BinanceClient

    binance = BinanceClient()
    initial_capital = settings.PORTFOLIO_INITIAL_CAPITAL
    total_realised_pnl = get_total_realised_pnl()

    with get_db() as db:
        positions = db.query(Position).all()

        holdings: dict[str, dict[str, Any]] = {}
        total_position_value = Decimal("0")

        for pos in positions:
            sym = pos.symbol
            qty = pos.quantity
            if qty <= 0:
                continue
            avg_entry = pos.avg_entry_price

            try:
                live_price = Decimal(str(binance.get_current_price(sym)))
            except Exception:
                live_price = Decimal(str(pos.current_price)) if pos.current_price else Decimal("0")

            pos_value = qty * live_price
            total_position_value += pos_value
            unrealised_pnl = (live_price - avg_entry) * qty if avg_entry > 0 else Decimal("0")

            trade = (
                db.query(Trade)
                .filter(
                    and_(
                        Trade.symbol == sym,
                        Trade.side == "BUY",
                        Trade.status == "FILLED",
                    )
                )
                .order_by(desc(Trade.created_at))
                .first()
            )
            sl_price = Decimal(str(trade.stop_loss_price)) if trade and trade.stop_loss_price else Decimal("0")
            tp_price = Decimal(str(trade.take_profit_price)) if trade and trade.take_profit_price else Decimal("0")

            holdings[sym] = {
                "quantity": qty,
                "avg_entry_price": avg_entry,
                "current_price": live_price,
                "unrealized_pnl": unrealised_pnl,
                "value": pos_value,
                "stop_loss_price": sl_price,
                "take_profit_price": tp_price,
            }

        pstate = db.query(PortfolioState).filter(PortfolioState.id == "singleton").first()
        if pstate is None:
            peak_value = initial_capital
            db.add(PortfolioState(id="singleton", peak_value=peak_value, updated_at=datetime.utcnow()))
        else:
            peak_value = pstate.peak_value

    cash = _compute_cash_from_trades(initial_capital)
    total_value = cash + total_position_value

    if total_value > peak_value:
        peak_value = total_value
        with get_db() as db:
            pstate = db.query(PortfolioState).filter(PortfolioState.id == "singleton").first()
            if pstate:
                pstate.peak_value = peak_value
                pstate.updated_at = datetime.utcnow()

    drawdown_pct = ((peak_value - total_value) / peak_value * 100) if peak_value > 0 else Decimal("0")

    return {
        "total_value": total_value,
        "cash": cash,
        "holdings": holdings,
        "peak_value": peak_value,
        "drawdown_pct": drawdown_pct,
        "total_realised_pnl": total_realised_pnl,
    }


def get_portfolio_history(limit: int = 100) -> list[dict[str, Any]]:
    """Return the most recent portfolio snapshots as dicts.

    Args:
        limit: Maximum number of snapshots to return.

    Returns:
        List of dicts ordered by ``created_at`` descending.
    """
    result: list[dict[str, Any]] = []
    with get_db() as db:
        rows = (
            db.query(PortfolioSnapshot)
            .order_by(desc(PortfolioSnapshot.created_at))
            .limit(limit)
            .all()
        )
        for r in rows:
            result.append({
                "id": r.id,
                "cycle_id": r.cycle_id,
                "total_value": float(r.total_value) if r.total_value else 0.0,
                "cash": float(r.cash) if r.cash else 0.0,
                "positions_value": float(r.positions_value) if r.positions_value else 0.0,
                "unrealised_pnl": float(r.unrealised_pnl) if r.unrealised_pnl else 0.0,
                "realised_pnl": float(r.realised_pnl) if r.realised_pnl else 0.0,
                "peak_value": float(r.peak_value) if r.peak_value else 0.0,
                "drawdown_pct": float(r.drawdown_pct) if r.drawdown_pct else 0.0,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
    return result


def get_trade_history(
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent trades, optionally filtered by symbol.

    Args:
        symbol: Trading pair filter (e.g. ``BTC/USDT``). ``None`` for all.
        limit: Maximum number of trades to return.

    Returns:
        List of trade dicts ordered by ``created_at`` descending.
    """
    result: list[dict[str, Any]] = []
    with get_db() as db:
        query = db.query(Trade).order_by(desc(Trade.created_at))
        if symbol is not None:
            query = query.filter(Trade.symbol == symbol)
        rows = query.limit(limit).all()
        for r in rows:
            result.append({
                "id": r.id,
                "cycle_id": r.cycle_id,
                "symbol": r.symbol,
                "side": r.side,
                "proposed_quantity": float(r.proposed_quantity) if r.proposed_quantity else 0.0,
                "executed_quantity": float(r.executed_quantity) if r.executed_quantity else None,
                "entry_price": float(r.entry_price) if r.entry_price else 0.0,
                "executed_price": float(r.executed_price) if r.executed_price else None,
                "stop_loss_price": float(r.stop_loss_price) if r.stop_loss_price else 0.0,
                "take_profit_price": float(r.take_profit_price) if r.take_profit_price else 0.0,
                "order_id": r.order_id,
                "status": r.status,
                "reasoning": r.reasoning,
                "is_sentiment_driven": bool(r.is_sentiment_driven) if r.is_sentiment_driven is not None else None,
                "fee_paid": float(r.fee_paid) if r.fee_paid else None,
                "signal_confidence": float(r.signal_confidence) if r.signal_confidence else None,
                "pnl": float(r.pnl) if r.pnl else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
    return result


def get_open_trade_for_symbol(symbol: str) -> dict[str, Any] | None:
    """Return the most recent filled BUY trade for *symbol*.

    Used by the Portfolio Monitor to retrieve stop-loss and take-profit
    prices for open position exit checks.

    Args:
        symbol: Trading pair (e.g. ``BTC/USDT``).

    Returns:
        Dict with keys ``stop_loss_price``, ``take_profit_price``,
        ``entry_price``, ``symbol``, ``id``, or ``None`` if no trade found.
    """
    with get_db() as db:
        trade = (
            db.query(Trade)
            .filter(
                and_(
                    Trade.symbol == symbol,
                    Trade.side == "BUY",
                    Trade.status == "FILLED",
                )
            )
            .order_by(desc(Trade.created_at))
            .first()
        )
    if trade is None:
        _logger.debug("No open trade found for %s", symbol)
        return None

    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "entry_price": float(trade.entry_price) if trade.entry_price else 0.0,
        "stop_loss_price": float(trade.stop_loss_price) if trade.stop_loss_price else 0.0,
        "take_profit_price": float(trade.take_profit_price) if trade.take_profit_price else 0.0,
    }


def get_latest_signals() -> list[dict[str, Any]]:
    """Return all signals from the most recent cycle.

    The most recent cycle is determined by the latest ``CycleRun``
    by ``started_at``.

    Returns:
        List of signal dicts enriched with ``has_holding`` and
        ``distance_to_threshold``, or an empty list if no cycles exist.
    """
    result: list[dict[str, Any]] = []
    with get_db() as db:
        latest = (
            db.query(CycleRun.cycle_id)
            .order_by(desc(CycleRun.started_at))
            .limit(1)
            .scalar()
        )
        if latest is None:
            return result

        # Determine which symbols are currently held
        held_symbols: set[str] = {
            p.symbol for p in db.query(Position).all() if p.quantity > 0
        }

        rows = (
            db.query(Signal)
            .filter(Signal.cycle_id == latest)
            .order_by(desc(Signal.confidence))
            .all()
        )
        for r in rows:
            sym = r.symbol
            score = float(r.sentiment_score) if r.sentiment_score else 0.0
            has_holding = sym in held_symbols
            threshold = -0.30 if has_holding else 0.30
            distance_to_threshold = abs(threshold - score)

            result.append({
                "id": r.id,
                "cycle_id": r.cycle_id,
                "symbol": sym,
                "predicted_return": float(r.predicted_return) if r.predicted_return else 0.0,
                "direction": r.direction,
                "confidence": float(r.confidence) if r.confidence else 0.0,
                "sentiment_score": score,
                "sentiment_label": r.sentiment_label,
                "fear_greed_value": r.fear_greed_value,
                "has_holding": has_holding,
                "distance_to_threshold": round(distance_to_threshold, 4),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
    return result


def get_performance_metrics() -> dict[str, Any]:
    """Aggregate performance statistics from the database.

    Computes:
        - ``total_trades`` — number of trades with status ``FILLED``
        - ``win_rate`` — fraction of filled trades with positive PnL
        - ``avg_pnl`` — mean realised PnL per filled trade
        - ``best_trade`` — maximum realised PnL
        - ``worst_trade`` — minimum realised PnL
        - ``total_realised_pnl`` — sum of all realised PnL
        - ``current_drawdown_pct`` — drawdown from the latest snapshot

    Returns:
        Dict with all computed metrics. Values default to ``0`` / ``0.0``
        when no data is available.
    """
    metrics: dict[str, Any] = {
        "total_trades": 0,
        "win_rate": 0.0,
        "avg_pnl": 0.0,
        "best_trade": 0.0,
        "worst_trade": 0.0,
        "total_realised_pnl": 0.0,
        "current_drawdown_pct": 0.0,
    }

    with get_db() as db:
        filled_count: int = (
            db.query(func.count(Trade.id))
            .filter(
                Trade.status == "FILLED",
                Trade.is_pre_fix_artifact == False,
            )
            .scalar()
            or 0
        )
        metrics["total_trades"] = filled_count

        if filled_count > 0:
            pnl_values = (
                db.query(Trade.pnl)
                .filter(
                    Trade.status == "FILLED",
                    Trade.is_pre_fix_artifact == False,
                    Trade.pnl.isnot(None),
                )
                .all()
            )
            pnl_list = [float(row[0]) for row in pnl_values if row[0] is not None]

            if pnl_list:
                metrics["avg_pnl"] = sum(pnl_list) / len(pnl_list)
                metrics["best_trade"] = max(pnl_list)
                metrics["worst_trade"] = min(pnl_list)
                wins = sum(1 for p in pnl_list if p > 0)
                metrics["win_rate"] = wins / len(pnl_list)
                metrics["total_realised_pnl"] = sum(pnl_list)

        latest_dd = (
            db.query(PortfolioSnapshot.drawdown_pct)
            .order_by(desc(PortfolioSnapshot.created_at))
            .limit(1)
            .scalar()
        )
        if latest_dd is not None:
            metrics["current_drawdown_pct"] = float(latest_dd)

    return metrics


def check_strategy_decay() -> dict[str, Any]:
    """Detect strategy decay by comparing recent vs all-time win rate.

    Queries the most recent 10 filled trades and compares their win rate
    against the all-time win rate. If the recent win rate has fallen
    more than 20 percentage points below the all-time rate, the strategy
    may be degrading in current market conditions.

    Returns:
        Dict with keys: ``recent_win_rate``, ``all_time_win_rate``,
        ``drop_pct_points``, ``recent_trades_count``, ``is_decaying``,
        ``message``. If fewer than 10 recent trades exist, ``is_decaying``
        is ``False`` with a ``message`` explaining insufficient data.
    """
    result: dict[str, Any] = {
        "recent_win_rate": 0.0,
        "all_time_win_rate": 0.0,
        "drop_pct_points": 0.0,
        "recent_trades_count": 0,
        "is_decaying": False,
        "message": "",
    }

    with get_db() as db:
        all_filled = (
            db.query(Trade.pnl)
            .filter(Trade.status == "FILLED", Trade.pnl.isnot(None))
            .order_by(desc(Trade.created_at))
            .all()
        )

    pnl_list = [float(row[0]) for row in all_filled if row[0] is not None]
    total = len(pnl_list)

    if total < 10:
        result["message"] = (
            f"Insufficient trades for decay analysis "
            f"({total} filled trades, need at least 10)"
        )
        return result

    recent = pnl_list[:10]
    all_pnl = pnl_list

    recent_wins = sum(1 for p in recent if p > 0)
    all_wins = sum(1 for p in all_pnl if p > 0)

    recent_win_rate = recent_wins / 10 * 100
    all_time_win_rate = all_wins / total * 100
    drop = all_time_win_rate - recent_win_rate

    result["recent_win_rate"] = round(recent_win_rate, 2)
    result["all_time_win_rate"] = round(all_time_win_rate, 2)
    result["drop_pct_points"] = round(drop, 2)
    result["recent_trades_count"] = 10

    if drop > 20:
        result["is_decaying"] = True
        result["message"] = (
            f"Strategy may be decaying: recent win rate {recent_win_rate:.1f}% "
            f"is {drop:.1f}pp below all-time {all_time_win_rate:.1f}%. "
            f"Consider reviewing strategy parameters or pausing trading."
        )
        _logger.warning("Strategy decay detected: %s", result["message"])
    else:
        result["message"] = (
            f"Recent win rate {recent_win_rate:.1f}% is within "
            f"{drop:.1f}pp of all-time {all_time_win_rate:.1f}% — no decay signal."
        )

    return result


def get_sentiment_trade_performance(days: int = 30) -> dict[str, Any]:
    """Analyse performance of sentiment-driven trades within the last *days*.

    Queries filled trades where ``is_sentiment_driven`` is True and
    ``created_at`` falls within the window. Computes win/loss statistics
    and compares average sentiment confidence between winners and losers.

    .. note::

        Trades created before ``validation_start_date`` (set in the
        ``portfolio_state`` singleton table) are excluded — this resets
        the sample window to count only post-reset trades, without
        deleting any historical data.

    Args:
        days: Lookback window in days (default 30).

    Returns:
        Dict with keys ``total_sentiment_trades``, ``winning_trades``,
        ``losing_trades``, ``win_rate_pct``, ``avg_win_amount``,
        ``avg_loss_amount``, ``total_pnl``, ``avg_sentiment_score_winners``,
        ``avg_sentiment_score_losers``, ``is_statistically_ready``.
    """
    import datetime as dt
    from collections import Counter

    from src.database.models import PortfolioState

    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)

    with get_db() as db:
        # Read validation_start_date from the singleton row.
        pstate = db.query(PortfolioState).filter(PortfolioState.id == "singleton").first()
        val_start = pstate.validation_start_date if pstate and pstate.validation_start_date else cutoff
        trade_date_filter = and_(
            Trade.created_at >= cutoff,
            Trade.created_at >= val_start,
        )

        # Log breakdown of all sentiment-driven trades by status for auditability.
        all_statuses = (
            db.query(Trade.status)
            .filter(
                and_(
                    Trade.is_sentiment_driven == True,
                    Trade.is_pre_fix_artifact == False,
                    trade_date_filter,
                )
            )
            .all()
        )
        status_counts = Counter(row[0] for row in all_statuses)
        _logger.info(
            "Sentiment trade status breakdown (last %d days): %s",
            days,
            dict(status_counts),
        )

        rows = (
            db.query(Trade)
            .filter(
                and_(
                    Trade.is_sentiment_driven == True,
                    Trade.is_pre_fix_artifact == False,
                    Trade.status == "FILLED",
                    trade_date_filter,
                )
            )
            .all()
        )

        # Materialise all needed attributes while session is open.
        _rows: list[dict[str, Any]] = [
            {
                "pnl": float(r.pnl) if r.pnl is not None else None,
                "signal_confidence": float(r.signal_confidence) if r.signal_confidence is not None else None,
            }
            for r in rows
        ]

    total = len(_rows)
    winners = [r for r in _rows if r["pnl"] is not None and r["pnl"] > 0]
    losers = [r for r in _rows if r["pnl"] is not None and r["pnl"] <= 0]

    total_sentiment_trades = total
    winning_trades = len(winners)
    losing_trades = len(losers)
    settled_trades = winning_trades + losing_trades
    win_rate_pct = (winning_trades / settled_trades * 100) if settled_trades > 0 else 0.0

    avg_win_amount = (
        sum(r["pnl"] for r in winners) / winning_trades
        if winning_trades > 0
        else 0.0
    )
    avg_loss_amount = (
        sum(r["pnl"] for r in losers) / losing_trades
        if losing_trades > 0
        else 0.0
    )

    total_pnl = sum(r["pnl"] for r in _rows if r["pnl"] is not None)

    scores_winners = [r["signal_confidence"] for r in winners if r["signal_confidence"] is not None]
    scores_losers = [r["signal_confidence"] for r in losers if r["signal_confidence"] is not None]

    avg_sentiment_score_winners = (
        sum(scores_winners) / len(scores_winners)
        if scores_winners
        else 0.0
    )
    avg_sentiment_score_losers = (
        sum(scores_losers) / len(scores_losers)
        if scores_losers
        else 0.0
    )

    is_statistically_ready = settled >= 30
    if not is_statistically_ready:
        needed = 30 - settled
        _logger.warning(
            "Sentiment trade sample too small (%d settled trades) — need %d more "
            "for statistically reliable validation",
            settled, needed,
        )

    return {
        "total_sentiment_trades": total_sentiment_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate_pct": round(win_rate_pct, 2),
        "avg_win_amount": round(avg_win_amount, 2),
        "avg_loss_amount": round(avg_loss_amount, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_sentiment_score_winners": round(avg_sentiment_score_winners, 4),
        "avg_sentiment_score_losers": round(avg_sentiment_score_losers, 4),
        "is_statistically_ready": is_statistically_ready,
    }
