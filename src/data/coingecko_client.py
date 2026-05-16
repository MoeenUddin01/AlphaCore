"""CoinGecko API client for market data and Fear & Greed Index.

Provides on-chain and market sentiment data through CoinGecko's free
REST API and the Alternative.me Fear & Greed Index.
"""

from typing import Any

import requests

from src.utils.config import settings
from src.utils.helpers import retry_with_backoff
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"
_FNG_URL = "https://api.alternative.me/fng/"

_COIN_ID_MAP: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "ADA": "cardano",
}


class CoinGeckoClient:
    """Client for the CoinGecko REST API (free tier)."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        _logger.info("Initialised CoinGeckoClient")

    def _request(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET request with optional API key injection."""
        if params is None:
            params = {}
        if settings.COINGECKO_API_KEY:
            params["x_cg_demo_api_key"] = settings.COINGECKO_API_KEY
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff
    def get_market_data(self, coin_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch current market data for one or more coins.

        Args:
            coin_ids: CoinGecko coin IDs (e.g. ``["bitcoin", "ethereum"]``).

        Returns:
            List of dicts with keys ``id``, ``symbol``, ``current_price``,
            ``market_cap``, ``total_volume``, ``price_change_percentage_24h``.
        """
        _logger.info("Fetching market data for %s", coin_ids)
        url = f"{_BASE_URL}/coins/markets"
        params: dict[str, Any] = {
            "vs_currency": "usd",
            "ids": ",".join(coin_ids),
            "order": "market_cap_desc",
            "sparkline": "false",
        }
        try:
            data = self._request(url, params)
        except requests.RequestException as exc:
            raise RuntimeError(f"CoinGecko market data request failed: {exc}") from exc

        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected CoinGecko response type: {type(data).__name__}")

        keys = {"id", "symbol", "current_price", "market_cap", "total_volume", "price_change_percentage_24h"}
        results: list[dict[str, Any]] = []
        for item in data:
            results.append({k: item.get(k) for k in keys})
        return results

    @retry_with_backoff
    def get_fear_greed_index(self) -> dict[str, Any]:
        """Fetch the current Fear & Greed Index.

        Returns:
            Dict with keys ``value`` (int) and ``classification`` (str)
            e.g. ``{"value": 25, "classification": "Fear"}``.
        """
        _logger.info("Fetching Fear & Greed Index")
        try:
            data = self._request(_FNG_URL)
        except requests.RequestException as exc:
            raise RuntimeError(f"Fear & Greed request failed: {exc}") from exc

        entries = data.get("data", [])
        if not entries:
            raise RuntimeError("Fear & Greed response contained no data entries")

        latest = entries[0]
        try:
            return {
                "value": int(latest["value"]),
                "classification": str(latest["value_classification"]),
            }
        except (KeyError, ValueError, TypeError) as exc:
            raise RuntimeError(f"Malformed Fear & Greed entry: {exc}") from exc

    def get_coin_id(self, pair: str) -> str:
        """Convert a trading pair to a CoinGecko coin ID.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.

        Returns:
            CoinGecko coin ID (e.g. ``"bitcoin"``).

        Raises:
            ValueError: If the base asset is not in the known mapping.
        """
        base = pair.split("/")[0].upper()
        if base not in _COIN_ID_MAP:
            raise ValueError(
                f"Unknown coin ID for pair '{pair}'. "
                f"Known bases: {list(_COIN_ID_MAP.keys())}"
            )
        coin_id = _COIN_ID_MAP[base]
        _logger.debug("Mapped %s -> %s", pair, coin_id)
        return coin_id
