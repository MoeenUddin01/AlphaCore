"""Signal-related API endpoints for the AlphaCore system.

Exposes the latest prediction signals, historical signal listing, and
a daily summary with bullish/bearish/neutral counts and averages.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, func

from src.api.schemas import SignalResponse
from src.database.connection import get_db
from src.database.crud import get_latest_signals
from src.database.models import Signal
from src.utils.logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get(
    "/latest",
    response_model=list[SignalResponse],
    summary="Get latest signals",
    description="Return all prediction signals from the most recent agent cycle.",
)
def latest_signals() -> list[SignalResponse]:
    _logger.info("GET /signals/latest")
    try:
        signals = get_latest_signals()
        _logger.info("GET /signals/latest -> %d signal(s)", len(signals))
        return [SignalResponse(**s) for s in signals]
    except Exception:
        _logger.exception("GET /signals/latest failed")
        raise HTTPException(status_code=500, detail="Failed to fetch latest signals")


@router.get(
    "/history",
    response_model=list[SignalResponse],
    summary="List historical signals",
    description="Return recent signals, optionally filtered by trading pair symbol.",
)
def signal_history(symbol: str | None = None, limit: int = 100) -> list[SignalResponse]:
    _logger.info("GET /signals/history (symbol=%s, limit=%d)", symbol, limit)
    try:
        result: list[SignalResponse] = []
        with get_db() as db:
            query = db.query(Signal).order_by(desc(Signal.created_at))
            if symbol is not None:
                query = query.filter(Signal.symbol == symbol)
            rows = query.limit(limit).all()
            for r in rows:
                result.append(SignalResponse.model_validate(r))
        _logger.info("GET /signals/history -> %d signal(s)", len(result))
        return result
    except Exception:
        _logger.exception("GET /signals/history failed")
        raise HTTPException(status_code=500, detail="Failed to fetch signal history")


@router.get(
    "/summary",
    summary="Daily signal summary",
    description="Return aggregate statistics for today's signals: total count, bullish/bearish/neutral breakdown, strongest signal, and average Fear & Greed value.",
)
def signal_summary() -> dict[str, Any]:
    _logger.info("GET /signals/summary")
    try:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        result: dict[str, Any] = {
            "total_signals_today": 0,
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "strongest_signal": {},
            "avg_fear_greed": 0.0,
        }

        with get_db() as db:
            base = db.query(Signal).filter(Signal.created_at >= today_start)

            result["total_signals_today"] = base.count()

            result["bullish_count"] = (
                base.filter(Signal.direction == "up").count()
            )
            result["bearish_count"] = (
                base.filter(Signal.direction == "down").count()
            )
            result["neutral_count"] = (
                base.filter(Signal.direction == "neutral").count()
            )

            strongest = (
                base.order_by(desc(Signal.confidence)).limit(1).first()
            )
            if strongest is not None:
                result["strongest_signal"] = {
                    "symbol": strongest.symbol,
                    "confidence": float(strongest.confidence),
                }

            fg_avg = (
                db.query(func.avg(Signal.fear_greed_value))
                .filter(Signal.created_at >= today_start)
                .scalar()
            )
            if fg_avg is not None:
                result["avg_fear_greed"] = round(float(fg_avg), 2)

        _logger.info(
            "GET /signals/summary -> total=%d bullish=%d bearish=%d",
            result["total_signals_today"],
            result["bullish_count"],
            result["bearish_count"],
        )
        return result
    except Exception:
        _logger.exception("GET /signals/summary failed")
        raise HTTPException(status_code=500, detail="Failed to compute signal summary")
