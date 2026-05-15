"""Technical feature engineering for OHLCV market data.

Computes RSI, MACD, Bollinger Bands, ATR, EMAs, returns, and
volatility using pandas-ta. Provides min-max normalisation with
invertible scalers.
"""

import pandas as pd
import pandas_ta as ta

from src.utils.logger import get_logger

_logger = get_logger(__name__)


class FeatureEngineer:
    """Computes and normalises technical indicators from OHLCV data."""

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enrich an OHLCV DataFrame with technical indicator columns.

        Expects at minimum columns ``close``, ``high``, ``low``.
        All NaN rows introduced by indicator lookback periods are dropped.

        Args:
            df: Raw OHLCV DataFrame with ``open``, ``high``, ``low``,
                ``close``, ``volume`` columns.

        Returns:
            DataFrame with all original columns plus new indicator columns.
        """
        _logger.info("Computing technical features on %d rows", len(df))
        out = df.copy()

        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            if col in out.columns:
                out[col] = out[col].astype(float)

        out["rsi"] = ta.rsi(out["close"], length=14)

        macd_df = ta.macd(out["close"])
        if macd_df is not None and not macd_df.empty:
            macd_cols = [c for c in macd_df.columns if c.startswith("MACD_") and "s" not in c.split("_")[-1]]
            signal_cols = [c for c in macd_df.columns if c.startswith("MACDs_")]
            out["macd"] = macd_df[macd_cols[0]] if macd_cols else None
            out["macd_signal"] = macd_df[signal_cols[0]] if signal_cols else None

        bb_df = ta.bbands(out["close"], length=20)
        if bb_df is not None and not bb_df.empty:
            cols = list(bb_df.columns)
            for prefix, label in [("BBU", "bb_upper"), ("BBM", "bb_middle"), ("BBL", "bb_lower")]:
                match = [c for c in cols if c.startswith(prefix)]
                if match:
                    out[label] = bb_df[match[0]]

        out["atr"] = ta.atr(out["high"], out["low"], out["close"], length=14)

        out["ema_20"] = ta.ema(out["close"], length=20)
        out["ema_50"] = ta.ema(out["close"], length=50)

        out["returns"] = out["close"].pct_change() * 100

        out["log_returns"] = (out["close"] / out["close"].shift(1)).apply(
            lambda x: __import__("math").log(x) if pd.notna(x) and x > 0 else None
        )

        out["volatility"] = out["returns"].rolling(window=24).std()

        before = len(out)
        out = out.dropna()
        after = len(out)
        _logger.info(
            "Dropped %d NaN rows — %d rows remaining",
            before - after,
            after,
        )

        return out

    @staticmethod
    def normalize_features(
        df: pd.DataFrame,
        feature_cols: list[str],
    ) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
        """Min-max normalise selected columns in-place.

        Args:
            df: DataFrame containing the feature columns.
            feature_cols: Column names to normalise.

        Returns:
            Tuple of (normalised DataFrame, scalers dict).
            The scalers dict maps column names to
            ``{"min": <float>, "max": <float>}``.
        """
        _logger.info("Min-max normalising %d feature columns", len(feature_cols))
        out = df.copy()
        scalers: dict[str, dict[str, float]] = {}

        for col in feature_cols:
            if col not in out.columns:
                _logger.warning("Column '%s' not found — skipping normalisation", col)
                continue
            col_min = float(out[col].min())
            col_max = float(out[col].max())
            if col_max == col_min:
                _logger.warning("Column '%s' is constant — setting to 0", col)
                out[col] = 0.0
                scalers[col] = {"min": col_min, "max": col_max}
            else:
                out[col] = (out[col] - col_min) / (col_max - col_min)
                scalers[col] = {"min": col_min, "max": col_max}

        return out, scalers
