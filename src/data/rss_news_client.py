"""CoinDesk RSS client — drop-in fallback news source for AlphaCore.

Uses feedparser to fetch and parse the CoinDesk RSS feed, returning
results in the exact same dict format as CryptoPanicClient so it can
be used as a drop-in replacement anywhere in the pipeline.
"""

from datetime import datetime, timezone
from typing import Any

import feedparser

from src.utils.logger import get_logger

_logger = get_logger(__name__)


class CoinDeskRSSClient:
    """Fallback news client that parses the CoinDesk RSS feed.

    Returns results in the same format as
    :meth:`CryptoPanicClient.get_news_for_pair` for drop-in compatibility.
    """

    SYMBOL_KEYWORDS: dict[str, list[str]] = {
        "BTC": ["bitcoin", "btc"],
        "ETH": ["ethereum", "eth"],
        "SOL": ["solana", "sol"],
        "BNB": ["binance", "bnb"],
        "ADA": ["cardano", "ada"],
    }

    _RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"

    def __init__(self) -> None:
        _logger.info("Initialised CoinDeskRSSClient")

    def get_news_for_pair(self, pair: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent CoinDesk articles relevant to *pair*.

        Fetches the RSS feed, extracts the base symbol from *pair*, and
        filters entries whose title or summary contains any matching
        keyword from :attr:`SYMBOL_KEYWORDS` (case-insensitive).

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            limit: Maximum number of matching articles to return.

        Returns:
            List of dicts with keys ``title``, ``published_at``,
            ``currencies``, ``source``, ``url`` — matching the
            ``CryptoPanicClient`` interface.  Sorted by ``published_at``
            descending.  Empty list on failure (never raises).
        """
        base = pair.split("/")[0].upper()
        keywords = self.SYMBOL_KEYWORDS.get(base, [base.lower()])
        _logger.info("Fetching CoinDesk RSS for %s (keywords: %s)", pair, keywords)

        try:
            feed = feedparser.parse(self._RSS_URL)
        except Exception as exc:
            _logger.error("CoinDesk RSS parse failed for %s: %s", pair, exc)
            return []

        matched: list[dict[str, Any]] = []
        for entry in feed.entries:
            title = entry.get("title", "") or ""
            summary = entry.get("summary", "") or ""
            combined = (title + " " + summary).lower()

            if not any(kw in combined for kw in keywords):
                continue

            published: datetime | None = None
            parsed = entry.get("published_parsed")
            if parsed:
                try:
                    published = datetime(*parsed[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    published = None

            if published is None:
                published = datetime.now(timezone.utc)

            matched.append({
                "title": title,
                "published_at": published,
                "currencies": [base],
                "source": "CoinDesk RSS",
                "url": entry.get("link", ""),
            })

        matched.sort(key=lambda n: n["published_at"], reverse=True)

        _logger.info(
            "CoinDesk RSS: %d/%d entries matched %s",
            len(matched), len(feed.entries), pair,
        )
        return matched[:limit]
