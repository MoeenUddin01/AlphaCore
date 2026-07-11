"""AgentState builder functions — produce ready-made states for isolation tests.

Each function returns a complete ``AgentState`` dict that can be passed
directly to an agent's ``run()`` method.  Tests can override individual
fields after construction for custom scenarios.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.agents.agent_state import AgentState, ProposedTrade


def clean_state_no_positions() -> AgentState:
    """AgentState with empty holdings and no trades."""
    return AgentState(
        cycle_id="test-cycle-id",
        timestamp=datetime.utcnow(),
        pipeline_data={},
        signals=[],
        proposed_trades=[],
        approved_trades=[],
        executed_trades=[],
        portfolio_summary={
            "total_value": 10000.0,
            "total_position_value": 0.0,
            "cash": 10000.0,
            "holdings": {},
            "positions": [],
        },
        risk_report={},
        cycle_log=[],
    )


def _holding_for(
    symbol: str,
    qty: Decimal,
    avg_entry: Decimal,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
    current_price: Decimal | None = None,
) -> dict[str, Any]:
    """Build a single holding dict for ``portfolio_summary["holdings"]``."""
    price = current_price or avg_entry
    h: dict[str, Any] = {
        "quantity": float(qty),
        "avg_entry_price": float(avg_entry),
        "current_price": float(price),
        "value": float(qty * price),
        "unrealized_pnl": float((price - avg_entry) * qty),
    }
    if stop_loss is not None:
        h["stop_loss_price"] = float(stop_loss)
    if take_profit is not None:
        h["take_profit_price"] = float(take_profit)
    return h


def state_with_open_position(
    symbol: str,
    quantity: Decimal,
    avg_entry_price: Decimal,
    stop_loss_price: Decimal | None = None,
    take_profit_price: Decimal | None = None,
) -> AgentState:
    """AgentState with one open position.

    The holding is populated in ``portfolio_summary["holdings"]``.
    Optional ``stop_loss_price`` and ``take_profit_price`` are included
    when provided so ``check_exit_conditions`` can evaluate them.
    """
    pos_value = float(quantity * avg_entry_price)
    holding = _holding_for(symbol, quantity, avg_entry_price,
                           stop_loss_price, take_profit_price)

    return AgentState(
        cycle_id="test-cycle-id",
        timestamp=datetime.utcnow(),
        pipeline_data={
            symbol: {
                "current_price": float(avg_entry_price),
                "fear_greed": {"value": 50},
            },
        },
        signals=[],
        proposed_trades=[],
        approved_trades=[],
        executed_trades=[],
        portfolio_summary={
            "total_value": 10000.0 + pos_value,
            "total_position_value": pos_value,
            "cash": 10000.0,
            "holdings": {symbol: holding},
            "positions": [{
                "symbol": symbol,
                "quantity": float(quantity),
                "avg_entry_price": float(avg_entry_price),
                "current_price": float(avg_entry_price),
                "value": pos_value,
            }],
        },
        risk_report={},
        cycle_log=[],
    )


def state_with_pending_auto_exit(
    symbol: str,
    quantity: Decimal,
    stop_loss_price: Decimal,
    take_profit_price: Decimal | None = None,
) -> AgentState:
    """AgentState with a position that has a stop-loss price set.

    Entry is fixed at 80.00 USDT so tests can choose a current price
    above/below the stop threshold without worrying about the entry
    price.
    """
    return state_with_open_position(
        symbol=symbol,
        quantity=quantity,
        avg_entry_price=Decimal("80.00"),
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
    )
