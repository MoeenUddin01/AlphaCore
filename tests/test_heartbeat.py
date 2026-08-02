"""Tests for the process heartbeat / hang-detection module.

Covers the watchdog-facing heartbeat file: liveness touches, cycle
start/end transitions, staleness detection, and the hang thresholds.
"""

import json
import time
from pathlib import Path

import pytest

from src.utils import heartbeat
from src.utils.heartbeat import (
    CYCLE_MAX_DURATION_S,
    HEARTBEAT_MAX_AGE_S,
    cycle_end,
    cycle_start,
    report,
    stale,
    touch,
)


@pytest.fixture()
def hb_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the heartbeat module at a temp file and return its path."""
    path = tmp_path / "heartbeat.json"
    monkeypatch.setattr(heartbeat, "_HEARTBEAT_FILE", str(path))
    return path


def _write_heartbeat(hb_file: Path, data: dict) -> None:
    hb_file.write_text(json.dumps(data))


class TestHeartbeatLifecycle:
    """Tests for the basic touch / cycle transitions."""

    def test_touch_creates_file(self, hb_file: Path) -> None:
        touch()
        assert hb_file.exists()

    def test_touch_records_last_activity(self, hb_file: Path) -> None:
        touch()
        data = json.loads(hb_file.read_text())
        assert data["last_activity"] > 0
        assert "last_activity_iso" in data

    def test_cycle_start_sets_running(self, hb_file: Path) -> None:
        cycle_start("cyc-1")
        data = json.loads(hb_file.read_text())
        assert data["cycle_state"] == "running"
        assert data["cycle_id"] == "cyc-1"

    def test_cycle_end_returns_to_idle(self, hb_file: Path) -> None:
        cycle_start("cyc-1")
        cycle_end("cyc-1")
        data = json.loads(hb_file.read_text())
        assert data["cycle_state"] == "idle"


class TestStaleDetection:
    """Tests for hang detection used by the watchdog."""

    def test_missing_file_is_stale(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(heartbeat, "_HEARTBEAT_FILE", str(tmp_path / "missing.json"))
        assert stale()

    def test_fresh_heartbeat_is_healthy(self, hb_file: Path) -> None:
        _write_heartbeat(hb_file, {"last_activity": time.time(), "cycle_state": "idle"})
        assert not stale()
        assert report()["healthy"]

    def test_old_heartbeat_is_stale(self, hb_file: Path) -> None:
        _write_heartbeat(
            hb_file,
            {"last_activity": time.time() - HEARTBEAT_MAX_AGE_S - 60, "cycle_state": "idle"},
        )
        assert stale()
        assert not report()["healthy"]

    def test_cycle_started_long_ago_is_stale(self, hb_file: Path) -> None:
        _write_heartbeat(
            hb_file,
            {
                "last_activity": time.time() - 30,
                "cycle_state": "running",
                "cycle_started": time.time() - CYCLE_MAX_DURATION_S - 60,
            },
        )
        assert stale()

    def test_recent_cycle_is_healthy(self, hb_file: Path) -> None:
        _write_heartbeat(
            hb_file,
            {
                "last_activity": time.time() - 30,
                "cycle_state": "running",
                "cycle_started": time.time() - 60,
            },
        )
        assert not stale()


class TestReport:
    """Tests for the report() status snapshot."""

    def test_report_shape(self, hb_file: Path) -> None:
        _write_heartbeat(hb_file, {"last_activity": time.time(), "cycle_state": "idle"})
        snap = report()
        assert "healthy" in snap
        assert "age_s" in snap
        assert "cycle_running" in snap
        assert "cycle_age_s" in snap
        assert "state" in snap

    def test_report_cycle_age_zero_when_idle(self, hb_file: Path) -> None:
        _write_heartbeat(hb_file, {"last_activity": time.time(), "cycle_state": "idle"})
        snap = report()
        assert snap["cycle_running"] is False
        assert snap["cycle_age_s"] == 0

    def test_report_cycle_age_when_running(self, hb_file: Path) -> None:
        started = time.time() - 123
        _write_heartbeat(
            hb_file,
            {"last_activity": time.time(), "cycle_state": "running", "cycle_started": started},
        )
        snap = report()
        assert snap["cycle_running"] is True
        assert 122 <= snap["cycle_age_s"] <= 124
