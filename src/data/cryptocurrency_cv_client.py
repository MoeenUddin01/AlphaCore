"""Cryptocurrency.cv news client — free, no API key required.

Aggregates crypto news from 200+ sources via the cryptocurrency.cv API.
Base URL: https://cryptocurrency.cv

Endpoints used:
  - /api/news — latest articles from all sources
  - /api/search?q=<ticker> — keyword search

No authentication required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from src.utils.logger import get_logger

_logger = get_logger(__name__)

_BASE_URL = "https://cryptocurrency.cv"


class CryptocurrencyCVClient:
    """Fetch crypto news from the cryptocurrency.cv free API."""

    def __init__(self) -> None:
        self._available = True
        _logger.info("CryptocurrencyCVClient initialised (no API key required)")

    def get_news_for_pair(self, pair: str, limit: int = 15) -> list[dict[str, Any]]:
        """Fetch recent cryptocurrency.cv news relevant to *pair*.

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
        ticker_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
                       "BNB": "binance", "ADA": "cardano"}
        search_term = ticker_map.get(base, base.lower())

        try:
            articles = self._fetch_news(limit=min(limit * 3, 50))
        except Exception as exc:
            _logger.error("CryptocurrencyCV fetch failed for %s: %s", pair, exc)
            return []

        matched: list[dict[str, Any]] = []
        seen_titles: set[str] = set()

        for article in articles:
            title = (article.get("title") or "").strip()
            if not title or title in seen_titles:
                continue

            title_lower = title.lower()
            if (search_term in title_lower
                    or base.lower() in title_lower
                    or "crypto" in title_lower):
                published = article.get("publishedAt") or article.get("created_at", "")
                source_name = article.get("source", "cryptocurrency.cv")
                if isinstance(source_name, dict):
                    source_name = source_name.get("name", "cryptocurrency.cv")
                url = article.get("url") or article.get("link", "")

                matched.append({
                    "title": title,
                    "published_at": published,
                    "source": f"cryptocurrency.cv ({source_name})",
                    "url": url,
                })
                seen_titles.add(title)

                if len(matched) >= limit:
                    break

        _logger.info(
            "CryptocurrencyCV: %d/%d articles matched %s",
            len(matched), len(articles), pair,
        )
        return matched

    def _fetch_news(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch articles from /api/news.

        Args:
            limit: Maximum number of articles to fetch.

        Returns:
            List of article dicts from the API response.
        """
        url = f"{_BASE_URL}/api/news"
        params = {"limit": min(limit, 50)}

        _logger.info("Fetching cryptocurrency.cv news (limit=%d)", limit)
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict):
            return data.get("articles", []) if "articles" in data else data.get("data", [])
        if isinstance(data, list):
            return data
        return []
