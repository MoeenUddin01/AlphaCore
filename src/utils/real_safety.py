"""Real-trading safety checks for the Autonomous Crypto Quant system.

Provides a single ``real_safety_check()`` function that every real-money
order path must call before routing a trade to the exchange.  The
function enforces three hard limits:

* Kill switch (``real_trading_halted``)
* Max position size per trade (``REAL_MAX_POSITION_USD``)
* Max daily loss (``REAL_MAX_DAILY_LOSS_USD``)
* Max trades per day (``REAL_MAX_TRADES_PER_DAY``)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.database.real_crud import (
    get_real_daily_loss,
    get_real_trades_today_count,
    get_real_trading_halted,
    set_real_trading_halted,
)
from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)


def real_safety_check(
    *,
    symbol: str,
    side: str,
    proposed_quantity: Decimal,
    proposed_price: Decimal,
) -> dict[str, Any]:
    """Run all real-trading safety checks for a proposed trade.

    Checks are evaluated in order: kill switch first, then position
    size, then daily loss, then trade count.  The first failing check
    short-circuits and returns ``{"action": "deny", "reason": ...}``.

    If ``REAL_MAX_DAILY_LOSS_USD`` is exceeded the kill switch is
    automatically set to ``True`` as a safety measure.

    Args:
        symbol: Trading pair symbol (e.g. ``"BTC/USDT"``).
        side: ``"BUY"`` or ``"SELL"``.
        proposed_quantity: Proposed order quantity in base currency.
        proposed_price: Expected execution price in quote currency.

    Returns:
        Dict with keys ``action`` (``"allow"`` | ``"deny"``),
        ``reason`` (human-readable explanation), and ``limits``
        (dict of current limit values).
    """
    limits = {
        "max_position_usd": settings.REAL_MAX_POSITION_USD,
        "max_daily_loss_usd": settings.REAL_MAX_DAILY_LOSS_USD,
        "max_trades_per_day": settings.REAL_MAX_TRADES_PER_DAY,
    }

    # --- 1. Kill switch ---
    try:
        halted = get_real_trading_halted()
    except Exception:
        _logger.exception("Failed to read kill-switch state — denying trade by default")
        return {"action": "deny", "reason": "Kill switch state unreachable — denying as precaution", "limits": limits}

    if halted:
        _logger.warning("Trade DENIED for %s %s %s — kill switch is active", side, proposed_quantity, symbol)
        return {"action": "deny", "reason": "Real trading is halted via kill switch", "limits": limits}

    # --- 2. Max position size ---
    proposed_value = proposed_quantity * proposed_price
    abs_value = abs(proposed_value)
    if abs_value > settings.REAL_MAX_POSITION_USD:
        _logger.warning(
            "Trade DENIED for %s %s %s — $%.2f exceeds max position $%s",
            side, proposed_quantity, symbol, float(abs_value), settings.REAL_MAX_POSITION_USD,
        )
        return {
            "action": "deny",
            "reason": f"Proposed value ${float(abs_value):.2f} exceeds "
                      f"max position USD ${float(settings.REAL_MAX_POSITION_USD):.2f}",
            "limits": limits,
        }

    # --- 3. Max daily loss ---
    try:
        daily_loss = get_real_daily_loss()
    except Exception:
        _logger.exception("Failed to read daily loss — denying trade by default")
        return {"action": "deny", "reason": "Daily loss state unreachable — denying as precaution", "limits": limits}

    if daily_loss < -settings.REAL_MAX_DAILY_LOSS_USD:
        set_real_trading_halted(True)
        _logger.warning(
            "Daily loss $%.2f exceeds limit $%s — auto-halting real trading",
            float(daily_loss), settings.REAL_MAX_DAILY_LOSS_USD,
        )
        return {
            "action": "deny",
            "reason": f"Daily realised loss ${float(abs(daily_loss)):.2f} exceeds "
                      f"max daily loss USD ${float(settings.REAL_MAX_DAILY_LOSS_USD):.2f} — "
                      "kill switch auto-engaged",
            "limits": limits,
        }

    # --- 4. Max trades per day ---
    try:
        trades_today = get_real_trades_today_count()
    except Exception:
        _logger.exception("Failed to read trade count — denying trade by default")
        return {"action": "deny", "reason": "Trade count unreachable — denying as precaution", "limits": limits}

    if trades_today >= settings.REAL_MAX_TRADES_PER_DAY:
        _logger.warning(
            "Trade DENIED for %s — %d trades today exceeds limit of %d",
            symbol, trades_today, settings.REAL_MAX_TRADES_PER_DAY,
        )
        return {
            "action": "deny",
            "reason": f"{trades_today} trades executed today (limit: {settings.REAL_MAX_TRADES_PER_DAY})",
            "limits": limits,
        }

    # --- All checks passed ---
    _logger.info(
        "Safety check PASSED for %s %s %s — %.2f USD",
        side, proposed_quantity, symbol, float(abs_value),
    )
    return {"action": "allow", "reason": "All safety checks passed", "limits": limits}
