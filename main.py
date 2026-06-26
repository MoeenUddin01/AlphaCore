"""AlphaCore — autonomous crypto quant trading system.

Single entry point for all system modes:

    ``python main.py --mode train``
        Initialise the database and train LSTM models for all trading
        pairs, then exit.

    ``python main.py --mode trade``
        Scheduler-only mode: run the APScheduler loop (data pipeline
        → ML prediction → agent pipeline → persist).  No API server
        is started — deploy as a separate process on any machine that
        shares the same database.

    ``python main.py --mode api``
        Start only the FastAPI REST API server (no scheduler).

    ``python main.py --mode dashboard``
        Launch the Streamlit dashboard.
"""

import argparse
import os
import sys
import uvicorn

from src.database.connection import init_db
from src.scheduler.job_runner import SchedulerRunner
from src.scheduler.jobs import run_model_training
from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger("alphacore.main")


def _print_banner(mode: str) -> None:
    """Print the system startup banner to stdout."""
    banner = f"""
{'=' * 60}
  AlphaCore — Autonomous Crypto Quant System
{'=' * 60}
  Mode          : {mode}
  Trading pairs : {', '.join(settings.TRADING_PAIRS)}
  Initial cap   : ${settings.PORTFOLIO_INITIAL_CAPITAL:,.2f}
  Testnet       : {'YES' if settings.BINANCE_TESTNET else 'NO'}
{'=' * 60}
"""
    print(banner, flush=True)


def _run_train() -> None:
    """Train LSTM models and exit."""
    _logger.info("Starting in TRAIN mode")
    _print_banner("train")
    init_db()
    run_model_training()
    _logger.info("Training complete — exiting")


def _run_trade() -> None:
    """Scheduler-only: start the trading cycle loop (no API server)."""
    _logger.info("Starting in TRADE mode")
    _print_banner("trade")
    init_db()

    runner = SchedulerRunner()
    runner.setup_jobs()
    runner.start()


def _run_api() -> None:
    """Start only the FastAPI server (blocks)."""
    _logger.info("Starting in API mode")
    _print_banner("api")
    init_db()
    uvicorn.run(
        app="src.api.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


def _run_dashboard() -> None:
    """Launch the Streamlit dashboard."""
    _logger.info("Starting in DASHBOARD mode")
    _print_banner("dashboard")
    ret = os.system("streamlit run src/dashboard/app.py")
    if ret != 0:
        _logger.error("Streamlit exited with code %d", ret)
        sys.exit(ret)


def main() -> None:
    """Parse CLI args and dispatch to the selected mode."""
    parser = argparse.ArgumentParser(
        description="AlphaCore — Autonomous Crypto Quant Trading System",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="trade",
        choices=["train", "trade", "api", "dashboard"],
        help="System mode (default: trade)",
    )
    args = parser.parse_args()

    mode_handlers = {
        "train": _run_train,
        "trade": _run_trade,
        "api": _run_api,
        "dashboard": _run_dashboard,
    }

    handler = mode_handlers[args.mode]
    try:
        handler()
    except KeyboardInterrupt:
        _logger.info("Received Ctrl+C — shutting down")
        sys.exit(0)
    except Exception:
        _logger.exception("Unhandled exception in %s mode — exiting", args.mode)
        sys.exit(1)


if __name__ == "__main__":
    main()
