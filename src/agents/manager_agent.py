"""Manager Agent — the brain of the AlphaCore trading system.

Reads ML predictions and sentiment, ranks signals by strength,
generates trade proposals, and delegates them to the Risk Agent.
This is the entry point of the LangGraph agent pipeline.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.agents.agent_state import AgentState, ProposedTrade, Signal
from src.models.predictor import Predictor
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_TRADING_PAUSED_FLAG = Path("data_cache/.trading_paused")

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

        from src.data.multi_source_news import MultiSourceNewsClient
        news_client = MultiSourceNewsClient()
        for pair in list(state["pipeline_data"].keys()):
            fresh = news_client.fetch_headlines(pair, limit_per_source=15)
            if fresh:
                state["pipeline_data"][pair]["news"] = fresh

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
                regime_label=str(vol_regime.get("regime_label", "LOW_VOL")),
                fear_greed_value=fng_value,
                timestamp=state["timestamp"],
            )
            signals.append(signal)

        signals.sort(key=lambda s: abs(s.sentiment_score), reverse=True)
        top_signals = signals[:3]

        _logger.info(
            "Top %d signals: %s",
            len(top_signals),
            [f"{s.symbol}(sentiment={s.sentiment_score:.4f})" for s in top_signals],
        )

        portfolio_value = float(
            state["portfolio_summary"].get("total_value", settings.PORTFOLIO_INITIAL_CAPITAL)
        )

        # OPTION A LOGIC: Sentiment-primary decision making.
        # Regression LSTM direction is NOT used for trading decisions —
        # only logged for research comparison.
        proposed_trades: list[ProposedTrade] = []

        trading_paused = _TRADING_PAUSED_FLAG.exists()
        if trading_paused:
            _logger.info(
                "Trading PAUSED — flag file %s exists. "
                "Skipping all new entry proposals. Auto-exit trades "
                "(stop-loss / take-profit) will still be handled by PortfolioMonitor.",
                _TRADING_PAUSED_FLAG,
            )

        if not trading_paused:
            exiting_symbols = {
                t.symbol for t in state.get("proposed_trades", [])
                if getattr(t, "is_auto_exit", False)
            }
            if exiting_symbols:
                _logger.info(
                    "Auto-exit in progress for %s — skipping new proposals for these symbols",
                    exiting_symbols,
                )

            for sig in top_signals:
                if abs(sig.sentiment_score) < MIN_SENTIMENT_STRENGTH:
                    _logger.info(
                        "%s skipped — no strong sentiment signal (%.2f)",
                        sig.symbol, sig.sentiment_score,
                    )
                    continue
                if sig.symbol in exiting_symbols:
                    _logger.info(
                        "%s skipped — auto-exit already in progress this cycle",
                        sig.symbol,
                    )
                    continue
                trade = self._signal_to_trade(sig, portfolio_value, state)
                if trade is not None:
                    proposed_trades.append(trade)

        state["signals"] = signals
        # Preserve any auto-exit trades from monitor_exits node
        existing_auto_exits = [
            t for t in state.get("proposed_trades", [])
            if getattr(t, "is_auto_exit", False)
        ]
        state["proposed_trades"] = existing_auto_exits + proposed_trades
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
        """Convert a ranked signal into a ProposedTrade using sentiment-primary logic.

        Side is determined purely by sentiment_score direction.
        Regression LSTM outputs (predicted_return, direction, confidence)
        are ignored for the trade decision — they remain in state["signals"]
        for research comparison only.

        Args:
            sig: The ranked signal.
            portfolio_value: Current portfolio value in USDT.
            state: Full agent state (for price lookups).

        Returns:
            A ProposedTrade or None if the signal is skipped.
        """
        sentiment_score = sig.sentiment_score

        if sentiment_score > 0.30:
            side = "BUY"
        elif sentiment_score < -0.30:
            side = "SELL"
        else:
            _logger.info("Skipping %s: sentiment=%.2f — no clear direction", sig.symbol, sentiment_score)
            return None

        holdings_raw = state.get("portfolio_summary", {}).get("holdings", {})
        holdings_symbols: set[str] = set()
        if isinstance(holdings_raw, dict):
            holdings_symbols = {
                sym for sym, hdata in holdings_raw.items()
                if isinstance(hdata, dict) and float(hdata.get("quantity", 0)) > 0
            }

        if side == "BUY" and sig.symbol in holdings_symbols:
            _logger.info(
                "Skipping %s BUY — position already held (%.2f). Preventing duplicate.",
                sig.symbol,
                float(holdings_raw[sig.symbol].get("quantity", 0)),
            )
            return None

        if side == "SELL" and sig.symbol not in holdings_symbols:
            _logger.info(
                "Skipping %s SELL — no existing holding. Spot trading cannot short.",
                sig.symbol,
            )
            return None

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
        pct_quantity = (max_position * Decimal(str(portfolio_value)) / entry_price).quantize(Decimal("0.00001"))

        max_usd_qty = (settings.MAX_POSITION_SIZE_USD / entry_price).quantize(Decimal("0.00001"))
        base_quantity = min(pct_quantity, max_usd_qty)

        _logger.info(
            "%s base quantity: pct=%s, usd_cap=%s, final=%s",
            sig.symbol, pct_quantity, max_usd_qty, base_quantity,
        )

        vol_regime = getattr(sig, "vol_regime", 0)
        if vol_regime == 1:
            final_quantity = (base_quantity * Decimal("0.5")).quantize(Decimal("0.00001"))
            vol_tag = " [HIGH VOL: position halved]"
            _logger.info(
                "%s high volatility regime — position halved to %s",
                sig.symbol, final_quantity,
            )
        else:
            final_quantity = base_quantity
            vol_tag = " [LOW VOL: full size]"

        sl_pct = Decimal(str(settings.STOP_LOSS_PCT))
        stop_loss = entry_price * (Decimal("1") - sl_pct)
        take_profit = entry_price * (Decimal("1") + sl_pct * Decimal("2"))

        reasoning = (
            f"Sentiment-driven {side}: score={sentiment_score:.2f}, "
            f"vol_regime={sig.regime_label}, fear_greed={sig.fear_greed_value}"
        )
        reasoning += vol_tag

        trade = ProposedTrade(
            symbol=sig.symbol,
            side=side,
            quantity=final_quantity,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            signal_confidence=round(abs(sentiment_score), 4),
            reasoning=reasoning,
        )
        return trade
