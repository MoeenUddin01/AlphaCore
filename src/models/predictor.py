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

from src.models.lstm_model import LSTMClassifier, LSTMModel
from src.models.sentiment_model import SentimentModel
from src.models.trainer import LSTMClassifierTrainer, LSTMTrainer
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_FEATURE_COLS = [
    "rsi", "macd", "macd_signal", "bb_upper", "bb_middle", "bb_lower",
    "atr", "ema_20", "ema_50", "returns", "log_returns", "volatility",
]

class Predictor:
    """Aggregate interface for price, sentiment, and volatility predictions.

    Maintains two model sets per trading pair:
      - ``LSTMModel`` for next-candle direction (up/down)
      - ``LSTMClassifier`` for volatility regime (high/low)
    and a shared scaler dict for feature normalisation.
    """

    def __init__(self) -> None:
        _logger.info("Initialising Predictor")
        self.sentiment = SentimentModel()
        self.models: dict[str, nn.Module] = {}
        self.classifier_models: dict[str, nn.Module] = {}
        self.scalers: dict[str, dict[str, dict[str, float]]] = {}

        artifacts_dir = Path("artifacts")
        for symbol in settings.TRADING_PAIRS:
            sym = format_pair_for_binance(symbol)

            model = LSTMModel(input_size=len(_FEATURE_COLS))
            trainer = LSTMTrainer(model=model)
            found = trainer.load_checkpoint(sym)
            if found:
                _logger.info("Direction checkpoint loaded for %s", sym)
            else:
                _logger.warning("No direction checkpoint for %s — using fresh model", sym)
            self.models[sym] = model

            classifier = LSTMClassifier(input_size=len(_FEATURE_COLS))
            clf_trainer = LSTMClassifierTrainer(model=classifier)
            clf_found = clf_trainer.load_checkpoint(sym)
            if clf_found:
                _logger.info("Classifier checkpoint loaded for %s", sym)
            else:
                _logger.warning("No classifier checkpoint for %s — using fresh model", sym)
            self.classifier_models[sym] = classifier

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

    def predict_volatility_regime(self, symbol: str, feature_df: pd.DataFrame) -> dict[str, Any]:
        """Predict volatility regime (high / low) for *symbol*.

        Args:
            symbol: Trading pair in ``BTC/USDT`` format.
            feature_df: DataFrame containing at least the last 24 rows of
                technical indicator features.

        Returns:
            Dict with keys ``symbol``, ``vol_regime`` (int 0 or 1),
            ``vol_regime_prob`` (float, raw sigmoid output),
            ``regime_label`` ("HIGH_VOL" / "LOW_VOL").
        """
        sym = format_pair_for_binance(symbol)

        if len(feature_df) < 24:
            _logger.warning("%s: only %d rows available (need 24)", sym, len(feature_df))
            return {
                "symbol": symbol,
                "vol_regime": 0,
                "vol_regime_prob": 0.0,
                "regime_label": "LOW_VOL",
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

        classifier = self.classifier_models.get(sym)
        if classifier is None:
            return {
                "symbol": symbol, "vol_regime": 0,
                "vol_regime_prob": 0.0, "regime_label": "LOW_VOL",
            }

        classifier.eval()
        with torch.no_grad():
            prob = classifier(tensor).squeeze().item()

        vol_regime = 1 if prob >= 0.5 else 0
        regime_label = "HIGH_VOL" if vol_regime else "LOW_VOL"

        _logger.info(
            "Volatility regime %s: prob=%.4f regime=%s",
            sym, prob, regime_label,
        )

        return {
            "symbol": symbol,
            "vol_regime": vol_regime,
            "vol_regime_prob": round(prob, 4),
            "regime_label": regime_label,
        }

    def predict_sentiment(self, symbol: str, headline_dicts: list[dict[str, Any]]) -> dict[str, Any]:
        """Score sentiment for a batch of headline dicts.

        Each dict must contain ``title`` and ``published_at`` keys.
        See :meth:`SentimentModel.aggregate_sentiment` for decay details.

        Args:
            symbol: Trading pair in ``BTC/USDT`` format.
            headline_dicts: List of headline dicts from CryptoPanicClient.

        Returns:
            Dict from :meth:`SentimentModel.aggregate_sentiment` with
            ``symbol`` added.
        """
        result = self.sentiment.aggregate_sentiment(headline_dicts)
        result["symbol"] = symbol
        _logger.info(
            "Sentiment %s: composite=%.4f avg_age=%.1fh positive=%.4f negative=%.4f",
            format_pair_for_binance(symbol),
            result["composite_score"],
            result.get("avg_headline_age_hours", 0.0),
            result.get("positive", 0.0),
            result.get("negative", 0.0),
        )
        return result

    def compute_confidence_score(
        self,
        regression_conf: float,
        vol_regime_prob: float,
        sentiment_score: float,
    ) -> float:
        """Combine regression, volatility, and sentiment into one score.

        ``final = (regression_conf * 0.4) + (vol_regime_prob * 0.3) + (abs(sentiment_score) * 0.3)``

        Args:
            regression_conf: Confidence from the direction model (0-1).
            vol_regime_prob: Raw sigmoid probability from the classifier (0-1).
            sentiment_score: Composite sentiment score (-1 to 1).

        Returns:
            Combined confidence score in [0, 1].
        """
        final = (
            regression_conf * 0.4
            + vol_regime_prob * 0.3
            + abs(sentiment_score) * 0.3
        )
        return round(final, 4)

    def run_all(self, pipeline_data: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Run price, volatility, and sentiment predictions for every pair.

        Args:
            pipeline_data: Output from ``DataPipeline.run()``, a dict
                keyed by pair with ``ohlcv_features`` and ``news``.

        Returns:
            Dict keyed by pair with sub-keys ``price``, ``vol_regime``,
            ``sentiment``, and ``combined_confidence``.
        """
        signals: dict[str, dict[str, Any]] = {}
        for pair, data in pipeline_data.items():
            sym = format_pair_for_binance(pair)
            _logger.info("Running predictions for %s", sym)

            price_pred = self.predict_price(pair, data.get("ohlcv_features", pd.DataFrame()))
            vol_pred = self.predict_volatility_regime(pair, data.get("ohlcv_features", pd.DataFrame()))
            sentiment_pred = self.predict_sentiment(pair, data.get("news", []))

            combined_conf = self.compute_confidence_score(
                regression_conf=price_pred.get("confidence", 0.0),
                vol_regime_prob=vol_pred.get("vol_regime_prob", 0.0),
                sentiment_score=sentiment_pred.get("composite_score", 0.0),
            )
            _logger.info(
                "Combined confidence %s: regression=%.4f vol=%.4f sentiment=%.4f final=%.4f",
                sym,
                price_pred.get("confidence", 0.0),
                vol_pred.get("vol_regime_prob", 0.0),
                sentiment_pred.get("composite_score", 0.0),
                combined_conf,
            )

            signals[pair] = {
                "price": price_pred,
                "vol_regime": vol_pred,
                "sentiment": sentiment_pred,
                "combined_confidence": combined_conf,
            }

        return signals
