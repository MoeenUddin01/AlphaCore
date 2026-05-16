"""FinBERT sentiment analysis for crypto news headlines.

Wraps the ProsusAI/finbert model from HuggingFace to score individual
headlines and aggregate sentiment over a batch of news.
"""

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
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
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

    def aggregate_sentiment(self, headlines: list[str]) -> dict[str, Any]:
        """Score all headlines and return averaged sentiment.

        Args:
            headlines: List of headline strings. May be empty.

        Returns:
            Dict with averaged ``positive``, ``negative``, ``neutral``
            scores and a ``composite_score`` (``positive - negative``,
            ranging from -1 to +1).
        """
        if not headlines:
            _logger.warning("Empty headline list — returning neutral scores")
            return {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "composite_score": 0.0,
            }

        scores = self.score_headlines(headlines)
        avg: dict[str, float] = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        for s in scores:
            for key in avg:
                avg[key] += s[key]
        n = len(scores)
        for key in avg:
            avg[key] /= n

        avg["composite_score"] = avg["positive"] - avg["negative"]
        return avg
