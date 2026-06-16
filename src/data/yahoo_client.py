"""Yahoo Finance client for fetching historical OHLCV data for training.

Provides long-range historical data (up to decades) without any API key.
Used primarily for model training, not for live trading signals.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import yfinance as yf

from src.utils.logger import get_logger

_logger = get_logger(__name__)

_YAHOO_SYMBOLS: dict[str, str] = {
    "BTC/USDT": "BTC-USD",
    "ETH/USDT": "ETH-USD",
    "SOL/USDT": "SOL-USD",
    "BNB/USDT": "BNB-USD",
    "ADA/USDT": "ADA-USD",
}


class YahooClient:
    """Fetch historical crypto OHLCV data from Yahoo Finance.

    All data is returned in USD (Yahoo does not list USDT pairs).
    """

    def get_historical_ohlcv(
        self,
        pair: str,
        interval: str = "1h",
        years: int = 5,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data for *pair*.

        Args:
            pair: Trading pair in ``BTC/USDT`` format (mapped to Yahoo symbol).
            interval: Kline interval (``1h``, ``1d``). Default ``1h``.
            years: Number of years of history to fetch. Default 5.

        Returns:
            DataFrame with columns ``timestamp`` (datetime), ``open``,
            ``high``, ``low``, ``close``, ``volume`` (all Decimal),
            sorted oldest-first.

        Raises:
            ValueError: If *pair* is not in the Yahoo symbol mapping.
            RuntimeError: If the download fails or returns no data.
        """
        yahoo_symbol = _YAHOO_SYMBOLS.get(pair)
        if yahoo_symbol is None:
            raise ValueError(f"No Yahoo Finance symbol mapping for {pair}")

        period = f"{years}y"

        yf_interval = interval

        _logger.info(
            "Fetching %s %s data for %s (yahoo=%s, period=%s)",
            years, interval, pair, yahoo_symbol, period,
        )

        try:
            df = yf.download(
                tickers=yahoo_symbol,
                period=period,
                interval=yf_interval,
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:
            raise RuntimeError(f"Yahoo Finance download failed for {yahoo_symbol}: {exc}") from exc

        if df is None or df.empty:
            raise RuntimeError(f"Empty response from Yahoo Finance for {yahoo_symbol}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()

        if "Datetime" in df.columns:
            time_col = "Datetime"
        elif "Date" in df.columns:
            time_col = "Date"
        else:
            time_col = df.columns[0]

        rows = []
        for _, row in df.iterrows():
            ts = row[time_col]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)

            rows.append({
                "timestamp": ts,
                "open": Decimal(str(row.get("Open", 0))),
                "high": Decimal(str(row.get("High", 0))),
                "low": Decimal(str(row.get("Low", 0))),
                "close": Decimal(str(row.get("Close", 0))),
                "volume": Decimal(str(row.get("Volume", 0))),
            })

        result = pd.DataFrame(rows)
        result = result.sort_values("timestamp").reset_index(drop=True)
        _logger.info("Returning %d rows for %s", len(result), yahoo_symbol)
        return result
