"""Shared timestamp normalisation for all news source clients.

Every source client returns ``published_at`` in a different format.
This module provides a single ``normalize_timestamp()`` that converts
any common format into a consistent timezone-aware ``datetime`` object,
so that sorting, deduplication, and age calculations work correctly
across all sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

_TIMESTAMP_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S +0000",
    "%Y-%m-%dT%H:%M:%S.%f +0000",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S GMT",
]


def normalize_timestamp(raw: Union[str, int, float, datetime, None]) -> datetime:
    """Convert any common timestamp format to a timezone-aware datetime.

    Handles:
      - ``datetime`` objects (returned as-is if tz-aware, otherwise
        assumed UTC)
      - Unix timestamps as ``int`` or ``float`` (seconds since epoch)
      - ISO 8601 strings with or without ``Z`` / ``+0000`` suffix
      - Common date formats from news APIs
      - ``None`` or empty string → epoch (1970-01-01 UTC)

    Args:
        raw: The raw timestamp value from a news source.

    Returns:
        A timezone-aware ``datetime`` in UTC.
    """
    if raw is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw

    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)

    if not isinstance(raw, str):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    raw = raw.strip()
    if not raw:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    # Handle 'Z' suffix (Python <3.11 can't parse Z directly)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    for fmt in _TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    # Last resort: try dateutil-style parsing
    try:
        from dateutil import parser as _dateutil_parser
        dt = _dateutil_parser.parse(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    return datetime(1970, 1, 1, tzinfo=timezone.utc)
