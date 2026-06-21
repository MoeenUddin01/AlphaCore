"""FinBERT sentiment analysis for crypto news headlines.

Wraps the ProsusAI/finbert model from HuggingFace to score individual
headlines and aggregate sentiment over a batch of news with time-decay
weighting so that fresher headlines contribute more to the composite score.
"""

from datetime import datetime, timezone
from typing import Any

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src.utils.logger import get_logger

_logger = get_logger(__name__)

_LABELS = ["positive", "negative", "neutral"]


class SentimentModel:
    """FinBERT-based sentiment scorer for financial/crypto text."""

    def __init__(self) -> None:
        _logger.info("Loading FinBERT model (ProsusAI/finbert)")
        self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            "ProsusAI/finbert"
        )
        self.model.eval()
        if torch.cuda.is_available():
            try:
                cc = torch.cuda.get_device_capability()
                if cc[0] < 7 or (cc[0] == 7 and cc[1] < 5):
                    _logger.warning(
                        "GPU CC %d.%d < 7.5 — incompatible with PyTorch CUDA build. "
                        "Falling back to CPU.",
                        cc[0], cc[1],
                    )
                    self._device = torch.device("cpu")
                else:
                    self._device = torch.device("cuda")
            except Exception:
                self._device = torch.device("cpu")
        else:
            self._device = torch.device("cpu")
        self.model.to(self._device)
        _logger.info("FinBERT loaded on %s", self._device)

    @property
    def device(self) -> torch.device:
        """Return the device the model is running on (cuda / cpu)."""
        return self._device

    def score_headline(self, headline: str) -> dict[str, Any]:
        """Score a single headline and return label probabilities.

        Args:
            headline: The news headline text.

        Returns:
            Dict with keys ``positive``, ``negative``, ``neutral`` (float)
            and ``sentiment`` (str — the label with highest probability).
        """
        inputs = self.tokenizer(
            headline,
            return_tensors="pt",
            truncation=True,
            padding=True,
        ).to(self._device)

        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = F.softmax(logits, dim=-1).squeeze(0)

        scores = {
            _LABELS[i]: float(probs[i].item())
            for i in range(len(_LABELS))
        }
        scores["sentiment"] = _LABELS[probs.argmax().item()]
        return scores

    def score_headlines(self, headlines: list[str]) -> list[dict[str, Any]]:
        """Score a list of headlines.

        Args:
            headlines: List of headline strings.

        Returns:
            List of dicts as returned by :meth:`score_headline`.
        """
        return [self.score_headline(h) for h in headlines]

    def aggregate_sentiment(self, headline_dicts: list[dict[str, Any]]) -> dict[str, Any]:
        """Score all headlines and return time-decay-weighted sentiment.

        Each headline dict must contain a ``title`` (str) and a
        ``published_at`` (datetime).  Fresher headlines receive higher
        weight via a linear decay over 24 hours (floor 10 %).

        Args:
            headline_dicts: List of dicts with ``title`` and
                ``published_at`` keys. May be empty.

        Returns:
            Dict with weighted ``positive``, ``negative``, ``neutral``
            scores, a ``composite_score`` (``positive - negative``,
            range -1 to +1), and ``avg_headline_age_hours`` (float).
        """
        if not headline_dicts:
            _logger.warning("Empty headline list — returning neutral scores")
            return {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "composite_score": 0.0,
                "avg_headline_age_hours": 0.0,
            }

        titles: list[str] = []
        weights: list[float] = []
        now = datetime.now(timezone.utc)
        total_age = 0.0

        for h in headline_dicts:
            title = h.get("title", "")
            if not title:
                continue
            titles.append(title)

            published = h.get("published_at")
            if isinstance(published, datetime):
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                hours_old = (now - published).total_seconds() / 3600.0
            else:
                hours_old = 24.0

            total_age += hours_old
            weight = max(0.1, 1.0 - (hours_old / 24.0))
            weights.append(weight)

        if not titles:
            _logger.warning("No valid headlines after filtering — returning neutral scores")
            return {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "composite_score": 0.0,
                "avg_headline_age_hours": 0.0,
            }

        scores = self.score_headlines(titles)

        weighted: dict[str, float] = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        total_weight = sum(weights)

        for s, w in zip(scores, weights):
            for key in weighted:
                weighted[key] += s[key] * w

        for key in weighted:
            weighted[key] /= total_weight

        weighted["composite_score"] = weighted["positive"] - weighted["negative"]
        weighted["avg_headline_age_hours"] = round(total_age / len(titles), 2)

        _logger.info(
            "Aggregated sentiment: composite=%.4f avg_age=%.1fh weights=%d",
            weighted["composite_score"],
            weighted["avg_headline_age_hours"],
            len(weights),
        )
        return weighted
