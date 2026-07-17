"""Real-money trade API endpoints for the AlphaCore system.

Exposes real trade history and statistics via a FastAPI ``APIRouter``
— all data sourced from the ``real_trades`` table only.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, func

from src.api.schemas import RealTradeResponse
from src.database.connection import get_db
from src.database.models import RealTrade
from src.utils.logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/real/trades", tags=["real-trades"])


@router.get(
    "/history",
    response_model=list[RealTradeResponse],
    summary="Retrieve real trade history",
    description="Return recent real-money trades, optionally filtered by symbol.",
)
def real_list_trade_history(symbol: str | None = None, limit: int = 50) -> list[RealTradeResponse]:
    _logger.info("GET /real/trades/history (symbol=%s, limit=%d)", symbol, limit)
    try:
        result: list[RealTradeResponse] = []
        with get_db() as db:
            query = db.query(RealTrade).order_by(desc(RealTrade.created_at))
            if symbol is not None:
                query = query.filter(RealTrade.symbol == symbol)
            rows = query.limit(limit).all()
            for r in rows:
                result.append(RealTradeResponse.model_validate(r))
        return result
    except Exception:
        _logger.exception("GET /real/trades/history failed")
        raise HTTPException(status_code=500, detail="Failed to fetch real trade history")


@router.get(
    "/stats",
    summary="Compute real trade statistics",
    description="Return aggregate real trade counts, most traded symbol, and total volume in USDT.",
)
def real_trade_stats() -> dict[str, Any]:
    _logger.info("GET /real/trades/stats")
    try:
        result: dict[str, Any] = {
            "total_buys": 0,
            "total_sells": 0,
            "total_filled": 0,
            "most_traded_symbol": "",
            "total_volume_usdt": 0.0,
        }
        with get_db() as db:
            result["total_buys"] = (
                db.query(func.count(RealTrade.id))
                .filter(RealTrade.side == "BUY")
                .scalar()
                or 0
            )
            result["total_sells"] = (
                db.query(func.count(RealTrade.id))
                .filter(RealTrade.side == "SELL")
                .scalar()
                or 0
            )
            result["total_filled"] = (
                db.query(func.count(RealTrade.id))
                .filter(RealTrade.status == "FILLED")
                .scalar()
                or 0
            )

            most_traded = (
                db.query(RealTrade.symbol, func.count(RealTrade.id).label("cnt"))
                .group_by(RealTrade.symbol)
                .order_by(desc("cnt"))
                .limit(1)
                .first()
            )
            if most_traded is not None:
                result["most_traded_symbol"] = most_traded[0]

            volume_row = (
                db.query(
                    func.sum(
                        RealTrade.executed_quantity * RealTrade.executed_price
                    )
                )
                .filter(
                    RealTrade.status == "FILLED",
                    RealTrade.executed_quantity.isnot(None),
                    RealTrade.executed_price.isnot(None),
                )
                .scalar()
            )
            if volume_row is not None:
                result["total_volume_usdt"] = float(volume_row)

        return result
    except Exception:
        _logger.exception("GET /real/trades/stats failed")
        raise HTTPException(status_code=500, detail="Failed to compute real trade statistics")
