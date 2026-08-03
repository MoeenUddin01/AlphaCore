"""Process heartbeat for external watchdog detection of hung jobs.

The trade/scheduler process writes a JSON heartbeat file on every
scheduled job activity and on cycle start/end. The ``watchdog.sh``
script reads this file: if the heartbeat goes stale or a trading cycle
stays in ``running`` state beyond the expected duration, the process is
restarted instead of being left to freeze silently.

The file is deliberately a plain JSON blob written atomically so the
watchdog (a separate shell process) can read it safely. Every write
also stamps the writer's ``pid``, letting the watchdog distinguish the
actively-heartbeating process from stale/dead instances.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_HEARTBEAT_FILE = f"{settings.DATA_CACHE_DIR}/.trade_heartbeat.json"

# A healthy trading cycle completes in well under 2 minutes. If a cycle
# is still marked "running" after this long, treat the process as hung.
CYCLE_MAX_DURATION_S = 600  # 10 minutes

# If no job activity at all for this long, the scheduler is frozen
# (health check runs every 5 min, so this is 3 missed ticks).
HEARTBEAT_MAX_AGE_S = 900  # 15 minutes


def _read() -> dict[str, Any]:
    """Return the current heartbeat dict, or an empty dict if unreadable."""
    try:
        with open(_HEARTBEAT_FILE, "r") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def _write(data: dict[str, Any]) -> None:
    """Atomically write *data* to the heartbeat file (tmp + rename).

    Always stamps the writing process's PID into the file so the
    watchdog can tell which instance actually owns the heartbeat and
    must never be killed in favour of a stale zombie.
    """
    data["pid"] = os.getpid()
    tmp = f"{_HEARTBEAT_FILE}.tmp"
    try:
        os.makedirs(settings.DATA_CACHE_DIR, exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, _HEARTBEAT_FILE)
    except OSError as exc:
        _logger.warning("Failed to write heartbeat file: %s", exc)


def touch() -> None:
    """Mark that the scheduler is alive (job activity occurred)."""
    data = _read()
    data["last_activity"] = time.time()
    data["last_activity_iso"] = datetime.now(timezone.utc).isoformat()
    _write(data)


def cycle_start(cycle_id: str) -> None:
    """Mark that a trading cycle has started running.

    Args:
        cycle_id: Unique id of the cycle being started.
    """
    data = _read()
    data["cycle_id"] = cycle_id
    data["cycle_started"] = time.time()
    data["cycle_started_iso"] = datetime.now(timezone.utc).isoformat()
    data["cycle_state"] = "running"
    data["last_activity"] = time.time()
    data["last_activity_iso"] = datetime.now(timezone.utc).isoformat()
    _write(data)
    _logger.debug("Heartbeat: cycle %s started", cycle_id)


def cycle_end(cycle_id: str) -> None:
    """Mark that a trading cycle finished (successfully or not).

    Args:
        cycle_id: Unique id of the cycle that finished.
    """
    data = _read()
    data["cycle_id"] = cycle_id
    data["cycle_ended"] = time.time()
    data["cycle_ended_iso"] = datetime.now(timezone.utc).isoformat()
    data["cycle_state"] = "idle"
    data["last_activity"] = time.time()
    data["last_activity_iso"] = datetime.now(timezone.utc).isoformat()
    _write(data)
    _logger.debug("Heartbeat: cycle %s ended", cycle_id)


def report() -> dict[str, Any]:
    """Return a human/script-readable status snapshot of the heartbeat.

    Returns:
        Dict with ``healthy``, ``age_s``, ``cycle_running``,
        ``cycle_age_s``, and the raw ``state``.
    """
    state = _read()
    now = time.time()
    last_activity = state.get("last_activity", 0)
    age_s = now - last_activity
    cycle_running = state.get("cycle_state") == "running"
    cycle_started = state.get("cycle_started", 0)
    cycle_age_s = now - cycle_started if cycle_running else 0
    return {
        "healthy": (
            age_s <= HEARTBEAT_MAX_AGE_S
            and not (cycle_running and cycle_age_s > CYCLE_MAX_DURATION_S)
        ),
        "age_s": age_s,
        "cycle_running": cycle_running,
        "cycle_age_s": cycle_age_s,
        "state": state,
    }


def stale() -> bool:
    """Return True if the process should be considered hung.

    True when either the heartbeat is older than ``HEARTBEAT_MAX_AGE_S``
    or a cycle has been running longer than ``CYCLE_MAX_DURATION_S``.
    """
    return not report()["healthy"]
