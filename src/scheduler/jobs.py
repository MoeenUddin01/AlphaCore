"""Scheduled job definitions for the AlphaCore trading system.

Defines the four recurring jobs that APScheduler runs:
    - Trading cycle (1h)
    - Data cache refresh (30m)
    - Health check (5m)
    - Model training (once on startup)
"""

from decimal import Decimal
from typing import Any

from src.agents import run_cycle
from src.data.data_pipeline import DataPipeline
from src.database.connection import check_db_connection, init_db
from src.database.crud import get_portfolio_history, save_cycle, update_positions
from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)


def run_trading_cycle() -> None:
    """Execute one full trading cycle: data → agents → persist.

    Called every hour by APScheduler. Fetches fresh pipeline data,
    runs the LangGraph agent pipeline, and persists the results.
    Never raises — all errors are caught and logged.
    """
    _logger.info("=== TRADING CYCLE START ===")
    try:
        pipeline_data = DataPipeline().run()
        history = get_portfolio_history(limit=1)
        if history:
            portfolio_summary: dict[str, Any] = {
                "total_value": Decimal(str(history[0].get("total_value", 10000))),
            }
        else:
            portfolio_summary = {"total_value": Decimal("10000")}

        final_state = run_cycle(pipeline_data, portfolio_summary)
        cycle_id = save_cycle(final_state)
        update_positions(final_state)

        signals_count = len(final_state.get("signals", []))
        trades_count = len(final_state.get("executed_trades", []))
        ps = final_state.get("portfolio_summary", {})
        portfolio_value = ps.get("total_value", Decimal("0"))

        _logger.info(
            "=== CYCLE %s DONE — signals=%d, trades=%d, portfolio_value=%s ===",
            cycle_id, signals_count, trades_count, portfolio_value,
        )
    except Exception:
        _logger.exception("Trading cycle failed — full traceback below")


def run_data_cache_refresh() -> None:
    """Refresh cached OHLCV data without running agents.

    Called every 30 minutes. Fetches fresh pipeline data which
    automatically writes CSVs to ``data_cache/``. Does not execute
    any trades or persist anything to the database.
    """
    _logger.info("=== DATA CACHE REFRESH START ===")
    try:
        DataPipeline().run()
        _logger.info("=== DATA CACHE REFRESH DONE ===")
    except Exception:
        _logger.exception("Data cache refresh failed — full traceback below")


def health_check_job() -> None:
    """Verify the database connection is alive.

    Called every 5 minutes. Logs OK or FAILED based on the result
    of ``check_db_connection()``.
    """
    ok = check_db_connection()
    if ok:
        _logger.info("=== HEALTH CHECK OK ===")
    else:
        _logger.error("=== HEALTH CHECK FAILED ===")


def run_model_training() -> None:
    """Train two models per trading pair on startup: a direction
    classifier (LSTMModel) and a volatility-regime classifier (LSTMClassifier).

    Fetches 2 years of 1h candles from Yahoo Finance, engineers
    technical features, and creates two binary targets:
      - ``direction``: 1 if the next candle's return >= 0, else 0.
      - ``target_vol_regime``: 1 if the next 4-candle range exceeds
        the rolling 24-candle median range, else 0.
    Features are min-max normalised using training-set statistics,
    chronologically split 80/10/10, and each model is trained for up
    to 50 epochs with early stopping. Scaler parameters saved to
    ``artifacts/`` so the Predictor can normalise at inference time.
    Total training time for all models is logged at the end.

    All model imports are kept local to avoid circular imports at
    module load time.
    """
    _logger.info("=== MODEL TRAINING START ===")
    _logger.info("Initialising database before training")
    try:
        init_db()
    except Exception:
        _logger.exception("Database initialisation failed — aborting training")
        return

    import json
    import time
    from pathlib import Path

    try:
        import torch
        from torch.utils.data import DataLoader

        from src.data.feature_engineer import FeatureEngineer
        from src.data.yahoo_client import YahooClient
        from src.models.lstm_model import LSTMClassifier, LSTMModel, create_sequences
        from src.models.trainer import LSTMClassifierTrainer, LSTMTrainer
        from src.utils.helpers import format_pair_for_binance

        yahoo = YahooClient()
        engineer = FeatureEngineer()

        feature_cols = [
            "rsi", "macd", "macd_signal",
            "bb_upper", "bb_middle", "bb_lower",
            "atr", "ema_20", "ema_50",
            "returns", "log_returns", "volatility",
        ]
        seq_len = 24
        batch_size = 32
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "feature_cols": feature_cols,
            "target_cols": ["direction", "target_vol_regime"],
            "seq_len": seq_len,
            "epochs": 50,
            "batch_size": batch_size,
            "learning_rate": 0.001,
        }
        config_path = artifacts_dir / "training_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        _train_start = time.monotonic()

        for pair in settings.TRADING_PAIRS:
            _logger.info("Training models for %s", pair)
            try:
                ohlcv = yahoo.get_historical_ohlcv(pair, interval="1h", years=2)
                features = engineer.compute_features(ohlcv)
                features["direction"] = (features["close"].pct_change().shift(-1) >= 0).astype(int)
                features = features.dropna()

                if len(features) < seq_len + 10:
                    _logger.warning("Not enough data for %s (%d rows) — skipping", pair, len(features))
                    continue

                total = len(features)
                train_end = int(total * 0.8)
                val_end = int(total * 0.9)

                train_df = features.iloc[:train_end]
                val_df = features.iloc[train_end:val_end]
                test_df = features.iloc[val_end:]

                train_norm, scalers = engineer.normalize_features(train_df, feature_cols)
                val_norm = engineer.apply_scalers(val_df, feature_cols, scalers)
                test_norm = engineer.apply_scalers(test_df, feature_cols, scalers)

                sym_safe = format_pair_for_binance(pair)

                # --- LSTM direction classifier ---
                _logger.info("Training direction model for %s", pair)
                dir_train_ds = create_sequences(train_norm, feature_cols, "direction", seq_len, classification=True)
                dir_val_ds = create_sequences(val_norm, feature_cols, "direction", seq_len, classification=True)
                dir_test_ds = create_sequences(test_norm, feature_cols, "direction", seq_len, classification=True)

                dir_train_loader = DataLoader(dir_train_ds, batch_size=batch_size, shuffle=True)
                dir_val_loader = DataLoader(dir_val_ds, batch_size=batch_size, shuffle=False)
                dir_test_loader = DataLoader(dir_test_ds, batch_size=batch_size, shuffle=False)

                model = LSTMModel(input_size=len(feature_cols))
                trainer = LSTMTrainer(
                    model=model,
                    learning_rate=0.001,
                    checkpoint_dir=settings.MODEL_CHECKPOINT_DIR,
                )
                dir_history = trainer.train(
                    train_loader=dir_train_loader,
                    val_loader=dir_val_loader,
                    epochs=50,
                    symbol=pair,
                )

                dir_test_loss, dir_test_acc = trainer.evaluate(dir_test_loader)

                scaler_path = artifacts_dir / f"scaler_{sym_safe}.json"
                with open(scaler_path, "w") as f:
                    json.dump(scalers, f, indent=2)

                metrics_path = artifacts_dir / f"metrics_{sym_safe}.json"

                up_c = up_t = down_c = down_t = 0
                with torch.no_grad():
                    for batch_f, batch_t in dir_test_loader:
                        preds = model(batch_f).argmax(dim=1)
                        for p, a in zip(preds, batch_t):
                            if a.item() == 1:
                                up_t += 1
                                if p.item() == a.item():
                                    up_c += 1
                            else:
                                down_t += 1
                                if p.item() == a.item():
                                    down_c += 1

                total_test = up_t + down_t
                dir_metrics = {
                    "train_loss": dir_history["train_loss"][-1] if dir_history.get("train_loss") else 0,
                    "val_loss": dir_history["val_loss"][-1] if dir_history.get("val_loss") else 0,
                    "test_loss": dir_test_loss,
                    "test_accuracy_pct": round(dir_test_acc, 2),
                    "up_correct": up_c,
                    "up_total": up_t,
                    "down_correct": down_c,
                    "down_total": down_t,
                    "test_samples": total_test,
                }
                with open(metrics_path, "w") as f:
                    json.dump(dir_metrics, f, indent=2)

                _logger.info(
                    "Direction model for %s — val_loss=%.6f, test_loss=%.6f, test_acc=%.1f%% (%d/%d up, %d/%d down)",
                    pair, dir_metrics["val_loss"], dir_test_loss, dir_test_acc,
                    up_c, up_t, down_c, down_t,
                )

                # --- LSTMClassifier: volatility regime ---
                _logger.info("Training volatility classifier for %s", pair)
                clf_train_ds = create_sequences(train_norm, feature_cols, "target_vol_regime", seq_len, classification=False)
                clf_val_ds = create_sequences(val_norm, feature_cols, "target_vol_regime", seq_len, classification=False)
                clf_test_ds = create_sequences(test_norm, feature_cols, "target_vol_regime", seq_len, classification=False)

                clf_train_loader = DataLoader(clf_train_ds, batch_size=batch_size, shuffle=True)
                clf_val_loader = DataLoader(clf_val_ds, batch_size=batch_size, shuffle=False)
                clf_test_loader = DataLoader(clf_test_ds, batch_size=batch_size, shuffle=False)

                classifier = LSTMClassifier(input_size=len(feature_cols))
                clf_trainer = LSTMClassifierTrainer(
                    model=classifier,
                    learning_rate=0.001,
                    checkpoint_dir=settings.MODEL_CHECKPOINT_DIR,
                )
                clf_history = clf_trainer.train(
                    train_loader=clf_train_loader,
                    val_loader=clf_val_loader,
                    epochs=50,
                    symbol=pair,
                )

                clf_test_loss = clf_trainer.evaluate(clf_test_loader)
                clf_test_acc = clf_trainer.evaluate_accuracy(clf_test_loader)

                clf_metrics_path = artifacts_dir / f"metrics_{sym_safe}_classifier.json"
                clf_metrics = {
                    "train_loss": clf_history["train_loss"][-1] if clf_history.get("train_loss") else 0,
                    "val_loss": clf_history["val_loss"][-1] if clf_history.get("val_loss") else 0,
                    "test_loss": clf_test_loss,
                    "test_accuracy_pct": round(clf_test_acc * 100, 2),
                }
                with open(clf_metrics_path, "w") as f:
                    json.dump(clf_metrics, f, indent=2)

                _logger.info(
                    "Volatility classifier for %s — test_loss=%.6f, test_acc=%.1f%%",
                    pair, clf_test_loss, clf_test_acc * 100,
                )
            except Exception:
                _logger.exception("Training failed for %s — skipping", pair)

        _elapsed = time.monotonic() - _train_start
        _logger.info("=== MODEL TRAINING DONE in %.1fs ===", _elapsed)
    except Exception:
        _logger.exception("Model training job failed — full traceback below")
