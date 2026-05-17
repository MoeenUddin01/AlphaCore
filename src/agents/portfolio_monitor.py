"""Portfolio Monitor — tracks live P&L, positions, and rebalancing alerts.

Computes portfolio-level metrics including unrealised/realised P&L,
drawdown from peak, and allocation drift detection for rebalancing.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.agents.agent_state import AgentState
from src.data.binance_client import BinanceClient
from src.utils.config import settings
from src.utils.helpers import to_decimal
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class PortfolioMonitor:
    """Live portfolio tracker — P&L, drawdown, and rebalance triggers."""

    def __init__(self) -> None:
        _logger.info("Initialising PortfolioMonitor")
        self.binance = BinanceClient()
        self.positions: dict[str, dict[str, Any]] = {}
        self.peak_portfolio_value: Decimal = Decimal("0")
        self._total_realised_pnl: Decimal = Decimal("0")
        self._initial_capital: Decimal = settings.PORTFOLIO_INITIAL_CAPITAL

    def run(self, state: AgentState) -> AgentState:
        """Update positions, compute portfolio metrics, and check rebalance.

        Args:
            state: Current LangGraph agent state with ``executed_trades``.

        Returns:
            Updated state with ``portfolio_summary`` populated.
        """
        _logger.info("PortfolioMonitor run — cycle %s", state["cycle_id"])

        self._update_positions(state.get("executed_trades", []))

        total_position_value = Decimal("0")
        position_details: list[dict[str, Any]] = []
        rebalance_alerts: list[str] = []

        for symbol, pos in self.positions.items():
            try:
                current_price = self.binance.get_current_price(symbol)
            except Exception as exc:
                _logger.warning("Failed to fetch price for %s: %s", symbol, exc)
                current_price = pos.get("avg_entry_price", Decimal("0"))

            pos_value = pos["quantity"] * current_price
            avg_entry = pos["avg_entry_price"]
            unrealised_pnl = (current_price - avg_entry) * pos["quantity"] if avg_entry > 0 else Decimal("0")
            return_pct = ((current_price - avg_entry) / avg_entry * 100) if avg_entry > 0 else Decimal("0")

            pos["current_price"] = current_price
            pos["value"] = pos_value
            pos["unrealized_pnl"] = unrealised_pnl
            pos["return_pct"] = return_pct

            total_position_value += pos_value

            position_details.append({
                "symbol": symbol,
                "quantity": float(pos["quantity"]),
                "avg_entry_price": float(avg_entry),
                "current_price": float(current_price),
                "value": float(pos_value),
                "unrealized_pnl": float(unrealised_pnl),
                "return_pct": float(return_pct),
            })

        cash = settings.PORTFOLIO_INITIAL_CAPITAL - total_position_value
        total_value = total_position_value + cash
        total_unrealised_pnl = sum(Decimal(str(p.get("unrealized_pnl", 0))) for p in position_details)
        total_return_pct = (
            (total_value - self._initial_capital) / self._initial_capital * 100
        ) if self._initial_capital > 0 else Decimal("0")

        if total_value > self.peak_portfolio_value:
            self.peak_portfolio_value = total_value

        drawdown_pct = (
            (self.peak_portfolio_value - total_value) / self.peak_portfolio_value * 100
        ) if self.peak_portfolio_value > 0 else Decimal("0")

        num_positions = len(self.positions)
        target_per_position_pct = Decimal("100") / max(num_positions, 1)
        for pos in position_details:
            alloc_pct = Decimal(str(pos["value"])) / total_value * 100 if total_value > 0 else Decimal("0")
            drift = abs(alloc_pct - target_per_position_pct)
            if drift > Decimal("10"):
                alert = (
                    f"{pos['symbol']} allocation {alloc_pct:.1f}% "
                    f"drifted {drift:.1f}% from target {target_per_position_pct:.1f}% — rebalance needed"
                )
                rebalance_alerts.append(alert)
                _logger.warning("Rebalance alert: %s", alert)

        state["portfolio_summary"] = {
            "total_position_value": round(float(total_position_value), 2),
            "cash": round(float(cash), 2),
            "total_value": round(float(total_value), 2),
            "total_unrealized_pnl": round(float(total_unrealised_pnl), 2),
            "total_realised_pnl": round(float(self._total_realised_pnl), 2),
            "return_pct": round(float(total_return_pct), 2),
            "peak_value": round(float(self.peak_portfolio_value), 2),
            "drawdown_pct": round(float(drawdown_pct), 2),
            "num_positions": num_positions,
            "positions": position_details,
            "rebalance_alerts": rebalance_alerts,
        }

        state["cycle_log"].append(
            f"[{datetime.utcnow().isoformat()}] PortfolioMonitor: "
            f"value=${float(total_value):.2f}, "
            f"PnL=${float(total_unrealised_pnl):.2f} unrealised, "
            f"drawdown={float(drawdown_pct):.2f}%, "
            f"{num_positions} position(s)"
        )

        _logger.info(
            "PortfolioMonitor done — value=%.2f, PnL=%.2f, drawdown=%.2f%%, %d position(s)",
            float(total_value),
            float(total_unrealised_pnl),
            float(drawdown_pct),
            num_positions,
        )
        return state

    def _update_positions(self, executed_trades: list[Any]) -> None:
        """Rebuild internal positions dict from executed trades.

        Args:
            executed_trades: List of :class:`ExecutedTrade` from state.
        """
        for et in executed_trades:
            if et.status != "FILLED":
                continue
            trade = et.proposal
            symbol = trade.symbol
            side = trade.side
            qty = et.executed_quantity
            price = et.executed_price

            if side == "BUY":
                if symbol in self.positions:
                    pos = self.positions[symbol]
                    total_qty = pos["quantity"] + qty
                    total_cost = (pos["quantity"] * pos["avg_entry_price"]) + (qty * price)
                    pos["avg_entry_price"] = total_cost / total_qty if total_qty > 0 else price
                    pos["quantity"] = total_qty
                else:
                    self.positions[symbol] = {
                        "quantity": qty,
                        "avg_entry_price": price,
                        "current_price": price,
                        "value": qty * price,
                        "unrealized_pnl": Decimal("0"),
                        "return_pct": Decimal("0"),
                    }
                _logger.info("Position added/updated: %s qty=%s avg_entry=%s", symbol, qty, price)

            elif side == "SELL":
                if symbol in self.positions:
                    pos = self.positions[symbol]
                    realised = (price - pos["avg_entry_price"]) * qty
                    self._total_realised_pnl += realised
                    pos["quantity"] -= qty
                    _logger.info(
                        "Position reduced: %s qty=%s realised_pnl=%s",
                        symbol, qty, realised,
                    )
                    if pos["quantity"] <= Decimal("0"):
                        del self.positions[symbol]
                        _logger.info("Position fully closed: %s", symbol)
                else:
                    _logger.warning("SELL executed for %s but no open position found", symbol)
