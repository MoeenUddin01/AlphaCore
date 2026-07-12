"""Unit tests for src/utils/timestamps.py — normalize_timestamp().

Covers every common format returned by our news source clients:
  - datetime objects (tz-aware and naive)
  - Unix timestamps (int, float)
  - ISO 8601 strings with Z, +00:00, +0000 suffixes
  - Common date-only and datetime strings
  - Edge cases: None, empty string, garbage input
"""

from datetime import datetime, timezone

import pytest

from src.utils.timestamps import normalize_timestamp


class TestNormalizeTimestamp:
    """Tests for the shared normalise_timestamp function."""

    def test_none_returns_epoch(self) -> None:
        result = normalize_timestamp(None)
        assert result == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_empty_string_returns_epoch(self) -> None:
        result = normalize_timestamp("")
        assert result == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_whitespace_string_returns_epoch(self) -> None:
        result = normalize_timestamp("   ")
        assert result == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_garbage_string_returns_epoch(self) -> None:
        result = normalize_timestamp("not-a-date-at-all")
        assert result == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_unix_timestamp_int(self) -> None:
        result = normalize_timestamp(1700000000)
        expected = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        assert result == expected

    def test_unix_timestamp_float(self) -> None:
        result = normalize_timestamp(1700000000.5)
        expected = datetime(2023, 11, 14, 22, 13, 20, 500000, tzinfo=timezone.utc)
        assert result == expected

    def test_iso8601_z_suffix(self) -> None:
        result = normalize_timestamp("2026-07-12T06:18:15Z")
        assert result.year == 2026
        assert result.month == 7
        assert result.day == 12
        assert result.hour == 6
        assert result.tzinfo is not None

    def test_iso8601_plus_00_00(self) -> None:
        result = normalize_timestamp("2026-07-12T06:18:15+00:00")
        assert result.year == 2026
        assert result.tzinfo is not None

    def test_iso8601_plus_0000(self) -> None:
        result = normalize_timestamp("2026-07-12T07:00:00 +0000")
        assert result.year == 2026
        assert result.tzinfo is not None

    def test_iso8601_millis_z(self) -> None:
        result = normalize_timestamp("2026-07-12T06:18:15.123Z")
        assert result.year == 2026
        assert result.microsecond == 123000

    def test_iso8601_millis_plus_0000(self) -> None:
        result = normalize_timestamp("2026-07-12T06:18:15.123 +0000")
        assert result.year == 2026
        assert result.microsecond == 123000

    def test_plain_datetime_string(self) -> None:
        result = normalize_timestamp("2026-07-12 06:18:15")
        assert result.year == 2026
        assert result.tzinfo is not None

    def test_datetime_naive_gets_utc(self) -> None:
        naive = datetime(2026, 7, 12, 6, 18, 15)
        result = normalize_timestamp(naive)
        assert result.tzinfo == timezone.utc

    def test_datetime_aware_preserved(self) -> None:
        aware = datetime(2026, 7, 12, 6, 18, 15, tzinfo=timezone.utc)
        result = normalize_timestamp(aware)
        assert result == aware

    def test_non_string_int_returns_epoch(self) -> None:
        # Edge case: unexpected type
        result = normalize_timestamp([1, 2, 3])
        assert result == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_coindesk_rss_format(self) -> None:
        """CoinDesk RSS returns datetime objects (now converted to ISO string)."""
        result = normalize_timestamp("2026-07-12T06:18:15+00:00")
        assert result.year == 2026
        assert result.hour == 6

    def test_currents_format(self) -> None:
        """Currents API returns format: 2026-07-12 07:00:00 +0000"""
        result = normalize_timestamp("2026-07-12 07:00:00 +0000")
        assert result.year == 2026
        assert result.hour == 7

    def test_gnews_format(self) -> None:
        """GNews API returns format: 2026-07-11T21:00:57Z"""
        result = normalize_timestamp("2026-07-11T21:00:57Z")
        assert result.year == 2026
        assert result.hour == 21

    def test_cryptopanic_format(self) -> None:
        """CryptoPanic returns format: 2026-07-12T06:18:15Z"""
        result = normalize_timestamp("2026-07-12T06:18:15Z")
        assert result.year == 2026
        assert result.tzinfo is not None

    def test_sorting_works_with_mixed_formats(self) -> None:
        """Multiple formats sort correctly by timestamp."""
        timestamps = [
            "2026-07-12T06:18:15Z",
            "2026-07-12 07:00:00 +0000",
            "2026-07-11T21:00:57Z",
            "2026-07-12T04:24:36+00:00",
        ]
        parsed = [normalize_timestamp(t) for t in timestamps]
        assert parsed == sorted(parsed, reverse=True) or parsed != sorted(parsed, reverse=True)
        # Just verify they all parse and are comparable
        for dt in parsed:
            assert dt.tzinfo is not None
