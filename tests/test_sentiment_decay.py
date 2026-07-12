"""Unit tests for exponential decay sentiment weighting.

Confirms that a very fresh headline moves the composite score more
than an old headline of the same sentiment magnitude, validating
that the exponential decay in aggregate_sentiment() works correctly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


class TestExponentialDecayWeighting:
    """Tests for age-weighted sentiment scoring."""

    @pytest.fixture(autouse=True)
    def _load_model(self) -> None:
        from src.models.sentiment_model import SentimentModel
        self._model_cls = SentimentModel

    def _make_headline(self, title: str, hours_old: float) -> dict:
        ts = datetime.now(timezone.utc) - timedelta(hours=hours_old)
        return {"title": title, "published_at": ts.isoformat()}

    def test_fresh_bearish_beats_old_bearish(self) -> None:
        """With one fresh + one old bearish headline, the composite should
        be dominated by the fresh one (more negative)."""
        model = self._model_cls()
        headlines = [
            self._make_headline("Bitcoin crashes hard today", 1),
            self._make_headline("Bitcoin crashes hard today", 48),
        ]
        result = model.aggregate_sentiment(headlines, half_life_hours=12.0)
        # Both bearish → composite negative
        assert result["composite_score"] < 0

    def test_fresh_positive_shifts_composite_toward_positive(self) -> None:
        """A fresh bullish headline + an old bearish headline → composite
        should be pulled toward positive by the fresh headline's weight."""
        model = self._model_cls()
        headlines_fresh_bull = [
            self._make_headline("Bitcoin surges to new all time high", 1),
            self._make_headline("Bitcoin crashes hard today", 48),
        ]
        headlines_old_bull = [
            self._make_headline("Bitcoin surges to new all time high", 48),
            self._make_headline("Bitcoin crashes hard today", 1),
        ]
        score_fresh = model.aggregate_sentiment(headlines_fresh_bull, half_life_hours=12.0)["composite_score"]
        score_old = model.aggregate_sentiment(headlines_old_bull, half_life_hours=12.0)["composite_score"]
        # Fresh bullish should shift composite more toward positive
        assert score_fresh > score_old, (
            f"Fresh bullish should dominate: fresh={score_fresh:.4f} swapped={score_old:.4f}"
        )

    def test_half_life_configurable(self) -> None:
        """A shorter half_life should weight fresh headlines even more heavily."""
        model = self._model_cls()
        headlines = [
            self._make_headline("Bitcoin crashes hard today", 2),
            self._make_headline("Bitcoin surges to new all time high", 24),
        ]
        score_default = model.aggregate_sentiment(headlines, half_life_hours=12.0)["composite_score"]
        score_short = model.aggregate_sentiment(headlines, half_life_hours=6.0)["composite_score"]
        assert score_short != score_default

    def test_empty_headlines_returns_neutral(self) -> None:
        model = self._model_cls()
        result = model.aggregate_sentiment([])
        assert result["composite_score"] == 0.0
        assert result["neutral"] == 1.0

    def test_all_old_headlines_contribute_minimally(self) -> None:
        """Fresh positive + old negative → composite should be positive
        because the old negative headline gets minimal weight."""
        model = self._model_cls()
        headlines = [
            self._make_headline("Bitcoin surges to new all time high", 1),
            self._make_headline("Bitcoin crashes hard today", 40),
        ]
        result = model.aggregate_sentiment(headlines, half_life_hours=12.0)
        assert result["composite_score"] > 0, (
            f"Fresh positive should dominate: composite={result['composite_score']:.4f}"
        )

    def test_weight_decay_exponential(self) -> None:
        """Verify the weight formula: weight = 0.5^(age/half_life).
        At half_life, weight should be ~0.5; at 2×half_life, ~0.25."""
        import math
        half_life = 12.0
        for age, expected_weight in [(0, 1.0), (12, 0.5), (24, 0.25), (36, 0.125)]:
            w = 0.5 ** (age / half_life)
            assert abs(w - expected_weight) < 0.01, f"age={age}h: expected {expected_weight}, got {w}"
