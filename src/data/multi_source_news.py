"""Multi-source news aggregator with deduplication and relevance filtering.

Combines CoinDesk RSS, CryptoPanic, CryptoCompare, CoinMarketCap,
Currents, and GNews into a single ``fetch_headlines(pair)`` call.
Headlines are deduplicated by title similarity and filtered to exclude
generic market-recap articles that add noise to sentiment scoring.
"""

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from src.data.rss_news_client import CoinDeskRSSClient
from src.utils.timestamps import normalize_timestamp
from src.utils.logger import get_logger

_logger = get_logger(__name__)

# --- Relevance filter ---------------------------------------------------
# Headlines must contain at least one coin ticker OR a directional keyword
# to pass the relevance gate.  Generic recaps ("Weekly Roundup", "Market
# Update") are silently dropped.

_COIN_TICKERS = {
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
    "binance", "bnb", "cardano", "ada", "xrp", "ripple",
    "dogecoin", "doge", "polkadot", "dot", "avalanche", "avax",
    "chainlink", "link", "uniswap", "uni", "litecoin", "ltc",
    "crypto", "blockchain", "defi", "nft", "web3",
}

_DIRECTIONAL_KEYWORDS = {
    "surge", "rally", "crash", "plunge", "soar", "tank", "dump", "pump",
    "bull", "bear", "breakout", "breakdown", "rally", "selloff", "sell-off",
    "ath", "all-time high", "all time high", "bottom", "top",
    "buy", "sell", "long", "short", "moon", "collapse", "recovery",
    "approve", "approval", "etf", "regulation", "ban", "launch",
    "hack", "exploit", "sec", "fed", "rate cut", "rate hike",
    "adoption", "partnership", "upgrade", "halving",
}


def _is_relevant(title: str) -> bool:
    """Return True if the headline mentions a specific coin or directional event."""
    lower = title.lower()
    return any(kw in lower for kw in _COIN_TICKERS | _DIRECTIONAL_KEYWORDS)


def _normalise_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for comparison."""
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _titles_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """Check whether two normalised titles are similar enough to dedup."""
    na, nb = _normalise_title(a), _normalise_title(b)
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


class MultiSourceNewsClient:
    """Aggregates news from CoinDesk RSS, CryptoPanic, and CryptoCompare.

    Falls back gracefully — if a source is unavailable or has no key, the
    other sources still contribute.  Headlines are deduplicated by title
    similarity and filtered for relevance before being returned.
    """

    def __init__(self) -> None:
        self._rss = CoinDeskRSSClient()

        # Lazy-init optional clients (they may lack API keys)
        self._cryptopanic = None
        self._cryptocompare = None
        self._coinmarketcap = None

        try:
            from src.data.cryptopanic_client import CryptoPanicClient
            self._cryptopanic = CryptoPanicClient()
        except Exception:
            _logger.debug("CryptoPanic client not available")

        try:
            from src.data.cryptocompare_client import CryptoCompareClient
            self._cryptocompare = CryptoCompareClient()
        except Exception:
            _logger.debug("CryptoCompare client not available")

        try:
            from src.data.coinmarketcap_client import CoinMarketCapClient
            self._coinmarketcap = CoinMarketCapClient()
        except Exception:
            _logger.debug("CoinMarketCap client not available")

        try:
            from src.data.currents_client import CurrentsClient
            self._currents = CurrentsClient()
        except Exception:
            _logger.debug("Currents client not available")

        try:
            from src.data.gnews_client import GNewsClient
            self._gnews = GNewsClient()
        except Exception:
            _logger.debug("GNews client not available")

    # ------------------------------------------------------------------
    def fetch_headlines(
        self,
        pair: str,
        limit_per_source: int = 15,
    ) -> list[dict[str, Any]]:
        """Fetch, deduplicate, and filter headlines from all available sources.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            limit_per_source: Max headlines to pull from each source.

        Returns:
            List of dicts with keys ``title``, ``published_at``,
            ``currencies``, ``source``, ``url`` — sorted by ``published_at``
            descending.  All titles pass the relevance filter.
        """
        raw: list[dict[str, Any]] = []

        # --- Source 1: CoinDesk RSS (always available, no key) ---
        try:
            rss_items = self._rss.get_news_for_pair(pair, limit=limit_per_source)
            raw.extend(rss_items)
            _logger.info("RSS: %d headlines for %s", len(rss_items), pair)
        except Exception as exc:
            _logger.warning("RSS fetch failed for %s: %s", pair, exc)

        # --- Source 2: CryptoPanic (DORMANT — needs valid API key) ---
        # Skips gracefully when no key is configured. Activates automatically
        # once CRYPTOPANIC_API_KEY is set in .env.
        if self._cryptopanic is not None:
            try:
                cp_items = self._cryptopanic.get_news_for_pair(pair, limit=limit_per_source)
                raw.extend(cp_items)
                _logger.info("CryptoPanic: %d headlines for %s", len(cp_items), pair)
            except ValueError:
                _logger.debug("CryptoPanic: dormant (no valid API key), skipping")
            except Exception as exc:
                _logger.warning("CryptoPanic fetch failed for %s: %s", pair, exc)

        # --- Source 3: CryptoCompare (DORMANT — API requires key, keyless returns 401) ---
        # Auto-disables after first 401. Activates automatically once
        # CRYPTOCOMPARE_API_KEY is set in .env.
        if self._cryptocompare is not None:
            try:
                cc_items = self._cryptocompare.get_news_for_pair(pair, limit=limit_per_source)
                raw.extend(cc_items)
                _logger.info("CryptoCompare: %d headlines for %s", len(cc_items), pair)
            except Exception as exc:
                _logger.warning("CryptoCompare fetch failed for %s: %s", pair, exc)

        # --- Source 4: CoinMarketCap (crypto-native news) ---
        if self._coinmarketcap is not None:
            try:
                cmc_items = self._coinmarketcap.get_news_for_pair(pair, limit=limit_per_source)
                raw.extend(cmc_items)
                _logger.info("CoinMarketCap: %d headlines for %s", len(cmc_items), pair)
            except Exception as exc:
                _logger.warning("CoinMarketCap fetch failed for %s: %s", pair, exc)

        # --- Source 5: Currents API (1,000 free req/day) ---
        if self._currents is not None:
            try:
                cur_items = self._currents.get_news_for_pair(pair, limit=limit_per_source)
                raw.extend(cur_items)
                _logger.info("Currents: %d headlines for %s", len(cur_items), pair)
            except Exception as exc:
                _logger.warning("Currents fetch failed for %s: %s", pair, exc)

        # --- Source 6: GNews API (DORMANT — free tier has ~12h indexing delay) ---
        # Structurally delayed: freshest headline is always 12-17h old.
        # Removed from active pipeline 2026-07-12. If GNews offers a faster
        # free tier or a paid plan, re-enable by uncommenting below.
        #
        # if self._gnews is not None:
        #     try:
        #         gn_items = self._gnews.get_news_for_pair(pair, limit=limit_per_source)
        #         raw.extend(gn_items)
        #         _logger.info("GNews: %d headlines for %s", len(gn_items), pair)
        #     except Exception as exc:
        #         _logger.warning("GNews fetch failed for %s: %s", pair, exc)

        _logger.info("Total raw headlines for %s: %d", pair, len(raw))

        # --- Relevance filter ---
        relevant = [h for h in raw if _is_relevant(h.get("title", ""))]
        _logger.info("After relevance filter: %d / %d", len(relevant), len(raw))

        # --- Deduplication by title similarity ---
        deduped: list[dict[str, Any]] = []
        for item in relevant:
            title = item.get("title", "")
            is_dup = False
            for existing in deduped:
                if _titles_similar(title, existing.get("title", "")):
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(item)

        _logger.info("After dedup: %d / %d", len(deduped), len(relevant))

        # Normalise all timestamps before sorting
        for item in deduped:
            item["_parsed_ts"] = normalize_timestamp(item.get("published_at"))

        # Sort by normalised timestamp descending
        deduped.sort(key=lambda n: n["_parsed_ts"], reverse=True)

        # Clean up internal key
        for item in deduped:
            item.pop("_parsed_ts", None)

        return deduped[:limit_per_source * 2]
