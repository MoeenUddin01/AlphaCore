"""Standalone entry point: run one trading cycle and exit.

Used by GitHub Actions (scheduled or manual trigger).
Not a long-running process — starts, runs one cycle, stops.
"""

import os
from pathlib import Path

from src.database.connection import init_db
from src.scheduler.jobs import run_trading_cycle
from src.utils.config import settings


def main() -> None:
    Path(settings.DATA_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    init_db()
    run_trading_cycle()


if __name__ == "__main__":
    main()
