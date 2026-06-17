"""Binance API client for fetching OHLCV data, prices, and account info.

Wraps the python-binance library with retry logic, Decimal conversion,
and structured DataFrame output for downstream consumption.
"""

import time
from decimal import Decimal

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance, retry_with_backoff, timestamp_to_datetime
from src.utils.logger import get_logger

_FUTURES_ERROR_MSG = "pair is not a valid futures symbol"

_logger = get_logger(__name__)

_INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}


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

        When ``limit > 1000`` the method paginates automatically by
        walking backwards from the current time in 1000-candle chunks.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.
            interval: Kline interval (e.g. ``1h``, ``1d``).
            limit: Number of candles to fetch. Max 1000 per request,
                but any value is accepted and paginated if needed.

        Returns:
            DataFrame with columns ``timestamp`` (datetime), ``open``,
            ``high``, ``low``, ``close``, ``volume`` (all Decimal),
            sorted oldest-first with duplicates removed.

        Raises:
            RuntimeError: If the API call or data parsing fails.
        """
        symbol = format_pair_for_binance(pair)
        _logger.info("Fetching %d %s klines for %s", limit, interval, symbol)

        if limit <= 1000:
            return self._fetch_chunk(symbol, interval, limit)

        chunk_size = 1000
        interval_ms = _INTERVAL_MS.get(interval, 3_600_000)
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - limit * interval_ms
        all_rows: list[dict] = []
        seen_timestamps: set[int] = set()

        _logger.info("Paginating %s %s data from %d chunks", symbol, interval, (limit + chunk_size - 1) // chunk_size)

        while start_ms < now_ms and len(all_rows) < limit:
            end_ms = min(start_ms + chunk_size * interval_ms, now_ms)
            try:
                klines = self._client.get_klines(
                    symbol=symbol, interval=interval, limit=chunk_size,
                    startTime=int(start_ms), endTime=int(end_ms),
                )
            except BinanceAPIException as exc:
                raise RuntimeError(f"Binance API error fetching klines for {symbol}: {exc}") from exc
            except Exception as exc:
                raise RuntimeError(f"Unexpected error fetching klines for {symbol}: {exc}") from exc

            if not klines:
                start_ms = end_ms
                continue

            for k in klines:
                try:
                    ts = int(k[0])
                    if ts in seen_timestamps:
                        continue
                    seen_timestamps.add(ts)
                    all_rows.append({
                        "timestamp": timestamp_to_datetime(ts),
                        "open": Decimal(k[1]),
                        "high": Decimal(k[2]),
                        "low": Decimal(k[3]),
                        "close": Decimal(k[4]),
                        "volume": Decimal(k[5]),
                    })
                except (IndexError, ValueError, TypeError) as exc:
                    raise RuntimeError(f"Malformed kline data for {symbol}: {exc}") from exc

            start_ms = end_ms
            _logger.debug("Fetched %d rows so far for %s", len(all_rows), symbol)

        if not all_rows:
            raise RuntimeError(f"Empty klines response for {symbol}")

        df = pd.DataFrame(all_rows)
        df = df.sort_values("timestamp").reset_index(drop=True)
        _logger.info("Returning %d %s klines for %s", len(df), interval, symbol)
        return df

    def _fetch_chunk(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """Fetch a single chunk of klines (``limit <= 1000``)."""
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

        return pd.DataFrame(rows)

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

    @retry_with_backoff
    def get_funding_rate(self, pair: str) -> dict:
        """Fetch the latest futures funding rate for *pair*.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.

        Returns:
            Dict with keys ``funding_rate`` (Decimal) and
            ``next_funding_time`` (datetime or ``None``).
            Returns zero values with a warning if the pair is not a
            valid futures symbol.
        """
        sym = format_pair_for_binance(pair)
        _logger.info("Fetching funding rate for %s", sym)
        try:
            data = self._client.futures_funding_rate(symbol=sym, limit=1)
            if not data:
                _logger.warning("Empty funding rate response for %s", sym)
                return {"funding_rate": Decimal("0"), "next_funding_time": None}
            entry = data[0]
            rate = Decimal(entry.get("fundingRate", "0"))
            funding_time_ms = entry.get("fundingTime")
            next_time = timestamp_to_datetime(int(funding_time_ms)) if funding_time_ms else None
            _logger.info("Funding rate for %s: rate=%s, next_time=%s", sym, rate, next_time)
            return {"funding_rate": rate, "next_funding_time": next_time}
        except BinanceAPIException as exc:
            _logger.warning("%s — %s", _FUTURES_ERROR_MSG, exc)
            return {"funding_rate": Decimal("0"), "next_funding_time": None}
        except Exception as exc:
            _logger.warning("%s — %s", _FUTURES_ERROR_MSG, exc)
            return {"funding_rate": Decimal("0"), "next_funding_time": None}

    @retry_with_backoff
    def get_open_interest(self, pair: str) -> dict:
        """Fetch the latest futures open interest for *pair*.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.

        Returns:
            Dict with keys ``open_interest`` (Decimal, quantity in base
            asset) and ``open_interest_value`` (Decimal, USDT notional
            value computed from the current spot price).
            Returns zero values with a warning if the pair is not a
            valid futures symbol.
        """
        sym = format_pair_for_binance(pair)
        _logger.info("Fetching open interest for %s", sym)
        try:
            data = self._client.futures_open_interest(symbol=sym)
            oi = Decimal(data.get("openInterest", "0"))
            price = self.get_current_price(pair)
            oi_value = oi * price
            _logger.info(
                "Open interest for %s: oi=%s, oi_value=%s, price=%s",
                sym, oi, oi_value, price,
            )
            return {"open_interest": oi, "open_interest_value": oi_value}
        except BinanceAPIException as exc:
            _logger.warning("%s — %s", _FUTURES_ERROR_MSG, exc)
            return {"open_interest": Decimal("0"), "open_interest_value": Decimal("0")}
        except Exception as exc:
            _logger.warning("%s — %s", _FUTURES_ERROR_MSG, exc)
            return {"open_interest": Decimal("0"), "open_interest_value": Decimal("0")}
