"""Manager Agent — the brain of the AlphaCore trading system.

Reads ML predictions and sentiment, ranks signals by strength,
generates trade proposals, and delegates them to the Risk Agent.
This is the entry point of the LangGraph agent pipeline.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.agents.agent_state import AgentState, ProposedTrade, Signal
from src.models.predictor import Predictor
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance
from src.utils.logger import get_logger

_logger = get_logger(__name__)

MIN_CONFIDENCE_THRESHOLD = 0.55
MIN_SENTIMENT_STRENGTH = 0.30


class ManagerAgent:
    """Strategy and delegation agent — generates ranked trade proposals."""

    def __init__(self) -> None:
        _logger.info("Initialising ManagerAgent")
        self.predictor = Predictor()

    def run(self, state: AgentState) -> AgentState:
        """Execute the Manager Agent node in the LangGraph pipeline.

        Steps:
            1. Run all predictions via Predictor.
            2. Convert raw predictions to typed Signal objects.
            3. Rank signals by composite score and take top 3.
            4. Generate ProposedTrade for each viable signal.
            5. Append summary to cycle log.

        Args:
            state: Current LangGraph agent state.

        Returns:
            Updated state with ``signals`` and ``proposed_trades`` populated.
        """
        _logger.info("ManagerAgent run — cycle %s", state["cycle_id"])

        raw_signals = self.predictor.run_all(state["pipeline_data"])

        signals: list[Signal] = []
        for pair, preds in raw_signals.items():
            price = preds["price"]
            sentiment = preds["sentiment"]

            fng_data = state["pipeline_data"].get(pair, {}).get("fear_greed", {})
            fng_value = int(fng_data.get("value", 50))

            pos = sentiment.get("positive", 0.0)
            neg = sentiment.get("negative", 0.0)
            neutral = sentiment.get("neutral", 1.0)

            if pos >= neg and pos >= neutral:
                sentiment_label = "positive"
            elif neg >= pos and neg >= neutral:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"

            vol_regime = preds.get("vol_regime", {})
            signal = Signal(
                symbol=pair,
                predicted_return=float(price.get("predicted_return", 0.0)),
                direction=str(price.get("direction", "neutral")),
                confidence=float(price.get("confidence", 0.0)),
                sentiment_score=float(sentiment.get("composite_score", 0.0)),
                sentiment_label=sentiment_label,
                vol_regime=int(vol_regime.get("vol_regime", 0)),
                fear_greed_value=fng_value,
                timestamp=state["timestamp"],
            )
            signals.append(signal)

        def _rank(s: Signal) -> float:
            return (s.confidence * 0.6) + (abs(s.sentiment_score) * 0.4)

        signals.sort(key=_rank, reverse=True)
        top_signals = signals[:3]

        _logger.info(
            "Top %d signals: %s",
            len(top_signals),
            [f"{s.symbol}({_rank(s):.4f})" for s in top_signals],
        )

        portfolio_value = float(
            state["portfolio_summary"].get("total_value", settings.PORTFOLIO_INITIAL_CAPITAL)
        )

        proposed_trades: list[ProposedTrade] = []
        for sig in top_signals:
            if sig.confidence < MIN_CONFIDENCE_THRESHOLD:
                _logger.info(
                    "%s skipped — confidence %.2f below threshold %.2f",
                    sig.symbol, sig.confidence, MIN_CONFIDENCE_THRESHOLD,
                )
                continue
            if abs(sig.sentiment_score) < MIN_SENTIMENT_STRENGTH:
                _logger.info(
                    "%s skipped — sentiment strength %.2f below threshold %.2f",
                    sig.symbol, abs(sig.sentiment_score), MIN_SENTIMENT_STRENGTH,
                )
                continue
            trade = self._signal_to_trade(sig, portfolio_value, state)
            if trade is not None:
                proposed_trades.append(trade)

        state["signals"] = signals
        state["proposed_trades"] = proposed_trades
        state["cycle_log"].append(
            f"[{datetime.utcnow().isoformat()}] ManagerAgent: "
            f"generated {len(signals)} signals, "
            f"{len(proposed_trades)} trades proposed"
        )
        _logger.info("ManagerAgent done — %d trades proposed", len(proposed_trades))
        return state

    def _signal_to_trade(
        self,
        sig: Signal,
        portfolio_value: float,
        state: AgentState,
    ) -> ProposedTrade | None:
        """Convert a ranked signal into a ProposedTrade if viable.

        Args:
            sig: The ranked signal.
            portfolio_value: Current portfolio value in USDT.
            state: Full agent state (for price lookups).

        Returns:
            A ProposedTrade or None if the signal is skipped.
        """
        direction = sig.direction
        sentiment_score = sig.sentiment_score

        if direction == "up" and sentiment_score <= 0:
            _logger.info("Skipping %s: direction=up but sentiment_score=%.4f", sig.symbol, sentiment_score)
            return None
        if direction == "down" and sentiment_score >= 0:
            _logger.info("Skipping %s: direction=down but sentiment_score=%.4f", sig.symbol, sentiment_score)
            return None
        if direction == "neutral":
            _logger.info("Skipping %s: direction=neutral", sig.symbol)
            return None

        side = "BUY" if direction == "up" else "SELL"

        pair_data = state["pipeline_data"].get(sig.symbol, {})
        price_data = pair_data.get("current_price", None)
        if price_data is not None:
            try:
                entry_price = Decimal(str(price_data))
            except (ValueError, TypeError):
                entry_price = Decimal("0")
        else:
            entry_price = Decimal("0")

        if entry_price <= Decimal("0"):
            _logger.warning("Skipping %s: invalid entry price %s", sig.symbol, entry_price)
            return None

        max_position = Decimal(str(settings.MAX_POSITION_SIZE_PCT))
        position_size = max_position * Decimal(str(portfolio_value))
        quantity = (position_size / entry_price).quantize(Decimal("0.00001"))

        vol_regime = getattr(sig, "vol_regime", 0)
        if vol_regime == 1:
            quantity = (quantity / Decimal("2")).quantize(Decimal("0.00001"))
            _logger.info(
                "%s high volatility regime — position halved to %s",
                sig.symbol, quantity,
            )

        score = (sig.confidence * 0.6) + (abs(sig.sentiment_score) * 0.4)

        sl_pct = Decimal(str(settings.STOP_LOSS_PCT))
        stop_loss = entry_price * (Decimal("1") - sl_pct)
        take_profit = entry_price * (Decimal("1") + sl_pct * Decimal("2"))

        reasoning = (
            f"Signal score={score:.4f}, direction={direction}, "
            f"confidence={sig.confidence:.4f}, sentiment={sig.sentiment_score:.4f}"
        )
        if vol_regime == 1:
            reasoning += " [HIGH VOL: position halved]"

        trade = ProposedTrade(
            symbol=sig.symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            signal_confidence=sig.confidence,
            reasoning=reasoning,
        )
        return trade
