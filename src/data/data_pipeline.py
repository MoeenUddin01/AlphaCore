"""Master orchestrator for all data fetching and feature computation.

Coordinates Binance, CoinGecko, CryptoPanic, and feature engineering
into a single ``run()`` call that returns a structured dict ready for
the prediction and agent layers.
"""

from pathlib import Path
from decimal import Decimal
from typing import Any

import pandas as pd

from src.data.binance_client import BinanceClient
from src.data.coingecko_client import CoinGeckoClient
from src.data.cryptopanic_client import CryptoPanicClient
from src.data.feature_engineer import FeatureEngineer
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class DataPipeline:
    """Aggregate data from all sources and produce enriched features."""

    def __init__(self) -> None:
        _logger.info("Initialising DataPipeline")
        self.binance = BinanceClient()
        self.coingecko = CoinGeckoClient()
        self.cryptopanic = CryptoPanicClient()
        self.feature_engineer = FeatureEngineer()
        self._cache_dir = Path(settings.DATA_CACHE_DIR)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def run(self, pairs: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """Execute the full data pipeline for all trading pairs.

        Args:
            pairs: List of pairs in ``BTC/USDT`` format. Defaults to
                   ``settings.TRADING_PAIRS``.

        Returns:
            Dict keyed by pair. Each value contains:
                - ``ohlcv_features`` (pd.DataFrame)
                - ``current_price`` (Decimal)
                - ``market_data`` (dict)
                - ``news`` (list[dict])
                - ``fear_greed`` (dict)
        """
        if pairs is None:
            pairs = list(settings.TRADING_PAIRS)

        _logger.info("Starting data pipeline run for %d pair(s): %s", len(pairs), pairs)

        fear_greed: dict[str, Any] = {}
        try:
            fear_greed = self.coingecko.get_fear_greed_index()
            _logger.info("Fear & Greed: %s", fear_greed)
        except Exception as exc:
            _logger.warning("Failed to fetch Fear & Greed index: %s", exc)

        result: dict[str, dict[str, Any]] = {}

        for pair in pairs:
            _logger.info("=== Processing %s ===", pair)
            pair_data: dict[str, Any] = {}

            try:
                ohlcv = self.binance.get_ohlcv(pair, interval="1h", limit=500)
                features = self.feature_engineer.compute_features(ohlcv)
                pair_data["ohlcv_features"] = features
            except Exception as exc:
                _logger.error("OHLCV / features failed for %s: %s", pair, exc)
                pair_data["ohlcv_features"] = pd.DataFrame()
                pair_data["current_price"] = Decimal("0")
                pair_data["market_data"] = {}
                pair_data["news"] = []
                pair_data["fear_greed"] = fear_greed
                result[pair] = pair_data
                continue

            try:
                price = self.binance.get_current_price(pair)
                pair_data["current_price"] = price
                _logger.info("Current price for %s: %s", pair, price)
            except Exception as exc:
                _logger.error("Price fetch failed for %s: %s", pair, exc)
                pair_data["current_price"] = Decimal("0")

            try:
                coin_id = self.coingecko.get_coin_id(pair)
                market_data_list = self.coingecko.get_market_data([coin_id])
                pair_data["market_data"] = market_data_list[0] if market_data_list else {}
            except Exception as exc:
                _logger.error("Market data failed for %s: %s", pair, exc)
                pair_data["market_data"] = {}

            try:
                news = self.cryptopanic.get_news_for_pair(pair, limit=10)
                pair_data["news"] = news
            except Exception as exc:
                _logger.error("News fetch failed for %s: %s", pair, exc)
                pair_data["news"] = []

            pair_data["fear_greed"] = fear_greed

            result[pair] = pair_data

            cache_path = self._cache_dir / f"{format_pair_for_binance(pair)}.csv"
            try:
                features.to_csv(cache_path, index=False)
                _logger.info("Cached OHLCV features to %s", cache_path)
            except Exception as exc:
                _logger.error("Failed to cache %s: %s", cache_path, exc)

        _logger.info("Data pipeline run complete — processed %d pair(s)", len(result))
        return result
