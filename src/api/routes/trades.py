"""Trade-related API endpoints for the AlphaCore system.

Exposes trade history listing, aggregate statistics, and single-trade
lookup by UUID via a FastAPI ``APIRouter``.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, func

from src.api.schemas import TradeResponse
from src.database.connection import get_db
from src.database.crud import get_trade_history
from src.database.models import Trade
from src.utils.logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get(
    "/history",
    response_model=list[TradeResponse],
    summary="Retrieve trade history",
    description="Return recent trades, optionally filtered by trading pair symbol.",
)
def list_trade_history(symbol: str | None = None, limit: int = 50) -> list[TradeResponse]:
    _logger.info("GET /trades/history (symbol=%s, limit=%d)", symbol, limit)
    try:
        trades = get_trade_history(symbol=symbol, limit=limit)
        _logger.info("GET /trades/history -> %d trade(s)", len(trades))
        return [TradeResponse(**t) for t in trades]
    except Exception:
        _logger.exception("GET /trades/history failed")
        raise HTTPException(status_code=500, detail="Failed to fetch trade history")


@router.get(
    "/stats",
    summary="Compute trade statistics",
    description="Return aggregate trade counts, most traded symbol, and total volume in USDT.",
)
def trade_stats() -> dict[str, Any]:
    _logger.info("GET /trades/stats")
    try:
        result: dict[str, Any] = {
            "total_buys": 0,
            "total_sells": 0,
            "total_filled": 0,
            "total_failed": 0,
            "most_traded_symbol": "",
            "total_volume_usdt": 0.0,
        }
        with get_db() as db:
            result["total_buys"] = (
                db.query(func.count(Trade.id))
                .filter(Trade.side == "BUY")
                .scalar()
                or 0
            )
            result["total_sells"] = (
                db.query(func.count(Trade.id))
                .filter(Trade.side == "SELL")
                .scalar()
                or 0
            )
            result["total_filled"] = (
                db.query(func.count(Trade.id))
                .filter(Trade.status == "FILLED")
                .scalar()
                or 0
            )
            result["total_failed"] = (
                db.query(func.count(Trade.id))
                .filter(Trade.status == "FAILED")
                .scalar()
                or 0
            )

            most_traded = (
                db.query(Trade.symbol, func.count(Trade.id).label("cnt"))
                .group_by(Trade.symbol)
                .order_by(desc("cnt"))
                .limit(1)
                .first()
            )
            if most_traded is not None:
                result["most_traded_symbol"] = most_traded[0]

            volume_row = (
                db.query(
                    func.sum(
                        Trade.executed_quantity * Trade.executed_price
                    )
                )
                .filter(
                    Trade.status == "FILLED",
                    Trade.executed_quantity.isnot(None),
                    Trade.executed_price.isnot(None),
                )
                .scalar()
            )
            if volume_row is not None:
                result["total_volume_usdt"] = float(volume_row)

        _logger.info(
            "GET /trades/stats -> buys=%d sells=%d filled=%d",
            result["total_buys"],
            result["total_sells"],
            result["total_filled"],
        )
        return result
    except Exception:
        _logger.exception("GET /trades/stats failed")
        raise HTTPException(status_code=500, detail="Failed to compute trade statistics")


@router.get(
    "/{trade_id}",
    response_model=TradeResponse,
    summary="Get trade by ID",
    description="Return a single trade by its UUID primary key. Returns 404 if not found.",
)
def get_trade(trade_id: str) -> TradeResponse:
    _logger.info("GET /trades/%s", trade_id)
    try:
        with get_db() as db:
            trade = db.query(Trade).filter(Trade.id == trade_id).first()
            if trade is None:
                raise HTTPException(status_code=404, detail="Trade not found")
            return TradeResponse.model_validate(trade)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("GET /trades/%s failed", trade_id)
        raise HTTPException(status_code=500, detail="Failed to fetch trade")
