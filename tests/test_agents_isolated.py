"""Per-agent isolation tests — 11 tests across all four agents.

Every test runs in <1 s with *zero* network or database calls.
``FakeBinanceClient`` replaces ``BinanceClient`` wherever needed and
``Predictor`` / ``send_alert`` are mocked so the tests exercise purely
the agent decision logic.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.mock_binance import FakeBinanceClient
from tests.fixtures.scenarios import (
    clean_state_no_positions,
    state_with_open_position,
    state_with_pending_auto_exit,
)
from src.agents.agent_state import AgentState, ExecutedTrade, ProposedTrade, Signal


# =========================================================================
# Manager Agent  (3 tests)
# =========================================================================


@patch("src.agents.manager_agent.Predictor")
class TestManagerAgent:
    """Manager Agent isolation tests — signal ranking, USD cap, auto-exit preservation."""

    def _make_signals(self, sentiment_score: float, symbol: str = "BTC/USDT") -> dict:
        """Build a ``run_all()`` return value with one signal."""
        return {
            symbol: {
                "price": {"symbol": symbol, "predicted_return": 0.5, "direction": "up", "confidence": 0.55},
                "vol_regime": {"symbol": symbol, "vol_regime": 0, "regime_label": "LOW_VOL", "vol_regime_prob": 0.3},
                "sentiment": {
                    "symbol": symbol, "composite_score": sentiment_score,
                    "positive": max(sentiment_score, 0), "negative": max(-sentiment_score, 0),
                    "neutral": 1 - abs(sentiment_score),
                    "avg_headline_age_hours": 1.0,
                },
                "combined_confidence": abs(sentiment_score) * 0.3 + 0.25,
            },
        }

    def _make_state(self, pipeline_data: dict | None = None) -> AgentState:
        s = clean_state_no_positions()
        if pipeline_data:
            s["pipeline_data"] = pipeline_data
        return s

    def test_manager_skips_symbol_below_sentiment_threshold(self, mock_predictor: MagicMock) -> None:
        mock_predictor.return_value.run_all.return_value = self._make_signals(sentiment_score=0.15)

        from src.agents.manager_agent import ManagerAgent

        state = self._make_state()
        result = ManagerAgent().run(state)

        assert len(result["proposed_trades"]) == 0, "no trade should be proposed below 0.30 threshold"

    def test_manager_applies_usd_position_cap(self, mock_predictor: MagicMock) -> None:
        mock_predictor.return_value.run_all.return_value = self._make_signals(sentiment_score=0.45)

        from src.agents.manager_agent import ManagerAgent

        state = self._make_state({
            "BTC/USDT": {"current_price": "100.00", "fear_greed": {"value": 50}},
        })
        # portfolio_value is 10000 (from clean_state), pct_qty = 0.05*10000/100 = 5.0
        # usd_cap = 500/100 = 5.0 — equal, so we need a larger portfolio to show cap at work
        state["portfolio_summary"]["total_value"] = 12_000.0

        result = ManagerAgent().run(state)

        assert len(result["proposed_trades"]) == 1
        trade = result["proposed_trades"][0]
        total_cost = trade.quantity * trade.entry_price
        assert total_cost <= Decimal("500"), f"USD cap violated: {trade.quantity} * {trade.entry_price} = {total_cost}"

    def test_manager_preserves_auto_exit_trades(self, mock_predictor: MagicMock) -> None:
        mock_predictor.return_value.run_all.return_value = self._make_signals(sentiment_score=0.45)

        from src.agents.manager_agent import ManagerAgent

        state = self._make_state({
            "BTC/USDT": {"current_price": "100.00", "fear_greed": {"value": 50}},
        })
        state["proposed_trades"] = [
            ProposedTrade(
                symbol="SOL/USDT", side="SELL", quantity=Decimal("1.0"),
                entry_price=Decimal("80.00"), stop_loss_price=Decimal("75.00"),
                take_profit_price=Decimal("90.00"), signal_confidence=1.0,
                reasoning="AUTO-EXIT: stop loss triggered",
                is_sentiment_driven=False, is_auto_exit=True,
            ),
        ]

        result = ManagerAgent().run(state)

        auto_exits = [t for t in result["proposed_trades"] if getattr(t, "is_auto_exit", False)]
        assert len(auto_exits) == 1, "auto-exit trade was overwritten"
        assert auto_exits[0].symbol == "SOL/USDT"
        assert auto_exits[0].reasoning.startswith("AUTO-EXIT")


# =========================================================================
# Risk Agent  (4 tests)
# =========================================================================


@patch("src.agents.risk_agent.send_alert")
class TestRiskAgent:
    """Risk Agent isolation tests — SELL-without-holding, auto-exit bypass, concentration, correlation."""

    def test_risk_rejects_sell_with_no_holding(self, mock_send_alert: MagicMock) -> None:
        from src.agents.risk_agent import RiskAgent

        state = clean_state_no_positions()
        state["proposed_trades"] = [
            ProposedTrade(
                symbol="BTC/USDT", side="SELL", quantity=Decimal("0.0001"),
                entry_price=Decimal("100"), stop_loss_price=Decimal("90"),
                take_profit_price=Decimal("110"), signal_confidence=0.9,
                reasoning="test SELL without holding",
            ),
        ]

        result = RiskAgent().run(state)

        assert len(result["approved_trades"]) == 0
        reasons = result["risk_report"].get("rejection_reasons", [])
        assert any("no existing holding" in r.get("reason", "").lower() or "no position" in r.get("reason", "").lower() for r in reasons)

    def test_risk_bypasses_checks_for_auto_exit(self, mock_send_alert: MagicMock) -> None:
        from src.agents.risk_agent import RiskAgent

        state = clean_state_no_positions()
        state["proposed_trades"] = [
            ProposedTrade(
                symbol="BTC/USDT", side="SELL", quantity=Decimal("0.01"),
                entry_price=Decimal("60000"), stop_loss_price=Decimal("58000"),
                take_profit_price=Decimal("65000"), signal_confidence=1.0,
                reasoning="AUTO-EXIT", is_sentiment_driven=False, is_auto_exit=True,
            ),
        ]

        result = RiskAgent().run(state)

        assert len(result["approved_trades"]) == 1
        assert result["approved_trades"][0].is_auto_exit

    def test_risk_rejects_over_concentration(self, mock_send_alert: MagicMock) -> None:
        from src.agents.risk_agent import RiskAgent

        state = clean_state_no_positions()
        state["portfolio_summary"]["total_value"] = 10_000.0
        state["portfolio_summary"]["holdings"] = {
            "BTC/USDT": {"value": 2000.0},  # 20% — any add pushes over limit
        }
        state["portfolio_summary"]["positions"] = []
        state["proposed_trades"] = [
            ProposedTrade(
                symbol="BTC/USDT", side="BUY", quantity=Decimal("0.0001"),
                entry_price=Decimal("1000"), stop_loss_price=Decimal("900"),
                take_profit_price=Decimal("1200"), signal_confidence=0.8,
                reasoning="over-concentration test",
            ),
        ]

        result = RiskAgent().run(state)

        assert len(result["approved_trades"]) == 0
        reasons = result["risk_report"].get("rejection_reasons", [])
        assert any("concentration" in r.get("reason", "").lower() for r in reasons)

    def test_risk_correlation_limit(self, mock_send_alert: MagicMock) -> None:
        from src.agents.risk_agent import RiskAgent

        state = clean_state_no_positions()
        holdings: dict[str, float] = {
            "BTC/USDT": 2000.0,
            "ETH/USDT": 1500.0,
            "SOL/USDT": 1000.0,
        }
        state["portfolio_summary"]["holdings"] = holdings
        state["portfolio_summary"]["total_value"] = 10000.0

        symbols = ["ADA/USDT", "BNB/USDT", "LINK/USDT", "DOT/USDT"]
        state["proposed_trades"] = [
            ProposedTrade(
                symbol=sym, side="BUY", quantity=Decimal("1"),
                entry_price=Decimal("10"), stop_loss_price=Decimal("9"),
                take_profit_price=Decimal("12"), signal_confidence=0.6,
                reasoning="correlation test",
            )
            for sym in symbols
        ]

        result = RiskAgent().run(state)

        rejected = result["risk_report"].get("rejection_reasons", [])
        assert len(rejected) >= 1
        assert any("correlation" in r.get("reason", "").lower() for r in rejected)
        assert result["risk_report"]["correlation_rejections"] >= 1


# =========================================================================
# Execution Agent  (2 tests)
# =========================================================================


class TestExecutionAgent:
    """Execution Agent isolation tests — LOT_SIZE rounding and MIN_NOTIONAL rejection."""

    # _round_down_to_step is a module-level function; no patch needed
    def test_execution_lot_size_rounding(self) -> None:
        from src.agents.execution_agent import _round_down_to_step

        result = _round_down_to_step(Decimal("0.14378"), Decimal("0.0001"))
        assert result == Decimal("0.1437")

    @patch("src.agents.execution_agent.BinanceClient")
    def test_execution_rejects_below_min_notional(self, mock_binance_cls: MagicMock) -> None:
        fake = FakeBinanceClient()
        fake._prices["ADA/USDT"] = Decimal("0.16")
        fake._filters["ADA/USDT"] = {
            "lot_size": {"stepSize": Decimal("0.1")},
            "min_notional": {"minNotional": Decimal("10")},
        }
        mock_binance_cls.return_value = fake

        from src.agents.execution_agent import ExecutionAgent

        agent = ExecutionAgent()
        assert agent.binance is fake

        trade = ProposedTrade(
            symbol="ADA/USDT", side="BUY", quantity=Decimal("1.0"),
            entry_price=Decimal("0.16"), stop_loss_price=Decimal("0.14"),
            take_profit_price=Decimal("0.20"), signal_confidence=0.8,
            reasoning="min_notional test",
        )
        state = clean_state_no_positions()
        state["approved_trades"] = [trade]
        # Ensure slippage doesn't push notional above min_notional
        state["pipeline_data"]["ADA/USDT"] = {"current_price": 0.16}

        result = agent.run(state)

        assert len(result["executed_trades"]) == 1
        et = result["executed_trades"][0]
        assert et.status == "REJECTED_LOT_SIZE"
        assert et.executed_quantity == Decimal("0")
        assert fake._order_call_count == 0, "create_order should not have been called"


# =========================================================================
# Portfolio Monitor  (2 tests)
# =========================================================================


@patch("src.agents.portfolio_monitor.BinanceClient")
class TestPortfolioMonitor:
    """Portfolio Monitor isolation tests — SL breach detection and safe-price pass."""

    def test_monitor_detects_stop_loss_breach(self, mock_binance_cls: MagicMock) -> None:
        fake = FakeBinanceClient()
        fake._prices["SOL/USDT"] = Decimal("70.00")  # below stop_loss_price = 75
        mock_binance_cls.return_value = fake

        from src.agents.portfolio_monitor import PortfolioMonitor

        state = state_with_pending_auto_exit(
            symbol="SOL/USDT", quantity=Decimal("1.601"),
            stop_loss_price=Decimal("75.00"),
        )

        result = PortfolioMonitor().check_exits_only(state)

        auto_exits = [t for t in result.get("proposed_trades", []) if getattr(t, "is_auto_exit", False)]
        assert len(auto_exits) == 1
        assert auto_exits[0].symbol == "SOL/USDT"
        assert auto_exits[0].side == "SELL"

    def test_monitor_no_exit_when_price_safe(self, mock_binance_cls: MagicMock) -> None:
        fake = FakeBinanceClient()
        fake._prices["SOL/USDT"] = Decimal("80.00")  # above stop_loss_price = 75 — safe
        mock_binance_cls.return_value = fake

        from src.agents.portfolio_monitor import PortfolioMonitor

        state = state_with_pending_auto_exit(
            symbol="SOL/USDT", quantity=Decimal("1.601"),
            stop_loss_price=Decimal("75.00"),
        )

        result = PortfolioMonitor().check_exits_only(state)

        auto_exits = [t for t in result.get("proposed_trades", []) if getattr(t, "is_auto_exit", False)]
        assert len(auto_exits) == 0, "no auto-exit should be generated when price is safe"
