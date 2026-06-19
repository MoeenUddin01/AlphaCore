"""Portfolio Monitor — tracks live P&L, positions, and rebalancing alerts.

Computes portfolio-level metrics including unrealised/realised P&L,
drawdown from peak, and allocation drift detection for rebalancing.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.agents.agent_state import AgentState, ProposedTrade
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
        """Update positions, check auto-exit, compute portfolio metrics.

        Args:
            state: Current LangGraph agent state with ``executed_trades``.

        Returns:
            Updated state with ``portfolio_summary`` populated.
        """
        _logger.info("PortfolioMonitor run — cycle %s", state["cycle_id"])

        state = self.check_exit_conditions(state)

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

    def check_exit_conditions(self, state: AgentState) -> AgentState:
        """Check SL/TP for every open position and generate auto-exit trades.

        Fetches the latest price for each open position and compares it
        against the stop-loss and take-profit prices from the originating
        trade. Triggered exits are appended to ``state["proposed_trades"]``
        with ``is_auto_exit=True`` and bypass the sentiment threshold filter.

        Args:
            state: Current agent state.

        Returns:
            Updated state with any auto-exit trades appended.
        """
        if not self.positions:
            return state

        from src.database.crud import get_open_trade_for_symbol

        auto_exits: list[ProposedTrade] = []

        for symbol in list(self.positions.keys()):
            try:
                current_price = self.binance.get_current_price(symbol)
            except Exception as exc:
                _logger.warning("check_exit: failed to fetch price for %s: %s", symbol, exc)
                continue

            trade_data = get_open_trade_for_symbol(symbol)
            if trade_data is None:
                continue

            entry_price = Decimal(str(trade_data["entry_price"]))
            sl_price = Decimal(str(trade_data["stop_loss_price"]))
            tp_price = Decimal(str(trade_data["take_profit_price"]))
            pos = self.positions[symbol]
            qty = pos["quantity"]

            if qty <= Decimal("0"):
                continue

            hit_sl = current_price <= sl_price
            hit_tp = current_price >= tp_price

            if not hit_sl and not hit_tp:
                continue

            reason = "stop loss" if hit_sl else "take profit"
            pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else Decimal("0")

            auto_exit = ProposedTrade(
                symbol=symbol,
                side="SELL",
                quantity=qty,
                entry_price=entry_price,
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
                signal_confidence=1.0,
                reasoning=f"AUTO-EXIT: {reason} triggered at {float(current_price):.2f}",
                is_sentiment_driven=False,
                is_auto_exit=True,
            )
            auto_exits.append(auto_exit)

            _logger.info(
                "AUTO-EXIT %s — %s triggered. "
                "entry=%.2f exit=%.2f pnl=%.2f%% qty=%s",
                symbol, reason,
                float(entry_price), float(current_price),
                float(pnl_pct), qty,
            )

        if auto_exits:
            current_proposed = state.get("proposed_trades", [])
            state["proposed_trades"] = current_proposed + auto_exits
            state["cycle_log"].append(
                f"[{datetime.utcnow().isoformat()}] PortfolioMonitor: "
                f"{len(auto_exits)} auto-exit trade(s) triggered"
            )
            _logger.info(
                "Added %d auto-exit trade(s) to proposed_trades",
                len(auto_exits),
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
                    pos["total_entry_fees"] += et.fee_paid
                else:
                    self.positions[symbol] = {
                        "quantity": qty,
                        "avg_entry_price": price,
                        "current_price": price,
                        "value": qty * price,
                        "unrealized_pnl": Decimal("0"),
                        "return_pct": Decimal("0"),
                        "total_entry_fees": et.fee_paid,
                    }
                _logger.info("Position added/updated: %s qty=%s avg_entry=%s", symbol, qty, price)

            elif side == "SELL":
                if symbol in self.positions:
                    pos = self.positions[symbol]
                    proportional_entry_fee = (
                        pos["total_entry_fees"] * (qty / pos["quantity"])
                        if pos["quantity"] > 0 else Decimal("0")
                    )
                    exit_fee = et.fee_paid
                    realised = (price - pos["avg_entry_price"]) * qty - proportional_entry_fee - exit_fee
                    self._total_realised_pnl += realised
                    pos["total_entry_fees"] -= proportional_entry_fee
                    pos["quantity"] -= qty
                    _logger.info(
                        "Position reduced: %s qty=%s realised_pnl=%s "
                        "(entry_fee=%s exit_fee=%s)",
                        symbol, qty, realised, proportional_entry_fee, exit_fee,
                    )
                    if pos["quantity"] <= Decimal("0"):
                        del self.positions[symbol]
                        _logger.info("Position fully closed: %s", symbol)
                else:
                    _logger.warning("SELL executed for %s but no open position found", symbol)
