"""Create, read, and update operations for the AlphaCore database.

Provides high-level functions that persist and query the full agent
cycle — cycle runs, signals, trades, positions, and portfolio snapshots
— using the SQLAlchemy ORM models.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func

from src.agents.agent_state import AgentState
from src.database.connection import get_db
from src.database.models import CycleRun, PortfolioSnapshot, Position, Signal, Trade
from src.utils.logger import get_logger

_logger = get_logger(__name__)


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
                    reasoning=p.reasoning,
                    pnl=et.pnl,
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
    """Upsert the ``Position`` table from the current portfolio summary.

    Reads the position list inside ``portfolio_summary`` and merges
    each entry into the ``positions`` table (insert or update based on
    the unique ``symbol`` column).

    Args:
        state: The ``AgentState`` with ``portfolio_summary`` populated.
    """
    ps = state.get("portfolio_summary", {})
    positions_list: list[dict[str, Any]] = ps.get("positions", [])
    now = datetime.utcnow()

    if not positions_list:
        _logger.debug("No positions to update")
        return

    with get_db() as db:
        for pos in positions_list:
            symbol = pos.get("symbol", "")
            position = Position(
                symbol=symbol,
                quantity=Decimal(str(pos.get("quantity", 0))),
                avg_entry_price=Decimal(str(pos.get("avg_entry_price", 0))),
                current_price=Decimal(str(pos.get("current_price", 0))),
                unrealised_pnl=Decimal(str(pos.get("unrealized_pnl", 0))),
                updated_at=now,
            )
            db.merge(position)

    _logger.info("Upserted %d position(s)", len(positions_list))


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
                "pnl": float(r.pnl) if r.pnl else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
    return result


def get_latest_signals() -> list[dict[str, Any]]:
    """Return all signals from the most recent cycle.

    The most recent cycle is determined by the latest ``CycleRun``
    by ``started_at``.

    Returns:
        List of signal dicts, or an empty list if no cycles exist.
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

        rows = (
            db.query(Signal)
            .filter(Signal.cycle_id == latest)
            .order_by(desc(Signal.confidence))
            .all()
        )
        for r in rows:
            result.append({
                "id": r.id,
                "cycle_id": r.cycle_id,
                "symbol": r.symbol,
                "predicted_return": float(r.predicted_return) if r.predicted_return else 0.0,
                "direction": r.direction,
                "confidence": float(r.confidence) if r.confidence else 0.0,
                "sentiment_score": float(r.sentiment_score) if r.sentiment_score else 0.0,
                "sentiment_label": r.sentiment_label,
                "fear_greed_value": r.fear_greed_value,
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
            .filter(Trade.status == "FILLED")
            .scalar()
            or 0
        )
        metrics["total_trades"] = filled_count

        if filled_count > 0:
            pnl_values = (
                db.query(Trade.pnl)
                .filter(Trade.status == "FILLED", Trade.pnl.isnot(None))
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
