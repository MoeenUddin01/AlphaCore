"""Real-money safety/kill-switch API endpoints for the AlphaCore system.

Exposes the kill-switch state, hard-limit configuration, and current
usage via a FastAPI ``APIRouter``.  The toggle endpoint requires a
``CONFIRM`` string in the request body to prevent accidental toggles.
"""

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from src.database.real_crud import (
    get_real_safety_status,
    get_real_trading_halted,
    set_real_trading_halted,
)
from src.utils.logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/real/safety", tags=["real-safety"])


class SafetyStatusResponse(BaseModel):
    """Current safety status for the real-money account."""

    trading_halted: bool
    daily_loss: float
    trades_today: int
    limits: dict


class ToggleKillSwitchRequest(BaseModel):
    """Request body to toggle the real-trading kill switch."""

    halted: bool
    confirm: str


@router.get(
    "/status",
    response_model=SafetyStatusResponse,
    summary="Get real-trading safety status",
    description="Return kill-switch state, daily loss, trade count, and configured limits.",
)
def safety_status() -> SafetyStatusResponse:
    _logger.info("GET /real/safety/status")
    try:
        status = get_real_safety_status()
        return SafetyStatusResponse(
            trading_halted=status["trading_halted"],
            daily_loss=float(status["daily_loss"]),
            trades_today=status["trades_today"],
            limits={
                "max_position_usd": float(status["limits"]["max_position_usd"]),
                "max_daily_loss_usd": float(status["limits"]["max_daily_loss_usd"]),
                "max_trades_per_day": status["limits"]["max_trades_per_day"],
            },
        )
    except Exception:
        _logger.exception("GET /real/safety/status failed")
        raise HTTPException(status_code=500, detail="Failed to fetch real safety status")


@router.post(
    "/toggle",
    summary="Toggle real-trading kill switch",
    description="Requires ``confirm`` field to be exactly ``CONFIRM``.",
)
def safety_toggle(body: ToggleKillSwitchRequest) -> dict:
    _logger.info("POST /real/safety/toggle halted=%s", body.halted)
    if body.confirm != "CONFIRM":
        raise HTTPException(status_code=400, detail="Must provide confirm='CONFIRM'")
    try:
        set_real_trading_halted(body.halted)
        return {"trading_halted": body.halted, "message": "Kill switch updated"}
    except Exception:
        _logger.exception("POST /real/safety/toggle failed")
        raise HTTPException(status_code=500, detail="Failed to toggle kill switch")
