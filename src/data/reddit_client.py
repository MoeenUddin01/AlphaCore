"""Reddit client — reads r/CryptoCurrency posts as a news source.

Uses the praw library (read-only mode) to search the r/CryptoCurrency
subreddit for posts matching a coin name.  Returns the same dict format
as CryptoPanicClient for drop-in compatibility.

Reddit setup (instant, no approval wait):
  1. Go to https://www.reddit.com/prefs/apps
  2. Click "create another app" → choose "script"
  3. Copy the client_id (under the app name) and client_secret
  4. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in your .env
"""

from datetime import datetime, timezone
from typing import Any

import praw

from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_SYMBOL_TO_NAME: dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "BNB": "Binance Coin",
    "ADA": "Cardano",
}


class RedditClient:
    """Client that searches r/CryptoCurrency for coin-related posts."""

    def __init__(self) -> None:
        _logger.info("Initialising RedditClient")
        self._reddit: praw.Reddit | None = None
        client_id = getattr(settings, "REDDIT_CLIENT_ID", "")
        client_secret = getattr(settings, "REDDIT_CLIENT_SECRET", "")
        user_agent = getattr(settings, "REDDIT_USER_AGENT", "AlphaCore/1.0")

        if not client_id or not client_secret:
            _logger.warning(
                "REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET not set — "
                "RedditClient will return empty results. "
                "Create a free app at https://www.reddit.com/prefs/apps (script type, no approval wait)."
            )
            return

        try:
            self._reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            _logger.info("RedditClient authenticated (read-only)")
        except Exception as exc:
            _logger.error("Failed to initialise RedditClient: %s", exc)

    def get_news_for_pair(self, pair: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search r/CryptoCurrency for posts about the coin in *pair*.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            limit: Maximum number of posts to return.

        Returns:
            List of dicts with keys ``title``, ``published_at``,
            ``currencies``, ``source``, ``url``.  Empty on failure.
        """
        if self._reddit is None:
            _logger.warning("RedditClient not initialised — skipping %s", pair)
            return []

        base = pair.split("/")[0].upper()
        coin_name = _SYMBOL_TO_NAME.get(base, base)
        _logger.info("Searching r/CryptoCurrency for %s (query: %s)", pair, coin_name)

        try:
            subreddit = self._reddit.subreddit("CryptoCurrency")
            posts = subreddit.search(
                query=coin_name,
                sort="new",
                time_filter="day",
                limit=limit,
            )
        except Exception as exc:
            _logger.error("Reddit search failed for %s: %s", pair, exc)
            return []

        parsed: list[dict[str, Any]] = []
        for post in posts:
            try:
                published_at = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                published_at = datetime.now(timezone.utc)

            parsed.append({
                "title": str(getattr(post, "title", "")),
                "published_at": published_at,
                "currencies": [base],
                "source": "Reddit",
                "url": f"https://reddit.com{getattr(post, 'permalink', '')}",
            })

        _logger.info(
            "Reddit: %d posts for %s",
            len(parsed), pair,
        )
        return parsed
