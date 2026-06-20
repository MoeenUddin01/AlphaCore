"""Execution Agent — routes approved trades to Binance Testnet.

Takes risk-approved trade proposals, fetches live prices, accounts for
slippage, places market orders, and records fills in the agent state.
"""

import random
from datetime import datetime
from decimal import Decimal

from binance.exceptions import BinanceAPIException

from src.agents.agent_state import AgentState, ExecutedTrade, ProposedTrade
from src.data.binance_client import BinanceClient
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance, retry_with_backoff
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class ExecutionAgent:
    """Order execution agent — places market orders on Binance Testnet."""

    def __init__(self) -> None:
        _logger.info("Initialising ExecutionAgent")
        self.binance = BinanceClient()

    @retry_with_backoff
    def run(self, state: AgentState) -> AgentState:
        """Execute every approved trade as a market order.

        For each trade: fetch live price, apply slippage, place market
        order on Binance Testnet, record fill details.

        Args:
            state: Current LangGraph agent state with ``approved_trades``.

        Returns:
            Updated state with ``executed_trades`` appended.
        """
        _logger.info("ExecutionAgent run — cycle %s", state["cycle_id"])

        approved = state.get("approved_trades", [])
        _logger.info("Attempting to execute %d approved trade(s)", len(approved))

        for trade in approved:
            executed = self._execute_trade(trade, state)
            if executed is not None:
                state["executed_trades"].append(executed)

        state["cycle_log"].append(
            f"[{datetime.utcnow().isoformat()}] ExecutionAgent: "
            f"executed {sum(1 for et in state['executed_trades'] if et.status == 'FILLED')}/"
            f"{len(approved)} trades "
            f"({sum(1 for et in state['executed_trades'] if et.status == 'FAILED')} failed)"
        )
        _logger.info(
            "ExecutionAgent done — %d/%d executed",
            len(state["executed_trades"]),
            len(approved),
        )
        return state

    def _execute_trade(self, trade: ProposedTrade, state: AgentState) -> ExecutedTrade | None:
        """Execute a single trade proposal.

        Args:
            trade: The approved trade to execute.
            state: Full agent state (used for timestamp).

        Returns:
            An ExecutedTrade record or None if execution was skipped.
        """
        symbol = trade.symbol
        sym_clean = format_pair_for_binance(symbol)
        side = trade.side

        try:
            live_price = self.binance.get_current_price(symbol)
        except Exception as exc:
            _logger.error("Failed to fetch live price for %s: %s", sym_clean, exc)
            return ExecutedTrade(
                proposal=trade,
                executed_price=Decimal("0"),
                executed_quantity=Decimal("0"),
                order_id="",
                status="FAILED",
                timestamp=state["timestamp"],
                fee_paid=Decimal("0"),
                pnl=Decimal("0"),
            )

        slippage_pct = random.uniform(0.0, 0.0015)
        if side == "BUY":
            fill_price = live_price * (Decimal("1") + Decimal(str(slippage_pct)))
        else:
            fill_price = live_price * (Decimal("1") - Decimal(str(slippage_pct)))

        fill_price = fill_price.quantize(Decimal("0.01"))
        qty = trade.quantity

        _logger.info(
            "Placing %s market order: %s %s @ ~%s (live=%s, slippage=%.4f%%)",
            side, qty, sym_clean, fill_price, live_price, slippage_pct * 100,
        )

        try:
            order = self.binance._client.create_order(
                symbol=sym_clean,
                side=side,
                type="MARKET",
                quantity=float(qty),
            )
            order_id = order.get("orderId", str(order.get("clientOrderId", "unknown")))
            executed_qty = Decimal(str(order.get("executedQty", qty)))
            cum_quote = Decimal(str(order.get("cummulativeQuoteQty", "0")))
            if executed_qty > Decimal("0"):
                actual_fill = (cum_quote / executed_qty).quantize(Decimal("0.01"))
            else:
                actual_fill = fill_price
            status_flag = "FILLED"
            _logger.info(
                "Order filled: %s %s %s @ %s (id=%s)",
                side, executed_qty, sym_clean, actual_fill, order_id,
            )
        except BinanceAPIException as exc:
            _logger.error("Binance API error for %s %s: %s", side, sym_clean, exc)
            order_id = ""
            actual_fill = fill_price
            executed_qty = Decimal("0")
            status_flag = "FAILED"
        except Exception as exc:
            _logger.error("Unexpected error for %s %s: %s", side, sym_clean, exc)
            order_id = ""
            actual_fill = fill_price
            executed_qty = Decimal("0")
            status_flag = "FAILED"

        fee_amount = executed_qty * actual_fill * Decimal(str(settings.TRADING_FEE_PCT))

        return ExecutedTrade(
            proposal=trade,
            executed_price=actual_fill,
            executed_quantity=executed_qty,
            order_id=str(order_id),
            status=status_flag,
            timestamp=state["timestamp"],
            fee_paid=fee_amount,
            pnl=Decimal("0"),
        )
