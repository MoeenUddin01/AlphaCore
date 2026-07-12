"""CryptoCompare API client — multi-source news feed for AlphaCore.

Uses the CoinDesk-branded CryptoCompare API at ``data-api.coindesk.com``.
Works with or without an API key (keyless tier has lower rate limits).
Provides the same interface as ``CryptoPanicClient`` for drop-in
compatibility in the data pipeline.
"""

from datetime import datetime, timezone
from typing import Any

import requests

from src.utils.config import settings
from src.utils.helpers import retry_with_backoff
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_BASE_URL = "https://data-api.coindesk.com/news/v1/article/list"


class CryptoCompareClient:
    """Client for the CryptoCompare / CoinDesk news API.

    Builds an ``x-api-key`` header only when
    ``settings.CRYPTOCOMPARE_API_KEY`` is non-empty.
    """

    SYMBOL_TO_NAME: dict[str, str] = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binance",
        "ADA": "cardano",
    }

    def __init__(self) -> None:
        api_key = settings.CRYPTOCOMPARE_API_KEY
        self.headers: dict[str, str] = {}
        if api_key and "your_" not in api_key:
            self.headers["x-api-key"] = api_key
            _logger.info("CryptoCompareClient using API key")
        else:
            _logger.info("CryptoCompareClient in keyless mode (lower rate limits)")
        self._logged_keys: bool = False
        self._available: bool = True

    def get_news_for_pair(self, pair: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent CryptoCompare news relevant to *pair*.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            limit: Maximum number of articles to return.

        Returns:
            List of dicts with keys ``title``, ``published_at``,
            ``currencies``, ``source``, ``url``.  Sorted by
            ``published_at`` descending.  Empty on failure.
        """
        if not self._available:
            return []

        base = pair.split("/")[0].upper()
        coin_name = self.SYMBOL_TO_NAME.get(base, base.lower())
        _logger.info("Fetching CryptoCompare news for %s (category: %s)", pair, coin_name)

        params: dict[str, str] = {
            "lang": "EN",
            "categories": coin_name,
        }

        try:
            data = self._request(params)
        except Exception as exc:
            _logger.error("CryptoCompare request failed for %s: %s", pair, exc)
            self._available = False
            return []

        if not isinstance(data, dict):
            _logger.warning("CryptoCompare: response is not a dict (%s)", type(data).__name__)
            return []

        if not self._logged_keys:
            _logger.info("CryptoCompare response top-level keys: %s", list(data.keys()))
            self._logged_keys = True

        raw_articles = data.get("Data", [])
        if not isinstance(raw_articles, list):
            _logger.warning(
                "CryptoCompare: 'Data' key has unexpected type %s. "
                "Top-level keys: %s",
                type(raw_articles).__name__,
                list(data.keys()),
            )
            if not self._logged_keys:
                _logger.info("CryptoCompare raw response: %s", str(data)[:500])
                self._logged_keys = True
            return []

        parsed: list[dict[str, Any]] = []
        for article in raw_articles:
            published_at: datetime | None = None
            raw_ts = article.get("published")
            if raw_ts is not None:
                try:
                    published_at = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    published_at = None

            if published_at is None:
                try:
                    raw_ts = article.get("published_on")
                    if raw_ts is not None:
                        published_at = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    published_at = None

            if published_at is None:
                published_at = datetime.now(timezone.utc)

            parsed.append({
                "title": str(article.get("title", "")),
                "published_at": published_at,
                "currencies": [base],
                "source": str(article.get("source", "CryptoCompare")),
                "url": str(article.get("url", article.get("guid", ""))),
            })

        parsed.sort(key=lambda n: n["published_at"], reverse=True)

        _logger.info(
            "CryptoCompare: %d articles for %s",
            len(parsed), pair,
        )
        return parsed[:limit]

    @retry_with_backoff(max_retries=2)
    def _request(self, params: dict[str, str]) -> dict[str, Any] | None:
        """Execute the HTTP GET with retry logic.

        Args:
            params: Query parameters for the API call.

        Returns:
            Parsed JSON dict, or ``None`` on failure.
        """
        resp = requests.get(_BASE_URL, params=params, headers=self.headers, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data
