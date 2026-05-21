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
    """Train LSTM models for every trading pair on startup.

    Runs once when the scheduler starts. For each symbol in
    ``TRADING_PAIRS``: fetches 1000 1h candles, engineers features,
    creates an LSTMDataset with sequence length 24, splits 80/10/10,
    and trains for 50 epochs. Logs the final validation loss per
    symbol.

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

    try:
        from torch.utils.data import DataLoader, random_split

        from src.data.binance_client import BinanceClient
        from src.data.feature_engineer import FeatureEngineer
        from src.models.lstm_model import LSTMModel, create_sequences
        from src.models.trainer import LSTMTrainer

        binance = BinanceClient()
        engineer = FeatureEngineer()

        feature_cols = [
            "rsi", "macd", "macd_signal",
            "bb_upper", "bb_middle", "bb_lower",
            "atr", "ema_20", "ema_50",
            "returns", "log_returns", "volatility",
        ]
        target_col = "close"
        seq_len = 24
        batch_size = 32

        for pair in settings.TRADING_PAIRS:
            _logger.info("Training model for %s", pair)
            try:
                ohlcv = binance.get_ohlcv(pair, interval="1h", limit=1000)
                features = engineer.compute_features(ohlcv)

                if len(features) < seq_len + 10:
                    _logger.warning(
                        "Not enough data for %s (%d rows) — skipping",
                        pair, len(features),
                    )
                    continue

                dataset = create_sequences(
                    df=features,
                    feature_cols=feature_cols,
                    target_col=target_col,
                    seq_len=seq_len,
                )

                total = len(dataset)
                train_len = int(total * 0.8)
                val_len = int(total * 0.1)
                test_len = total - train_len - val_len

                train_ds, val_ds, _ = random_split(
                    dataset, [train_len, val_len, test_len],
                )

                train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
                val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

                model = LSTMModel(input_size=len(feature_cols))
                trainer = LSTMTrainer(
                    model=model,
                    learning_rate=0.001,
                    checkpoint_dir=settings.MODEL_CHECKPOINT_DIR,
                )
                history = trainer.train(
                    train_loader=train_loader,
                    val_loader=val_loader,
                    epochs=50,
                    symbol=pair,
                )

                val_losses = history.get("val_loss", [])
                if val_losses:
                    _logger.info(
                        "Training complete for %s — final val loss: %.6f",
                        pair, val_losses[-1],
                    )
            except Exception:
                _logger.exception("Training failed for %s — skipping", pair)

        _logger.info("=== MODEL TRAINING DONE ===")
    except Exception:
        _logger.exception("Model training job failed — full traceback below")
