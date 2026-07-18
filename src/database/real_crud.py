"""CRUD operations for real-trading tables — isolated from paper/test data.

All functions read from and write to the ``real_*`` tables only.
Every write is wrapped in a transaction.  This module is the single
point of access for real account data.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.database.connection import get_db
from src.database.models import RealPortfolioSnapshot, RealPortfolioState, RealPosition, RealSafetyState, RealTrade
from src.utils.logger import get_logger

_logger = get_logger(__name__)


def save_real_sync_snapshot(
    *,
    total_value: Decimal,
    cash: Decimal,
    positions_value: Decimal,
    unrealised_pnl: Decimal,
    realised_pnl: Decimal,
    balances: dict[str, Decimal],
    positions: list[dict[str, Any]],
) -> str:
    """Persist a real-account sync snapshot and update positions.

    Args:
        total_value: Total portfolio value in USDT.
        cash: Free USDT (and other non-position) balance.
        positions_value: Value of all open positions.
        unrealised_pnl: Total unrealised P&L.
        realised_pnl: Total realised P&L (all-time).
        balances: Full asset balance dict (asset -> amount).
        positions: Current open positions from the real account.

    Returns:
        The ``sync_id`` (UUID string) written to the snapshot row.
    """
    sync_id = str(uuid4())
    now = datetime.utcnow()

    _logger.info("Saving real account sync snapshot — sync_id=%s", sync_id[:8])

    with get_db() as db:
        # --- update or insert peak_value singleton ---
        state = db.query(RealPortfolioState).filter(RealPortfolioState.id == "singleton").first()
        if state is None:
            peak = total_value
            db.add(
                RealPortfolioState(
                    id="singleton",
                    peak_value=peak,
                    updated_at=now,
                )
            )
        else:
            peak = max(state.peak_value, total_value)
            state.peak_value = peak
            state.updated_at = now

        drawdown = (Decimal("0") if peak == Decimal("0") else
                    ((peak - total_value) / peak) * Decimal("100"))

        # --- snapshot row ---
        snapshot = RealPortfolioSnapshot(
            id=str(uuid4()),
            sync_id=sync_id,
            total_value=total_value,
            cash=cash,
            positions_value=positions_value,
            unrealised_pnl=unrealised_pnl,
            realised_pnl=realised_pnl,
            peak_value=peak,
            drawdown_pct=drawdown,
            created_at=now,
        )
        db.add(snapshot)

        # --- upsert positions ---
        for pos in positions:
            sym = pos.get("symbol", "")
            qty = Decimal(str(pos.get("quantity", "0")))
            entry = Decimal(str(pos.get("avg_entry_price", "0")))
            curr = Decimal(str(pos.get("current_price", "0")))
            upnl = Decimal(str(pos.get("unrealised_pnl", "0")))

            existing = db.query(RealPosition).filter(RealPosition.symbol == sym).first()
            if qty <= Decimal("0"):
                if existing:
                    db.delete(existing)
                continue

            if existing:
                existing.quantity = qty
                existing.avg_entry_price = entry
                existing.current_price = curr
                existing.unrealised_pnl = upnl
                existing.updated_at = now
            else:
                db.add(
                    RealPosition(
                        id=str(uuid4()),
                        symbol=sym,
                        quantity=qty,
                        avg_entry_price=entry,
                        current_price=curr,
                        unrealised_pnl=upnl,
                        updated_at=now,
                    )
                )

        db.commit()
        _logger.info(
            "Real sync %s saved — total=%.2f cash=%.2f positions=%d drawdown=%.2f%%",
            sync_id[:8], float(total_value), float(cash), len(positions), float(drawdown),
        )

    return sync_id


def get_real_latest_snapshot() -> RealPortfolioSnapshot | None:
    """Fetch the most recent real-portfolio snapshot.

    Returns:
        The latest ``RealPortfolioSnapshot`` row, or ``None`` if none exist.
    """
    from sqlalchemy import desc

    with get_db() as db:
        return db.query(RealPortfolioSnapshot).order_by(desc(RealPortfolioSnapshot.created_at)).first()


def get_real_positions() -> list[RealPosition]:
    """Fetch all open real positions.

    Returns:
        List of ``RealPosition`` rows.
    """
    with get_db() as db:
        return db.query(RealPosition).all()


def get_real_portfolio_history(limit: int = 100) -> list[RealPortfolioSnapshot]:
    """Fetch recent real-portfolio snapshots.

    Args:
        limit: Maximum number of snapshots to return.

    Returns:
        List of ``RealPortfolioSnapshot`` rows ordered by ``created_at`` descending.
    """
    from sqlalchemy import desc

    with get_db() as db:
        return (
            db.query(RealPortfolioSnapshot)
            .order_by(desc(RealPortfolioSnapshot.created_at))
            .limit(limit)
            .all()
        )


def get_real_trade_history(
    symbol: str | None = None,
    limit: int = 50,
) -> list[RealTrade]:
    """Fetch recent real-money trades.

    Args:
        symbol: Optional trading pair filter.
        limit: Maximum number of trades to return.

    Returns:
        List of ``RealTrade`` rows ordered by ``created_at`` descending.
    """
    from sqlalchemy import desc

    with get_db() as db:
        query = db.query(RealTrade).order_by(desc(RealTrade.created_at))
        if symbol is not None:
            query = query.filter(RealTrade.symbol == symbol)
        return query.limit(limit).all()


# =============================================================================
# Safety / Kill-switch CRUD
# =============================================================================


def get_real_trading_halted() -> bool:
    """Return ``True`` if the real-trading kill switch is active.

    On a fresh install where no ``RealSafetyState`` row exists yet,
    the function creates one with ``trading_halted=True``.
    """
    with get_db() as db:
        state = db.query(RealSafetyState).filter(RealSafetyState.id == "singleton").first()
        if state is None:
            state = RealSafetyState(
                id="singleton",
                trading_halted=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(state)
            db.commit()
            _logger.warning("No RealSafetyState found — created singleton with trading_halted=True")
            return True
        return bool(state.trading_halted)


def set_real_trading_halted(halted: bool) -> None:
    """Set the real-trading kill switch to the given value.

    Args:
        halted: ``True`` to halt all real trading, ``False`` to allow it.
    """
    with get_db() as db:
        state = db.query(RealSafetyState).filter(RealSafetyState.id == "singleton").first()
        if state is None:
            state = RealSafetyState(
                id="singleton",
                trading_halted=halted,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(state)
        else:
            state.trading_halted = halted
            state.updated_at = datetime.utcnow()
        db.commit()
        _logger.info("Real-trading kill switch set to halted=%s", halted)


def get_real_daily_loss() -> Decimal:
    """Sum of realised P&L from real trades today.

    "Today" is defined as **UTC midnight** (00:00:00 UTC) to now.  This
    is unambiguous regardless of the server's local timezone.

    Returns:
        Negative ``Decimal`` if the day is a net loss, positive for net gain.
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    with get_db() as db:
        from sqlalchemy import func as sa_func

        result = (
            db.query(sa_func.coalesce(sa_func.sum(RealTrade.pnl), Decimal("0")))
            .filter(RealTrade.created_at >= today_start)
            .scalar()
        )
        return Decimal(str(result)) if result is not None else Decimal("0")


def get_real_trades_today_count() -> int:
    """Count of real trades executed today.

    "Today" is defined as **UTC midnight** (00:00:00 UTC) to now.  This
    is unambiguous regardless of the server's local timezone.

    Returns:
        Number of trades with ``created_at`` >= midnight UTC today.
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    with get_db() as db:
        from sqlalchemy import func as sa_func

        count = (
            db.query(sa_func.count(RealTrade.id))
            .filter(RealTrade.created_at >= today_start)
            .scalar()
        )
        return count or 0


def get_real_safety_status() -> dict:
    """Return a dict with all safety-relevant state for the dashboard.

    Returns:
        Dict containing ``trading_halted``, ``daily_loss``,
        ``trades_today``, and ``limits``.
    """
    from src.utils.config import settings

    halted = get_real_trading_halted()
    daily_loss = get_real_daily_loss()
    trades_today = get_real_trades_today_count()

    return {
        "trading_halted": halted,
        "daily_loss": daily_loss,
        "trades_today": trades_today,
        "limits": {
            "max_position_usd": settings.REAL_MAX_POSITION_USD,
            "max_daily_loss_usd": settings.REAL_MAX_DAILY_LOSS_USD,
            "max_trades_per_day": settings.REAL_MAX_TRADES_PER_DAY,
        },
    }
