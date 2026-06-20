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

    def compute_features(
        self,
        df: pd.DataFrame,
        funding_rate: float = 0.0,
        open_interest: float = 0.0,
        fear_greed: int = 50,
    ) -> pd.DataFrame:
        """Enrich an OHLCV DataFrame with technical indicator columns.

        Expects at minimum columns ``close``, ``high``, ``low``.
        All NaN rows introduced by indicator lookback periods are dropped.

        Args:
            df: Raw OHLCV DataFrame with ``open``, ``high``, ``low``,
                ``close``, ``volume`` columns.
            funding_rate: Perpetual futures funding rate (added as constant
                column ``funding_rate``).
            open_interest: Open interest in base asset (normalised to billions
                as ``open_interest_normalized``).
            fear_greed: Fear & Greed index 0-100 (normalised to 0-1 as
                ``fear_greed_normalized``).

        Returns:
            DataFrame with all original columns plus new indicator columns,
            including a ``target_vol_regime`` column.
        """
        _logger.info("Computing technical features on %d rows", len(df))
        out = df.copy()

        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            if col in out.columns:
                out[col] = out[col].astype(float)

        out["funding_rate"] = funding_rate
        out["open_interest_normalized"] = open_interest / 1e9
        out["fear_greed_normalized"] = fear_greed / 100.0

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

        indicator_cols = [
            "rsi", "macd", "macd_signal",
            "bb_upper", "bb_middle", "bb_lower",
            "atr", "ema_20", "ema_50",
            "returns", "log_returns", "volatility",
        ]
        present = [c for c in indicator_cols if c in out.columns]
        before = len(out)
        out = out.dropna(subset=present, how="all")
        after = len(out)
        _logger.info(
            "Dropped %d NaN-only rows (all indicators NaN) — %d rows remaining",
            before - after,
            after,
        )

        out = self.add_volatility_regime_target(out, window=4)

        return out

    @staticmethod
    def add_volatility_regime_target(df: pd.DataFrame, window: int = 4) -> pd.DataFrame:
        """Add a binary volatility regime target column.

        The target is 1 if the maximum price range over the next
        ``window`` candles exceeds the rolling 24-candle median
        price range, else 0. The target is shifted by 1 to prevent
        lookahead bias.

        Args:
            df: DataFrame with ``high`` and ``low`` columns.
            window: Number of lookahead candles to compute max range.

        Returns:
            Copy of *df* with an added ``target_vol_regime`` column
            (``int``, 0 or 1).
        """
        out = df.copy()
        price_range = out["high"] - out["low"]
        rolling_median_range = price_range.rolling(24).median()
        future_max_range = price_range.rolling(window).max().shift(-window)
        out["target_vol_regime"] = (
            (future_max_range > rolling_median_range).astype(int).shift(1)
        )
        dropped = out["target_vol_regime"].isna().sum()
        out = out.dropna(subset=["target_vol_regime"])
        zeros = int((out["target_vol_regime"] == 0).sum())
        ones = int((out["target_vol_regime"] == 1).sum())
        _logger.info(
            "Volatility regime target — %d zeros, %d ones (%d NaN rows dropped)",
            zeros, ones, dropped,
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

    @staticmethod
    def apply_scalers(
        df: pd.DataFrame,
        feature_cols: list[str],
        scalers: dict[str, dict[str, float]],
    ) -> pd.DataFrame:
        """Apply pre-computed min-max scalers to feature columns.

        Args:
            df: DataFrame containing the feature columns.
            feature_cols: Column names to normalise.
            scalers: Dict from ``normalize_features`` mapping column names
                to ``{"min": <float>, "max": <float>}``.

        Returns:
            Normalised copy of *df*.
        """
        out = df.copy()
        for col in feature_cols:
            if col not in out.columns or col not in scalers:
                continue
            col_min = scalers[col]["min"]
            col_max = scalers[col]["max"]
            if col_max == col_min:
                out[col] = 0.0
            else:
                out[col] = (out[col].astype(float) - col_min) / (col_max - col_min)
        return out
