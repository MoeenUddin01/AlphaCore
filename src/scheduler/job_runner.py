"""APScheduler runner that boots the entire scheduled job system.

Provides a ``SchedulerRunner`` class that initialises the database,
registers all recurring jobs, and handles graceful shutdown on
SIGINT / SIGTERM.
"""

import signal
import sys
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.database.connection import init_db
from src.scheduler.jobs import (
    health_check_job,
    run_data_cache_refresh,
    run_model_training,
    run_trading_cycle,
)
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class SchedulerRunner:
    """Manages the lifecycle of the APScheduler instance.

    Attributes:
        scheduler: Configured :class:`BlockingScheduler` instance.
        _logger: Module-level logger bound to this class.
    """

    def __init__(self) -> None:
        self._logger = get_logger(f"{__name__}.SchedulerRunner")
        self.scheduler: BlockingScheduler = BlockingScheduler(
            timezone="UTC",
        )

    def setup_jobs(self) -> None:
        """Register all recurring jobs with their schedules.

        ``run_model_training`` is deliberately excluded — it is called
        manually once on first run.
        """
        self._logger.info("Registering scheduled jobs")

        self.scheduler.add_job(
            run_trading_cycle,
            trigger=IntervalTrigger(hours=1),
            id="trading_cycle",
            max_instances=1,
            replace_existing=True,
        )

        self.scheduler.add_job(
            run_data_cache_refresh,
            trigger=IntervalTrigger(minutes=30),
            id="cache_refresh",
            replace_existing=True,
        )

        self.scheduler.add_job(
            health_check_job,
            trigger=IntervalTrigger(minutes=5),
            id="health_check",
            replace_existing=True,
        )

        self._logger.info("All recurring jobs registered")

    def start(self) -> None:
        """Initialise the database, log job schedule, and start the scheduler.

        Blocks the current thread until the scheduler is shut down.
        """
        self._logger.info("Initialising database")
        init_db()

        # Skip initial retraining — we already have 10 trained checkpoints
        # from the previous training run. Run one trading cycle immediately
        # to verify Predictor loads all checkpoints.
        self._logger.info("Running initial trading cycle (Predictor init + checkpoint verification)")
        try:
            run_trading_cycle()
        except Exception:
            self._logger.exception("Initial trading cycle failed — continuing")

        self._logger.info("Scheduled jobs:")
        for job in self.scheduler.get_jobs():
            try:
                nrt: Any = job.next_run_time
                next_str = nrt.strftime("%Y-%m-%d %H:%M:%S UTC") if nrt else "not scheduled"
            except AttributeError:
                next_str = "pending"
            self._logger.info("  %-20s next run: %s", job.id, next_str)

        self._logger.info("Starting scheduler (Ctrl+C to stop)")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self._logger.info("Scheduler stopped cleanly")


def main() -> None:
    """Entry point: wire signal handlers, run the scheduler loop."""
    runner = SchedulerRunner()
    runner.setup_jobs()

    def _handle_signal(signum: int, _frame: Any) -> None:
        _logger.info("Received signal %d — shutting down", signum)
        runner.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    runner.start()


if __name__ == "__main__":
    main()
