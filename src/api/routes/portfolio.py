"""Portfolio-related API endpoints for the AlphaCore system.

Exposes portfolio snapshots, performance metrics, cycle summaries,
and current open positions via a FastAPI ``APIRouter``.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc

from src.api.schemas import (
    CycleRunResponse,
    PerformanceMetricsResponse,
    PortfolioSnapshotResponse,
)
from src.database.connection import get_db
from src.database.crud import (
    get_performance_metrics,
    get_portfolio_history,
    get_sentiment_trade_performance,
)
from src.database.models import CycleRun, Position
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
