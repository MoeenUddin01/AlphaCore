"""Risk Agent — screens trade proposals through multiple risk checks.

Enforces position sizing, portfolio concentration, total exposure,
drawdown circuit breakers, and duplicate position prevention.
Only trades that pass all checks proceed to the Execution Agent.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.agents.agent_state import AgentState, ProposedTrade
from src.utils.config import settings
from src.utils.helpers import send_alert
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class RiskAgent:
    """Risk management agent — validates and filters trade proposals."""

    def run(self, state: AgentState) -> AgentState:
        """Screen every proposed trade through five risk checks.

        Args:
            state: Current LangGraph agent state with ``proposed_trades``.

        Returns:
            Updated state with ``approved_trades`` and ``risk_report``.
        """
        _logger.info("RiskAgent run — cycle %s", state["cycle_id"])

        portfolio: dict[str, Any] = state.get("portfolio_summary", {})
        total_value = float(portfolio.get("total_value", settings.PORTFOLIO_INITIAL_CAPITAL))
        peak_value = float(portfolio.get("peak_value", total_value))

        # holdings is populated by get_current_portfolio_state() in jobs.py
        # and keyed by full pair symbol (e.g. "ADA/USDT").
        holdings_raw: Any = portfolio.get("holdings", {})
        holdings: dict[str, float] = {}
        existing_symbols: set[str] = set()

        if isinstance(holdings_raw, dict):
            for sym, hdata in holdings_raw.items():
                if isinstance(hdata, dict):
                    holdings[sym] = float(hdata.get("value", 0))
                else:
                    holdings[sym] = float(hdata)
                existing_symbols.add(sym)

        # Same-cycle trades — prevent BUY+SELL same symbol within one cycle
        for et in state.get("executed_trades", []):
            existing_symbols.add(et.proposal.symbol)

        _logger.info(
            "RiskAgent sees %d existing holdings: %s",
            len(holdings),
            {s: f"${v:.2f}" for s, v in holdings.items()},
        )

        approved: list[ProposedTrade] = []
        auto_exits_approved: int = 0
        rejection_reasons: list[dict[str, Any]] = []
        correlation_adjustments: int = 0
        correlation_rejections: int = 0

        drawdown_pct = ((peak_value - total_value) / peak_value * 100) if peak_value > 0 else 0.0
        circuit_breaker = drawdown_pct > 15.0

        if drawdown_pct > 10.0:
            send_alert(
                f"Drawdown {drawdown_pct:.2f}% — {'CIRCUIT BREAKER ACTIVE' if circuit_breaker else 'exceeds 10% threshold'} "
                f"(peak={peak_value:.2f}, current={total_value:.2f})",
                level="error" if circuit_breaker else "warning",
            )

        if circuit_breaker:
            _logger.warning(
                "Circuit breaker ACTIVE — drawdown %.2f%% exceeds 15%% threshold. "
                "All trades rejected.",
                drawdown_pct,
            )

        for trade in state.get("proposed_trades", []):
            if getattr(trade, "is_auto_exit", False):
                approved.append(trade)
                auto_exits_approved += 1
                _logger.info(
                    "Auto-exit approved %s %s (qty=%s) — bypassing risk checks",
                    trade.side, trade.symbol, trade.quantity,
                )
                continue

            if circuit_breaker:
                rejection_reasons.append({
                    "symbol": trade.symbol,
                    "reason": f"Circuit breaker active: drawdown {drawdown_pct:.2f}% > 15%",
                })
                _logger.warning("Rejected %s (circuit breaker)", trade.symbol)
                continue

            trade_value = float(trade.quantity * trade.entry_price)

            if trade_value > settings.MAX_POSITION_SIZE_PCT * total_value:
                rejection_reasons.append({
                    "symbol": trade.symbol,
                    "reason": (
                        f"Position size ${trade_value:.2f} exceeds "
                        f"max {settings.MAX_POSITION_SIZE_PCT * 100:.0f}% "
                        f"of portfolio (${settings.MAX_POSITION_SIZE_PCT * total_value:.2f})"
                    ),
                })
                _logger.warning("Rejected %s (position size limit)", trade.symbol)
                continue

            current_coin_value = holdings.get(trade.symbol, 0.0)
            new_coin_value = current_coin_value + trade_value
            coin_pct = new_coin_value / total_value * 100
            if coin_pct > 20.0:
                rejection_reasons.append({
                    "symbol": trade.symbol,
                    "reason": (
                        f"Portfolio concentration {coin_pct:.2f}% exceeds 20% limit "
                        f"(current ${current_coin_value:.2f} + proposed ${trade_value:.2f})"
                    ),
                })
                _logger.warning("Rejected %s (concentration %.2f%%)", trade.symbol, coin_pct)
                continue

            existing_exposure = sum(
                float(et.proposal.quantity * et.proposal.entry_price)
                for et in state.get("executed_trades", [])
            )
            new_exposure = existing_exposure + trade_value
            exposure_pct = new_exposure / total_value * 100
            if exposure_pct > 80.0:
                rejection_reasons.append({
                    "symbol": trade.symbol,
                    "reason": (
                        f"Total exposure {exposure_pct:.2f}% exceeds 80% limit "
                        f"(existing ${existing_exposure:.2f} + proposed ${trade_value:.2f})"
                    ),
                })
                _logger.warning("Rejected %s (exposure %.2f%%)", trade.symbol, exposure_pct)
                continue

            if trade.side == "BUY" and trade.symbol in existing_symbols:
                rejection_reasons.append({
                    "symbol": trade.symbol,
                    "reason": "Duplicate BUY position already exists for this symbol",
                })
                _logger.warning("Rejected %s (duplicate position)", trade.symbol)
                continue

            if trade.side == "SELL" and trade.symbol not in existing_symbols:
                rejection_reasons.append({
                    "symbol": trade.symbol,
                    "reason": "Cannot SELL — no existing holding for this symbol (spot trading)",
                })
                _logger.warning("Rejected %s (SELL without holding)", trade.symbol)
                continue

            # Holdings from state are all long positions.
            # For a BUY proposal, every existing holding is a same-direction position.
            # For a SELL proposal, existing holdings are opposite direction.
            existing_same_direction = len(holdings) if trade.side == "BUY" else 0
            same_direction_count = existing_same_direction + sum(
                1 for t in approved if t.side == trade.side
            )
            if same_direction_count > 3:
                rejection_reasons.append({
                    "symbol": trade.symbol,
                    "reason": (
                        f"Correlation limit: too many same-direction crypto positions "
                        f"open simultaneously ({same_direction_count} total)"
                    ),
                })
                correlation_rejections += 1
                _logger.warning("Rejected %s (correlation limit — %d same-direction)", trade.symbol, same_direction_count)
                continue
            if same_direction_count > 2:
                original_qty = trade.quantity
                trade.quantity = trade.quantity / Decimal("2")
                correlation_adjustments += 1
                _logger.info(
                    "%s quantity halved — %s -> %s (%d other same-direction positions already open, "
                    "correlated sentiment risk)",
                    trade.symbol, original_qty, trade.quantity, same_direction_count,
                )

            approved.append(trade)
            _logger.info("Approved %s %s (qty=%s, entry=%s)", trade.side, trade.symbol, trade.quantity, trade.entry_price)

        state["approved_trades"] = approved

        open_value = sum(
            float(et.proposal.quantity * et.proposal.entry_price)
            for et in state.get("executed_trades", [])
        )
        approved_value = sum(float(t.quantity * t.entry_price) for t in approved)
        portfolio_exposure_pct = ((open_value + approved_value) / total_value * 100) if total_value > 0 else 0.0

        state["risk_report"] = {
            "total_proposed": len(state.get("proposed_trades", [])),
            "total_approved": len(approved),
            "total_rejected": len(rejection_reasons),
            "auto_exits_approved": auto_exits_approved,
            "correlation_adjustments": correlation_adjustments,
            "correlation_rejections": correlation_rejections,
            "rejection_reasons": rejection_reasons,
            "portfolio_exposure_pct": round(portfolio_exposure_pct, 2),
            "drawdown_pct": round(drawdown_pct, 2),
        }

        state["cycle_log"].append(
            f"[{datetime.utcnow().isoformat()}] RiskAgent: "
            f"{state['risk_report']['total_approved']}/{state['risk_report']['total_proposed']} trades approved "
            f"({auto_exits_approved} auto-exits), "
            f"exposure {portfolio_exposure_pct:.1f}%, drawdown {drawdown_pct:.1f}%"
        )
        _logger.info(
            "RiskAgent done — %d/%d approved (%d auto-exits), exposure=%.1f%%, drawdown=%.1f%%",
            len(approved),
            len(state.get("proposed_trades", [])),
            auto_exits_approved,
            portfolio_exposure_pct,
            drawdown_pct,
        )
        return state
