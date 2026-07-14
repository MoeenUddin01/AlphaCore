"""Currents API news client — 1,000 free requests/day.

Uses the Currents News API to fetch crypto-related headlines.
Base URL: https://api.currentsapi.services

Free tier: 1,000 requests/day, no credit card.
"""

from __future__ import annotations

from typing import Any

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_BASE_URL = "https://api.currentsapi.services/v1"


class CurrentsClient:
    """Fetch crypto news from the Currents News API."""

    def __init__(self) -> None:
        api_key = settings.CURRENTS_API_KEY
        if api_key and "your_" not in api_key:
            self._api_key = api_key
            self._available = True
            _logger.info("CurrentsClient initialised with API key")
        else:
            self._api_key = ""
            self._available = False
            _logger.info("CurrentsClient disabled (no valid API key)")

    def get_news_for_pair(self, pair: str, limit: int = 15) -> list[dict[str, Any]]:
        """Fetch recent Currents news relevant to *pair*.

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
            "BTC": ["bitcoin", "btc"],
            "ETH": ["ethereum", "eth"],
            "SOL": ["solana", "sol"],
            "BNB": ["binance", "bnb"],
            "ADA": ["cardano", "ada"],
        }
        keywords = ticker_names.get(base, [base.lower()])

        matched: list[dict[str, Any]] = []
        seen_titles: set[str] = set()

        for keyword in keywords:
            if len(matched) >= limit:
                break
            try:
                articles = self._search(keyword, limit=min(limit * 2, 40))
            except Exception as exc:
                _logger.warning("Currents search failed for '%s': %s", keyword, exc)
                continue

            for article in articles:
                title = (article.get("title") or "").strip()
                if not title or title in seen_titles:
                    continue

                matched.append({
                    "title": title,
                    "published_at": article.get("published", ""),
                    "source": article.get("author", "Currents"),
                    "url": article.get("url", ""),
                })
                seen_titles.add(title)

                if len(matched) >= limit:
                    break

        _logger.info("Currents: %d headlines matched %s", len(matched), pair)
        return matched

    def _search(self, keyword: str, limit: int = 30) -> list[dict[str, Any]]:
        """Search Currents by keyword.

        Args:
            keyword: Search term.
            limit: Maximum articles to return.

        Returns:
            List of article dicts from the API response.
        """
        url = f"{_BASE_URL}/search"
        params = {
            "keywords": keyword,
            "language": "en",
            "page_size": min(limit, 20),
            "apiKey": self._api_key,
        }

        _logger.info("Currents search: '%s' (limit=%d)", keyword, limit)
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict):
            return data.get("news", [])
        return []
