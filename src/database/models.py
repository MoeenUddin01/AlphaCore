"""SQLAlchemy ORM models for the Autonomous Crypto Quant system.

Defines five core tables that capture every trading cycle end-to-end:
cycle runs, prediction signals, executed trades, live positions, and
portfolio snapshots.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, JSON

from src.database.connection import Base


class CycleRun(Base):
    """Summary of one complete agent pipeline cycle.

    Tracks the lifecycle from start to completion and aggregates
    key counts (signals, proposals, approvals, executions) alongside
    portfolio-level P&L and drawdown metrics.
    """

    __tablename__ = "cycle_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cycle_id = Column(String(36), unique=True, nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    signals_count = Column(Integer, nullable=False, default=0)
    proposed_count = Column(Integer, nullable=False, default=0)
    approved_count = Column(Integer, nullable=False, default=0)
    executed_count = Column(Integer, nullable=False, default=0)
    portfolio_value = Column(Numeric(20, 8), nullable=True)
    pnl_unrealised = Column(Numeric(20, 8), nullable=True)
    pnl_realised = Column(Numeric(20, 8), nullable=True)
    drawdown_pct = Column(Numeric(10, 4), nullable=True)
    cycle_log = Column(JSON, nullable=True)


class Signal(Base):
    """Aggregated prediction signal for a single trading pair.

    Combines the LSTM price forecast and FinBERT sentiment score
    into one row per cycle per symbol.
    """

    __tablename__ = "signals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cycle_id = Column(String(36), ForeignKey("cycle_runs.cycle_id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    predicted_return = Column(Numeric(10, 6), nullable=False)
    direction = Column(String(10), nullable=False)
    confidence = Column(Numeric(10, 4), nullable=False)
    sentiment_score = Column(Numeric(10, 4), nullable=False)
    sentiment_label = Column(String(10), nullable=False)
    fear_greed_value = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Trade(Base):
    """Record of a proposed or executed trade.

    Captures the full lifecycle from proposal through execution,
    including fill details, order identifier, and realised P&L.
    """

    __tablename__ = "trades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cycle_id = Column(String(36), ForeignKey("cycle_runs.cycle_id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)
    proposed_quantity = Column(Numeric(20, 8), nullable=False)
    executed_quantity = Column(Numeric(20, 8), nullable=True)
    entry_price = Column(Numeric(20, 8), nullable=False)
    executed_price = Column(Numeric(20, 8), nullable=True)
    stop_loss_price = Column(Numeric(20, 8), nullable=False)
    take_profit_price = Column(Numeric(20, 8), nullable=False)
    order_id = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="proposed")
    is_sentiment_driven = Column(Boolean, nullable=False, default=True)
    trade_origin = Column(String(20), nullable=False, default="bot_sentiment")
    signal_confidence = Column(Numeric(10, 4), nullable=True)
    reasoning = Column(Text, nullable=True)
    pnl = Column(Numeric(20, 8), nullable=True)
    fee_paid = Column(Numeric(20, 8), nullable=True)
    is_pre_fix_artifact = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Position(Base):
    """Live position snapshot for a single trading pair.

    One row per actively held symbol. Updated each cycle to reflect
    the latest market price and unrealised P&L.
    """

    __tablename__ = "positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String(20), unique=True, nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    avg_entry_price = Column(Numeric(20, 8), nullable=False)
    current_price = Column(Numeric(20, 8), nullable=False)
    unrealised_pnl = Column(Numeric(20, 8), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PortfolioState(Base):
    """Singleton tracking portfolio-level state across cycles.

    Only one row exists (id='singleton'). Stores the peak portfolio
    value for drawdown calculations.
    """

    __tablename__ = "portfolio_state"

    id = Column(String(20), primary_key=True, default="singleton")
    peak_value = Column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    validation_start_date = Column(DateTime, nullable=True)


class PortfolioSnapshot(Base):
    """Point-in-time portfolio state captured at the end of a cycle.

    Stores the aggregate view: total value, cash balance, positions
    value, P&L splits, peak value tracking, and drawdown.
    """

    __tablename__ = "portfolio_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cycle_id = Column(String(36), ForeignKey("cycle_runs.cycle_id"), nullable=False, index=True)
    total_value = Column(Numeric(20, 8), nullable=False)
    cash = Column(Numeric(20, 8), nullable=False)
    positions_value = Column(Numeric(20, 8), nullable=False)
    unrealised_pnl = Column(Numeric(20, 8), nullable=False)
    realised_pnl = Column(Numeric(20, 8), nullable=False)
    peak_value = Column(Numeric(20, 8), nullable=False)
    drawdown_pct = Column(Numeric(10, 4), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# =============================================================================
# Real Trading Tables — structurally separate from test/paper tables
# All table names prefixed with "real_" so queries against test tables
# can never touch real data, and vice versa.
# =============================================================================


class RealTrade(Base):
    """Real-money trade record — isolated from paper/test trades.

    One row per proposed or executed real-money trade.  Structurally
    identical to ``Trade`` but lives in a separate table so that a
    bug or bad query in the test system can never touch real data.
    """

    __tablename__ = "real_trades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sync_id = Column(String(36), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)
    executed_quantity = Column(Numeric(20, 8), nullable=True)
    executed_price = Column(Numeric(20, 8), nullable=True)
    order_id = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="synced")
    pnl = Column(Numeric(20, 8), nullable=True)
    fee_paid = Column(Numeric(20, 8), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RealPosition(Base):
    """Real-money live position — isolated from paper/test positions.

    One row per actively held symbol in the real Binance account.
    Updated on every account-sync cycle.
    """

    __tablename__ = "real_positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String(20), unique=True, nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    avg_entry_price = Column(Numeric(20, 8), nullable=False)
    current_price = Column(Numeric(20, 8), nullable=False)
    unrealised_pnl = Column(Numeric(20, 8), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RealPortfolioSnapshot(Base):
    """Point-in-time real-portfolio state.

    Captured at the end of each account-sync cycle.  Tracks total
    value, cash, positions value, and P&L for the real-money account.
    """

    __tablename__ = "real_portfolio_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sync_id = Column(String(36), nullable=False, index=True)
    total_value = Column(Numeric(20, 8), nullable=False)
    cash = Column(Numeric(20, 8), nullable=False)
    positions_value = Column(Numeric(20, 8), nullable=False)
    unrealised_pnl = Column(Numeric(20, 8), nullable=False)
    realised_pnl = Column(Numeric(20, 8), nullable=False)
    peak_value = Column(Numeric(20, 8), nullable=False)
    drawdown_pct = Column(Numeric(10, 4), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RealPortfolioState(Base):
    """Singleton tracking real-portfolio peak value for drawdown.

    Only one row exists (id='singleton').  Structurally isolated from
    the paper-trading ``PortfolioState`` table.
    """

    __tablename__ = "real_portfolio_state"

    id = Column(String(20), primary_key=True, default="singleton")
    peak_value = Column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RealSafetyState(Base):
    """Singleton kill-switch state for real-money trading.

    Only one row exists (id='singleton').  ``trading_halted`` defaults
    to ``True`` so that on a fresh install no real trades can happen
    until the operator explicitly enables it via the dashboard.
    """

    __tablename__ = "real_safety_state"

    id = Column(String(20), primary_key=True, default="singleton")
    trading_halted = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
