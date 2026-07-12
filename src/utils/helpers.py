"""Shared utility functions for the Autonomous Crypto Quant system.

Provides retry logic, decimal conversion, timestamp handling, pair
formatting, list chunking, and alert webhook posting used across all modules.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from typing import Any, Callable, TypeVar

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

F = TypeVar("F", bound=Callable[..., Any])

_logger = get_logger(__name__)


def retry_with_backoff(
    func: F | None = None,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Callable[..., Any]:
    """Decorator that retries *func* on exception with exponential backoff.

    Args:
        func: The callable to wrap (or ``None`` when used with keyword args).
        max_retries: Maximum number of retry attempts before giving up.
        base_delay: Initial delay in seconds; doubles each attempt.

    Returns:
        Decorated function that retries on failure.

    Raises:
        The last exception raised by *func* after all retries are exhausted.
    """
    if func is None:
        return lambda f: retry_with_backoff(f, max_retries=max_retries, base_delay=base_delay)

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return func(*args, **kwargs)
            except ValueError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    _logger.warning(
                        "%s failed (attempt %d/%d): %s. Retrying in %.2fs…",
                        func.__name__,
                        attempt,
                        max_retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
        assert last_exc is not None
        _logger.error(
            "%s failed after %d attempts: %s",
            func.__name__,
            max_retries,
            last_exc,
        )
        raise last_exc

    return wrapper


def to_decimal(value: Any) -> Decimal:
    """Safely convert *value* to a Decimal with 8 decimal places.

    Args:
        value: Any numeric type (int, float, str, Decimal).

    Returns:
        Decimal rounded to 8 decimal places.

    Raises:
        ValueError: If conversion fails.
    """
    try:
        return Decimal(str(value)).quantize(Decimal("0.00000001"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(
            f"Cannot convert {value!r} ({type(value).__name__}) to Decimal"
        ) from exc


def timestamp_to_datetime(ts: int) -> datetime:
    """Convert a Binance millisecond timestamp to a UTC-aware datetime.

    Args:
        ts: Millisecond timestamp (e.g. ``1700000000000``).

    Returns:
        UTC datetime object.
    """
    return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)


def format_pair_for_binance(pair: str) -> str:
    """Convert ``BTC/USDT`` to ``BTCUSDT``.

    Args:
        pair: Trading pair in ``BASE/QUOTE`` format.

    Returns:
        Pair string without the separator.
    """
    return pair.replace("/", "")


def chunk_list(lst: list, size: int) -> list[list]:
    """Split *lst* into chunks of at most *size* elements each.

    Args:
        lst: The list to split.
        size: Maximum size of each chunk (must be >= 1).

    Returns:
        List of chunks.
    """
    if size < 1:
        raise ValueError(f"Chunk size must be >= 1, got {size}")
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def send_alert(message: str, level: str = "info") -> None:
    """Post *message* to the configured alert webhook (Discord / Telegram).

    Fires and forgets — failures are logged but never re-raised so an
    alert webhook outage never interrupts the trading pipeline.

    Args:
        message: Human-readable alert text.
        level: One of ``"info"``, ``"warning"``, ``"error"``.
    """
    webhook_url = settings.ALERT_WEBHOOK_URL
    if not webhook_url:
        return

    emoji = {"info": "", "warning": "⚠️ ", "error": "🚨 "}.get(level, "")
    payload = {"content": f"{emoji}**AlphaCore [{level.upper()}]**\n{message}"}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        _logger.info("Alert sent (level=%s): %s", level, message[:80])
    except requests.RequestException as exc:
        _logger.warning("Failed to send alert (level=%s): %s", level, exc)
