"""CoinMarketCap client for crypto market data and Fear & Greed Index.

Uses the free-tier endpoints that work with a Basic plan key:
  - /v3/fear-and-greed/latest  — Fear & Greed Index (0–100)
  - /v1/cryptocurrency/listings/latest — market data
  - /v1/global-metrics/quotes/latest — global market metrics

Base URL: https://pro-api.coinmarketcap.com
Free tier: 15,000 credits/month, 50 RPM.
"""

from __future__ import annotations

from typing import Any

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class CoinMarketCapClient:
    """Fetch crypto market data and Fear & Greed from CoinMarketCap."""

    BASE_URL = "https://pro-api.coinmarketcap.com"

    def __init__(self) -> None:
        api_key = settings.COINMARKETCAP_API_KEY
        if api_key and "your_" not in api_key:
            self.headers = {
                "X-CMC_PRO_API_KEY": api_key,
                "Accept": "application/json",
            }
            self._available = True
            _logger.info("CoinMarketCapClient initialised with API key")
        else:
            self.headers = {}
            self._available = False
            _logger.info("CoinMarketCapClient disabled (no valid API key)")

    def get_fear_greed(self) -> dict[str, Any]:
        """Fetch the latest Fear & Greed Index.

        Returns:
            Dict with keys ``value`` (0-100), ``value_classification``
            (e.g. "Extreme Fear"), ``update_time``.  Empty dict on failure.
        """
        if not self._available:
            return {}

        url = f"{self.BASE_URL}/v3/fear-and-greed/latest"
        try:
            _logger.info("Fetching CoinMarketCap Fear & Greed Index")
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", {})
            if str(status.get("error_code", "")) != "0":
                _logger.warning("CMC Fear & Greed error: %s", status.get("error_message"))
                return {}

            result = data.get("data", {})
            _logger.info(
                "CMC Fear & Greed: %s (%s)",
                result.get("value"), result.get("value_classification"),
            )
            return {
                "value": result.get("value", 50),
                "value_classification": result.get("value_classification", "Neutral"),
                "update_time": result.get("update_time", ""),
                "source": "CoinMarketCap",
            }
        except Exception as exc:
            _logger.error("CoinMarketCap Fear & Greed fetch failed: %s", exc)
            return {}

    def get_global_metrics(self) -> dict[str, Any]:
        """Fetch global crypto market metrics.

        Returns:
            Dict with keys ``total_market_cap``, ``total_volume_24h``,
            ``btc_dominance``, ``eth_dominance``.  Empty dict on failure.
        """
        if not self._available:
            return {}

        url = f"{self.BASE_URL}/v1/global-metrics/quotes/latest"
        try:
            _logger.info("Fetching CoinMarketCap global metrics")
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", {})
            if str(status.get("error_code", "")) != "0":
                _logger.warning("CMC global metrics error: %s", status.get("error_message"))
                return {}

            result = data.get("data", {})
            quote = result.get("quote", {}).get("USD", {})
            _logger.info(
                "CMC global: market_cap=%.0f BTC dominance=%.1f%%",
                quote.get("total_market_cap", 0),
                result.get("btc_dominance", 0),
            )
            return {
                "total_market_cap": quote.get("total_market_cap", 0),
                "total_volume_24h": quote.get("total_volume_24h", 0),
                "btc_dominance": result.get("btc_dominance", 0),
                "eth_dominance": result.get("eth_dominance", 0),
                "active_cryptocurrencies": result.get("active_cryptocurrencies", 0),
                "source": "CoinMarketCap",
            }
        except Exception as exc:
            _logger.error("CoinMarketCap global metrics fetch failed: %s", exc)
            return {}

    def get_news_for_pair(self, pair: str, limit: int = 15) -> list[dict[str, Any]]:
        """Placeholder — /content/latest requires paid plan.

        Returns:
            Empty list. News content is not available on the free tier.
        """
        _logger.debug("CoinMarketCap news not available on free tier")
        return []
