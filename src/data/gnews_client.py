"""GNews API news client — free tier available.

Uses the GNews API to fetch crypto-related headlines.
Base URL: https://gnews.io/api/v4

Free tier available, no credit card required.
"""

from __future__ import annotations

from typing import Any

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_BASE_URL = "https://gnews.io/api/v4"


class GNewsClient:
    """Fetch crypto news from the GNews API."""

    def __init__(self) -> None:
        api_key = settings.GNEWS_API_KEY
        if api_key and "your_" not in api_key:
            self._api_key = api_key
            self._available = True
            _logger.info("GNewsClient initialised with API key")
        else:
            self._api_key = ""
            self._available = False
            _logger.info("GNewsClient disabled (no valid API key)")

    def get_news_for_pair(self, pair: str, limit: int = 15) -> list[dict[str, Any]]:
        """Fetch recent GNews articles relevant to *pair*.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            limit: Maximum number of articles to return.

        Returns:
            List of dicts with keys ``title``, ``published_at``,
            ``source``, ``url``.  Sorted by ``published_at`` descending.
            Empty on failure.
        """
        if not self._available:
            return []

        base = pair.split("/")[0].upper()
        ticker_names = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "BNB": "binance crypto",
            "ADA": "cardano",
        }
        query = ticker_names.get(base, base.lower())

        try:
            articles = self._search(query, limit=min(limit * 2, 30))
        except Exception as exc:
            _logger.error("GNews fetch failed for %s: %s", pair, exc)
            return []

        matched: list[dict[str, Any]] = []
        seen_titles: set[str] = set()

        for article in articles:
            title = (article.get("title") or "").strip()
            if not title or title in seen_titles:
                continue

            source_name = article.get("source", {})
            if isinstance(source_name, dict):
                source_name = source_name.get("name", "GNews")

            matched.append({
                "title": title,
                "published_at": article.get("publishedAt", ""),
                "source": source_name,
                "url": article.get("url", ""),
            })
            seen_titles.add(title)

            if len(matched) >= limit:
                break

        _logger.info("GNews: %d headlines matched %s", len(matched), pair)
        return matched

    def _search(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        """Search GNews by query.

        Args:
            query: Search term.
            limit: Maximum articles to return.

        Returns:
            List of article dicts from the API response.
        """
        url = f"{_BASE_URL}/search"
        params = {
            "q": query,
            "lang": "en",
            "max": min(limit, 10),
            "apikey": self._api_key,
        }

        _logger.info("GNews search: '%s' (limit=%d)", query, limit)
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict):
            return data.get("articles", [])
        return []
