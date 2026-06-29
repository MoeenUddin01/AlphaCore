"""Pydantic v2 response schemas for the AlphaCore API.

All models are configured with ``from_attributes=True`` so they can be
populated directly from SQLAlchemy ORM instances.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SignalResponse(BaseModel):
    """Prediction signal for a single trading pair.

    Combines the LSTM price forecast and FinBERT sentiment score.
    """

    symbol: str
    predicted_return: float
    direction: str
    confidence: float
    sentiment_score: float
    sentiment_label: str
    fear_greed_value: int
    has_holding: bool = False
    distance_to_threshold: float = 0.0
    created_at: datetime

    model_config: Any = ConfigDict(from_attributes=True)


class TradeResponse(BaseModel):
    """Record of a proposed or executed trade."""

    id: str
    cycle_id: str
    symbol: str
    side: str
    proposed_quantity: float
    executed_quantity: float | None
    entry_price: float
    executed_price: float | None
    stop_loss_price: float
    take_profit_price: float
    order_id: str | None
    status: str
    reasoning: str
    pnl: float | None
    created_at: datetime

    model_config: Any = ConfigDict(from_attributes=True)


class PortfolioSnapshotResponse(BaseModel):
    """Point-in-time portfolio state captured at the end of a cycle."""

    cycle_id: str
    total_value: float
    cash: float
    positions_value: float
    unrealised_pnl: float
    realised_pnl: float
    peak_value: float
    drawdown_pct: float
    created_at: datetime

    model_config: Any = ConfigDict(from_attributes=True)


class PerformanceMetricsResponse(BaseModel):
    """Aggregate performance statistics computed from trade history."""

    total_trades: int
    win_rate: float
    avg_pnl_per_trade: float
    best_trade: float
    worst_trade: float
    total_realised_pnl: float
    current_drawdown: float

    model_config: Any = ConfigDict(from_attributes=True)


class CycleRunResponse(BaseModel):
    """Summary of one complete agent pipeline cycle."""

    cycle_id: str
    started_at: datetime
    completed_at: datetime | None
    signals_count: int
    proposed_count: int
    approved_count: int
    executed_count: int
    portfolio_value: float
    drawdown_pct: float
    cycle_log: list[str] | None

    model_config: Any = ConfigDict(from_attributes=True)


class HoldingResponse(BaseModel):
    """An open position in the current portfolio."""

    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    current_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    model_config: Any = ConfigDict(from_attributes=True)


class ClosedTradeResponse(BaseModel):
    """A fully-closed BUY→SELL pair from trade history."""

    symbol: str
    buy_price: float
    sell_price: float
    quantity: float
    realized_pnl: float
    realized_pnl_pct: float
    opened_at: datetime
    closed_at: datetime
    is_pre_fix_artifact: bool = False

    model_config: Any = ConfigDict(from_attributes=True)


class WalletResponse(BaseModel):
    """Full portfolio wallet snapshot — cash, open positions, closed trades."""

    cash_balance: float
    total_holdings_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    holdings: list[HoldingResponse]
    closed_positions: list[ClosedTradeResponse]

    model_config: Any = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    """API health check response."""

    status: str
    database: bool
    timestamp: datetime
    version: str

    model_config: Any = ConfigDict(from_attributes=True)
