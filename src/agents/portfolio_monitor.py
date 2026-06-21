"""Portfolio Monitor — tracks live P&L, positions, and rebalancing alerts.

Computes portfolio-level metrics including unrealised/realised P&L,
drawdown from peak, and allocation drift detection for rebalancing.
All state is read from the portfolio_summary passed in via the agent
state (populated by get_current_portfolio_state() in jobs.py), making
this agent stateless across cycles.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.agents.agent_state import AgentState, ProposedTrade
from src.data.binance_client import BinanceClient
from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class PortfolioMonitor:
    """Live portfolio tracker — P&L, drawdown, and rebalance triggers."""

    def __init__(self) -> None:
        _logger.info("Initialising PortfolioMonitor")
        self.binance = BinanceClient()

    def check_exits_only(self, state: AgentState) -> AgentState:
        """First pipeline node — detect SL/TP breaches and append exit trades.

        Runs only :meth:`check_exit_conditions` without any P&L or position
        tracking. Auto-exit trades are appended to ``state["proposed_trades"]``
        so they flow through Risk and Execution in the same cycle.

        Args:
            state: Current agent state.

        Returns:
            Updated state with any auto-exit trades appended to proposed_trades.
        """
        _logger.info("MonitorExits node — cycle %s", state["cycle_id"])
        state = self.check_exit_conditions(state)
        state["cycle_log"].append(
            f"[{datetime.utcnow().isoformat()}] MonitorExits: exit checks complete"
        )
        return state

    def run(self, state: AgentState) -> AgentState:
        """Final pipeline node — update positions, compute portfolio metrics.

        Args:
            state: Current LangGraph agent state with ``portfolio_summary``
                (populated by get_current_portfolio_state()) and
                ``executed_trades`` from the current cycle.

        Returns:
            Updated state with ``portfolio_summary`` populated.
        """
        _logger.info("MonitorUpdate node — cycle %s", state["cycle_id"])

        portfolio = state.get("portfolio_summary", {})
        holdings_raw: dict[str, Any] = portfolio.get("holdings", {})
        peak_value = Decimal(str(portfolio.get("peak_value", settings.PORTFOLIO_INITIAL_CAPITAL)))
        total_realised_pnl = Decimal(str(portfolio.get("total_realised_pnl", 0)))

        # Build positions from holdings + current cycle's executed trades
        positions = self._merge_positions(holdings_raw, state.get("executed_trades", []))

        total_position_value = Decimal("0")
        position_details: list[dict[str, Any]] = []
        rebalance_alerts: list[str] = []

        for symbol, pos in positions.items():
            try:
                current_price = self.binance.get_current_price(symbol)
            except Exception as exc:
                _logger.warning("Failed to fetch price for %s: %s", symbol, exc)
                current_price = pos.get("current_price") or pos.get("avg_entry_price", Decimal("0"))
                if not isinstance(current_price, Decimal):
                    current_price = Decimal(str(current_price))

            pos_value = pos["quantity"] * current_price
            avg_entry = pos["avg_entry_price"]
            unrealised_pnl = (current_price - avg_entry) * pos["quantity"] if avg_entry > 0 else Decimal("0")
            return_pct = ((current_price - avg_entry) / avg_entry * 100) if avg_entry > 0 else Decimal("0")

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

        cash = Decimal(str(portfolio.get("total_value", settings.PORTFOLIO_INITIAL_CAPITAL))) - total_position_value
        total_value = total_position_value + cash
        total_unrealised_pnl = sum(Decimal(str(p.get("unrealized_pnl", 0))) for p in position_details)
        total_return_pct = (
            (total_value - Decimal(str(settings.PORTFOLIO_INITIAL_CAPITAL)))
            / Decimal(str(settings.PORTFOLIO_INITIAL_CAPITAL)) * 100
        ) if settings.PORTFOLIO_INITIAL_CAPITAL > 0 else Decimal("0")

        # Add current cycle's realised PnL from SELL trades
        current_realised = self._compute_realised_pnl(state.get("executed_trades", []), holdings_raw)
        total_realised_pnl += current_realised

        if total_value > peak_value:
            peak_value = total_value

        drawdown_pct = (
            (peak_value - total_value) / peak_value * 100
        ) if peak_value > 0 else Decimal("0")

        num_positions = len(positions)
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
            "total_realised_pnl": round(float(total_realised_pnl), 2),
            "return_pct": round(float(total_return_pct), 2),
            "peak_value": round(float(peak_value), 2),
            "drawdown_pct": round(float(drawdown_pct), 2),
            "num_positions": num_positions,
            "positions": position_details,
            "holdings": holdings_raw,
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

        Reads existing positions from ``state["portfolio_summary"]["holdings"]``
        (populated by get_current_portfolio_state()). Triggered exits are
        appended to ``state["proposed_trades"]`` with ``is_auto_exit=True``
        and bypass the sentiment threshold filter in the Manager Agent.

        Args:
            state: Current agent state with ``portfolio_summary["holdings"]``.

        Returns:
            Updated state with any auto-exit trades appended.
        """
        holdings_raw: dict[str, Any] = state.get("portfolio_summary", {}).get("holdings", {})
        if not holdings_raw:
            return state

        auto_exits: list[ProposedTrade] = []

        for symbol, hdata in holdings_raw.items():
            if not isinstance(hdata, dict):
                continue

            try:
                current_price = self.binance.get_current_price(symbol)
            except Exception as exc:
                _logger.warning("check_exit: failed to fetch price for %s: %s", symbol, exc)
                continue

            qty = Decimal(str(hdata.get("quantity", 0)))
            entry_price = Decimal(str(hdata.get("avg_entry_price", 0)))
            sl_price = Decimal(str(hdata.get("stop_loss_price", 0)))
            tp_price = Decimal(str(hdata.get("take_profit_price", 0)))

            if qty <= Decimal("0"):
                continue

            hit_sl = sl_price > Decimal("0") and current_price <= sl_price
            hit_tp = tp_price > Decimal("0") and current_price >= tp_price

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

    def _merge_positions(
        self,
        holdings_raw: dict[str, Any],
        executed_trades: list[Any],
    ) -> dict[str, dict[str, Any]]:
        """Merge existing holdings with current cycle's executed trades.

        Args:
            holdings_raw: Holdings dict from ``portfolio_summary``.
            executed_trades: Trades executed in the current cycle.

        Returns:
            Dict of ``{symbol: {quantity, avg_entry_price, ...}}``.
        """
        positions: dict[str, dict[str, Any]] = {}

        for sym, hdata in holdings_raw.items():
            if isinstance(hdata, dict):
                qty = Decimal(str(hdata.get("quantity", 0)))
                if qty > 0:
                    positions[sym] = {
                        "quantity": qty,
                        "avg_entry_price": Decimal(str(hdata.get("avg_entry_price", 0))),
                        "current_price": Decimal(str(hdata.get("current_price", 0))),
                        "value": qty * Decimal(str(hdata.get("current_price", 0))),
                        "unrealized_pnl": Decimal(str(hdata.get("unrealized_pnl", 0))),
                    }

        for et in executed_trades:
            if et.status != "FILLED":
                continue
            trade = et.proposal
            symbol = trade.symbol
            side = trade.side
            qty = et.executed_quantity
            price = et.executed_price

            if side == "BUY":
                if symbol in positions:
                    pos = positions[symbol]
                    total_qty = pos["quantity"] + qty
                    total_cost = (pos["quantity"] * pos["avg_entry_price"]) + (qty * price)
                    pos["avg_entry_price"] = total_cost / total_qty if total_qty > 0 else price
                    pos["quantity"] = total_qty
                else:
                    positions[symbol] = {
                        "quantity": qty,
                        "avg_entry_price": price,
                        "current_price": price,
                        "value": qty * price,
                        "unrealized_pnl": Decimal("0"),
                    }
                _logger.info("Position added/updated: %s qty=%s avg_entry=%s", symbol, qty, price)

            elif side == "SELL":
                if symbol in positions:
                    pos = positions[symbol]
                    pos["quantity"] -= qty
                    if pos["quantity"] <= Decimal("0"):
                        del positions[symbol]
                        _logger.info("Position fully closed: %s", symbol)
                    else:
                        _logger.info("Position reduced: %s qty=%s", symbol, pos["quantity"])
                else:
                    _logger.warning("SELL executed for %s but no open position found", symbol)

        return positions

    def _compute_realised_pnl(
        self,
        executed_trades: list[Any],
        holdings_raw: dict[str, Any],
    ) -> Decimal:
        """Compute realised P&L from SELL trades in the current cycle.

        Args:
            executed_trades: Trades executed in this cycle.
            holdings_raw: Holdings at the start of the cycle.

        Returns:
            Total realised P&L as a Decimal.
        """
        total = Decimal("0")
        for et in executed_trades:
            if et.status != "FILLED" or et.proposal.side != "SELL":
                continue
            trade = et.proposal
            qty = et.executed_quantity
            price = et.executed_price
            hdata = holdings_raw.get(trade.symbol, {})
            avg_entry = Decimal(str(hdata.get("avg_entry_price", 0))) if isinstance(hdata, dict) else Decimal("0")
            if avg_entry > 0:
                realised = (price - avg_entry) * qty
                total += realised
        return total
