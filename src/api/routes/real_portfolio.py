"""Real-money portfolio API endpoints for the AlphaCore system.

Exposes real portfolio snapshots, open positions, and history via a
FastAPI ``APIRouter`` — all data sourced from ``real_*`` tables only,
never touching paper/test data.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc

from src.api.schemas import RealPortfolioSnapshotResponse, RealPositionResponse
from src.database.connection import get_db
from src.database.models import RealPortfolioSnapshot, RealPosition
from src.database.real_crud import get_real_latest_snapshot, get_real_positions
from src.utils.logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/real/portfolio", tags=["real-portfolio"])


@router.get(
    "/latest",
    response_model=RealPortfolioSnapshotResponse | None,
    summary="Get latest real-portfolio snapshot",
    description="Return the most recent real-portfolio snapshot (total value, cash, P&L, drawdown).",
)
def real_latest_snapshot() -> RealPortfolioSnapshotResponse | None:
    _logger.info("GET /real/portfolio/latest")
    try:
        snap = get_real_latest_snapshot()
        if snap is None:
            return None
        return RealPortfolioSnapshotResponse.model_validate(snap)
    except Exception:
        _logger.exception("GET /real/portfolio/latest failed")
        raise HTTPException(status_code=500, detail="Failed to fetch real portfolio snapshot")


@router.get(
    "/positions",
    response_model=list[RealPositionResponse],
    summary="List open real positions",
    description="Return all open positions from the real-money account.",
)
def real_list_positions() -> list[RealPositionResponse]:
    _logger.info("GET /real/portfolio/positions")
    try:
        positions = get_real_positions()
        return [RealPositionResponse.model_validate(p) for p in positions]
    except Exception:
        _logger.exception("GET /real/portfolio/positions failed")
        raise HTTPException(status_code=500, detail="Failed to fetch real positions")


@router.get(
    "/history",
    response_model=list[RealPortfolioSnapshotResponse],
    summary="Real-portfolio snapshot history",
    description="Return recent real-portfolio snapshots ordered by creation time descending.",
)
def real_portfolio_history(limit: int = 50) -> list[RealPortfolioSnapshotResponse]:
    _logger.info("GET /real/portfolio/history (limit=%d)", limit)
    try:
        result: list[RealPortfolioSnapshotResponse] = []
        with get_db() as db:
            rows = (
                db.query(RealPortfolioSnapshot)
                .order_by(desc(RealPortfolioSnapshot.created_at))
                .limit(limit)
                .all()
            )
            for r in rows:
                result.append(RealPortfolioSnapshotResponse.model_validate(r))
        return result
    except Exception:
        _logger.exception("GET /real/portfolio/history failed")
        raise HTTPException(status_code=500, detail="Failed to fetch real portfolio history")
