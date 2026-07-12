"""CryptoPanic API client for fetching crypto news headlines.

Provides access to the CryptoPanic news aggregator for sentiment analysis
and news-driven trading signals.
"""

from datetime import datetime
from typing import Any

import requests

from src.utils.config import settings
from src.utils.helpers import retry_with_backoff
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_BASE_URL = "https://cryptopanic.com/api/v1"


class CryptoPanicClient:
    """Client for the CryptoPanic news API."""

    def __init__(self) -> None:
        _logger.info("Initialised CryptoPanicClient")
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    @retry_with_backoff
    def get_news(
        self,
        currencies: list[str],
        filter: str = "hot",
    ) -> list[dict[str, Any]]:
        """Fetch news posts for the given currencies.

        Args:
            currencies: List of currency codes (e.g. ``["BTC", "ETH"]``).
            filter: Post filter — ``hot``, ``bullish``, or ``bearish``.

        Returns:
            List of dicts with keys ``title``, ``published_at`` (datetime),
            ``currencies`` (list[str]), ``source`` (str), ``url`` (str).

        Raises:
            ValueError: If ``CRYPTOPANIC_API_KEY`` is not configured.
            RuntimeError: If the API request fails.
        """
        if not settings.CRYPTOPANIC_API_KEY or "your_" in settings.CRYPTOPANIC_API_KEY:
            raise ValueError(
                "CRYPTOPANIC_API_KEY is not configured. "
                "Set a real key in .env or leave empty to skip."
            )

        _logger.info("Fetching %s news for %s", filter, currencies)
        params: dict[str, Any] = {
            "auth_token": settings.CRYPTOPANIC_API_KEY,
            "currencies": ",".join(currencies),
            "filter": filter,
            "public": "true",
        }
        try:
            resp = self._session.get(f"{_BASE_URL}/posts/", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"CryptoPanic API request failed: {exc}") from exc

        results = data.get("results", [])
        if not isinstance(results, list):
            raise RuntimeError(
                f"Unexpected CryptoPanic response: 'results' key is {type(results).__name__}"
            )

        parsed: list[dict[str, Any]] = []
        for post in results:
            try:
                currency_codes = [
                    c["code"]
                    for c in (post.get("currencies") or [])
                    if isinstance(c, dict) and c.get("code")
                ]
                parsed.append({
                    "title": str(post.get("title", "")),
                    "published_at": datetime.fromisoformat(
                        post["published_at"].replace("Z", "+00:00")
                    ),
                    "currencies": currency_codes,
                    "source": post.get("source", {}).get("title", ""),
                    "url": str(post.get("url", "")),
                })
            except (KeyError, ValueError, TypeError) as exc:
                _logger.warning("Skipping malformed CryptoPanic post: %s", exc)
                continue

        return parsed

    @retry_with_backoff
    def get_news_for_pair(self, pair: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent news for a trading pair.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            limit: Maximum number of results to return.

        Returns:
            Up to *limit* news posts sorted by ``published_at`` descending.
        """
        base = pair.split("/")[0].upper()
        _logger.info("Fetching news for pair %s (base: %s)", pair, base)

        news = self.get_news(currencies=[base])

        news.sort(key=lambda n: n["published_at"], reverse=True)

        return news[:limit]
