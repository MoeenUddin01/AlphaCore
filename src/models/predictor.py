"""Unified inference interface for price prediction and sentiment analysis.

Agents should never import LSTM or FinBERT directly — only this file.
The Predictor class combines both models and exposes predict_price,
predict_sentiment, and run_all entry points.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from src.models.lstm_model import LSTMModel
from src.models.sentiment_model import SentimentModel
from src.models.trainer import LSTMTrainer
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_FEATURE_COLS = [
    "rsi", "macd", "macd_signal", "bb_upper", "bb_middle", "bb_lower",
    "atr", "ema_20", "ema_50", "returns", "log_returns", "volatility",
]

class Predictor:
    """Aggregate interface for price and sentiment predictions.

    Loads one binary classification LSTM model per trading pair and
    exposes predict_price, predict_sentiment, and run_all entry points.
    """

    def __init__(self) -> None:
        _logger.info("Initialising Predictor")
        self.sentiment = SentimentModel()
        self.models: dict[str, nn.Module] = {}
        self.scalers: dict[str, dict[str, dict[str, float]]] = {}

        artifacts_dir = Path("artifacts")
        for symbol in settings.TRADING_PAIRS:
            sym = format_pair_for_binance(symbol)
            model = LSTMModel(input_size=len(_FEATURE_COLS))
            trainer = LSTMTrainer(model=model)
            found = trainer.load_checkpoint(sym)
            if found:
                _logger.info("Checkpoint loaded for %s", sym)
            else:
                _logger.warning("No checkpoint for %s — using fresh model", sym)
            self.models[sym] = model

            scaler_path = artifacts_dir / f"scaler_{sym}.json"
            if scaler_path.exists():
                with open(scaler_path) as f:
                    self.scalers[sym] = json.load(f)
                _logger.info("Scaler loaded for %s", sym)
            else:
                self.scalers[sym] = {}

    def predict_price(self, symbol: str, feature_df: pd.DataFrame) -> dict[str, Any]:
        """Predict next-period direction for *symbol*.

        Args:
            symbol: Trading pair in ``BTC/USDT`` format.
            feature_df: DataFrame containing at least the last 24 rows of
                technical indicator features.

        Returns:
            Dict with keys ``symbol``, ``predicted_return`` (probability
            of "up", 0-1), ``direction`` ("up" / "down"), and ``confidence``
            (max softmax probability, 0-1).
        """
        sym = format_pair_for_binance(symbol)

        if len(feature_df) < 24:
            _logger.warning("%s: only %d rows available (need 24)", sym, len(feature_df))
            return {
                "symbol": symbol,
                "predicted_return": 0.0,
                "direction": "neutral",
                "confidence": 0.0,
            }

        available = [c for c in _FEATURE_COLS if c in feature_df.columns]
        if len(available) < len(_FEATURE_COLS):
            _logger.warning("%s: missing feature columns: %s", sym, set(_FEATURE_COLS) - set(available))

        seq = feature_df[available].iloc[-24:].copy().astype("float32")
        scaler = self.scalers.get(sym, {})
        for i, col in enumerate(available):
            if col in scaler:
                mn = scaler[col]["min"]
                mx = scaler[col]["max"]
                if mx != mn:
                    seq.iloc[:, i] = (seq.iloc[:, i] - mn) / (mx - mn)
        tensor = torch.from_numpy(seq.values.copy()).unsqueeze(0)

        model = self.models.get(sym)
        if model is None:
            return {"symbol": symbol, "predicted_return": 0.0, "direction": "neutral", "confidence": 0.0}

        model.eval()
        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze(0)

        prob_up = float(probs[1].item())
        direction = "up" if prob_up >= 0.5 else "down"
        confidence = float(probs.max().item())

        _logger.info(
            "Price prediction %s: prob_up=%.4f direction=%s confidence=%.4f",
            sym, prob_up, direction, confidence,
        )

        return {
            "symbol": symbol,
            "predicted_return": prob_up,
            "direction": direction,
            "confidence": confidence,
        }

    def predict_sentiment(self, symbol: str, headlines: list[str]) -> dict[str, Any]:
        """Score sentiment for a batch of headlines.

        Args:
            symbol: Trading pair in ``BTC/USDT`` format.
            headlines: List of news headline strings.

        Returns:
            Dict from :meth:`SentimentModel.aggregate_sentiment` with
            ``symbol`` added.
        """
        result = self.sentiment.aggregate_sentiment(headlines)
        result["symbol"] = symbol
        _logger.info(
            "Sentiment %s: composite=%.4f positive=%.4f negative=%.4f",
            format_pair_for_binance(symbol),
            result["composite_score"],
            result.get("positive", 0.0),
            result.get("negative", 0.0),
        )
        return result

    def run_all(self, pipeline_data: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Run price and sentiment predictions for every pair.

        Args:
            pipeline_data: Output from ``DataPipeline.run()``, a dict
                keyed by pair with ``ohlcv_features`` and ``news``.

        Returns:
            Dict keyed by pair with sub-keys ``price`` and ``sentiment``.
        """
        signals: dict[str, dict[str, Any]] = {}
        for pair, data in pipeline_data.items():
            sym = format_pair_for_binance(pair)
            _logger.info("Running predictions for %s", sym)

            price_pred = self.predict_price(pair, data.get("ohlcv_features", pd.DataFrame()))
            sentiment_pred = self.predict_sentiment(pair, data.get("news", []))

            signals[pair] = {
                "price": price_pred,
                "sentiment": sentiment_pred,
            }

        return signals
