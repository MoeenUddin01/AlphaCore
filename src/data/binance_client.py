"""Binance API client for fetching OHLCV data, prices, and account info.

Wraps the python-binance library with retry logic, Decimal conversion,
and structured DataFrame output for downstream consumption.
"""

from decimal import Decimal

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance, retry_with_backoff, timestamp_to_datetime
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class BinanceClient:
    """Thin wrapper around the Binance API with retry and Decimal support."""

    def __init__(self) -> None:
        _logger.info("Initialising BinanceClient (testnet=%s)", settings.BINANCE_TESTNET)
        self._client = Client(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            testnet=settings.BINANCE_TESTNET,
        )

    @retry_with_backoff
    def get_ohlcv(self, pair: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """Fetch OHLCV klines for *pair* and return a DataFrame.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            interval: Kline interval (e.g. ``1h``, ``1d``).
            limit: Number of candles to fetch (max 1000).

        Returns:
            DataFrame with columns ``timestamp`` (datetime), ``open``,
            ``high``, ``low``, ``close``, ``volume`` (all Decimal).

        Raises:
            RuntimeError: If the API call or data parsing fails.
        """
        symbol = format_pair_for_binance(pair)
        _logger.info("Fetching %d %s klines for %s", limit, interval, symbol)
        try:
            klines = self._client.get_klines(symbol=symbol, interval=interval, limit=limit)
        except BinanceAPIException as exc:
            raise RuntimeError(f"Binance API error fetching klines for {symbol}: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Unexpected error fetching klines for {symbol}: {exc}") from exc

        if not klines:
            raise RuntimeError(f"Empty klines response for {symbol}")

        rows = []
        for k in klines:
            try:
                rows.append({
                    "timestamp": timestamp_to_datetime(int(k[0])),
                    "open": Decimal(k[1]),
                    "high": Decimal(k[2]),
                    "low": Decimal(k[3]),
                    "close": Decimal(k[4]),
                    "volume": Decimal(k[5]),
                })
            except (IndexError, ValueError, TypeError) as exc:
                raise RuntimeError(f"Malformed kline data for {symbol}: {exc}") from exc

        df = pd.DataFrame(rows)
        return df

    @retry_with_backoff
    def get_current_price(self, pair: str) -> Decimal:
        """Fetch the latest ticker price for *pair*.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.

        Returns:
            Current price as a Decimal.

        Raises:
            RuntimeError: If the API call fails.
        """
        symbol = format_pair_for_binance(pair)
        _logger.info("Fetching current price for %s", symbol)
        try:
            ticker = self._client.get_symbol_ticker(symbol=symbol)
            return Decimal(ticker["price"])
        except BinanceAPIException as exc:
            raise RuntimeError(f"Binance API error fetching price for {symbol}: {exc}") from exc
        except (KeyError, ValueError, TypeError) as exc:
            raise RuntimeError(f"Malformed price response for {symbol}: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Unexpected error fetching price for {symbol}: {exc}") from exc

    @retry_with_backoff
    def get_account_balance(self) -> dict[str, Decimal]:
        """Return all non-zero balances from the Binance testnet account.

        Returns:
            Dictionary mapping asset symbol (e.g. ``BTC``) to free balance
            as a Decimal.

        Raises:
            RuntimeError: If the API call fails.
        """
        _logger.info("Fetching account balances")
        try:
            account = self._client.get_account()
        except BinanceAPIException as exc:
            raise RuntimeError(f"Binance API error fetching account: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Unexpected error fetching account: {exc}") from exc

        balances: dict[str, Decimal] = {}
        for bal in account.get("balances", []):
            free = Decimal(bal.get("free", "0"))
            if free > Decimal("0"):
                balances[bal["asset"]] = free

        return balances
