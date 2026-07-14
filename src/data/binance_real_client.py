"""Read-only Binance real-account client — no trading capability.

Pulls account balances, open orders, and current prices from the
real Binance account using a read-only API key.  This client is
structurally separate from ``binance_client.py`` and is designed
to never place, cancel, or modify any order.

The real API key **must** be created on Binance with only
read-only permissions (no trading, no withdrawal).  This is
enforced at the Binance API key level, not just in code.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from binance.client import Client
from binance.exceptions import BinanceAPIException

from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_REQUIRED_CONFIG_MSG = (
    "Real Binance account sync is not configured. "
    "Set BINANCE_REAL_API_KEY, BINANCE_REAL_API_SECRET, "
    "and BINANCE_REAL_ENABLED=true in .env"
)


class BinanceRealClient:
    """Read-only client for the real Binance account.

    Uses the ``BINANCE_REAL_API_KEY`` / ``BINANCE_REAL_API_SECRET``
    credentials from ``.env``.  All methods are strictly read-only:
    they call ``GET`` endpoints and never create/modify/cancel orders.

    The client logs a warning at init if enabled but the keys look like
    placeholders.  Actual API key values are **never** logged.

    Raises:
        RuntimeError: If ``BINANCE_REAL_ENABLED`` is ``False`` or
            the API credentials are missing/placeholder.
    """

    def __init__(self) -> None:
        if not settings.BINANCE_REAL_ENABLED:
            raise RuntimeError(_REQUIRED_CONFIG_MSG)

        key = settings.BINANCE_REAL_API_KEY
        secret = settings.BINANCE_REAL_API_SECRET

        if not key or not secret or "your_" in key.lower() or "your_" in secret.lower():
            raise RuntimeError(_REQUIRED_CONFIG_MSG)

        self._client = Client(api_key=key, api_secret=secret, testnet=False)
        _logger.info("BinanceRealClient initialised (read-only)")

    def get_account_balances(self) -> dict[str, Decimal]:
        """Fetch all non-zero balances from the real Binance account.

        Calls ``GET /api/v3/account`` (read-only endpoint) and
        filters to assets with free balance > 0.

        Returns:
            Mapping of asset symbol (e.g. ``BTC``, ``USDT``) to
            free balance as a :class:`Decimal`.

        Raises:
            RuntimeError: If the API call fails.
        """
        _logger.info("Fetching real account balances")
        try:
            account = self._client.get_account()
        except BinanceAPIException as exc:
            raise RuntimeError(f"Real account API error: {exc}") from exc

        balances: dict[str, Decimal] = {}
        for bal in account.get("balances", []):
            free = Decimal(bal.get("free", "0"))
            locked = Decimal(bal.get("locked", "0"))
            total = free + locked
            if total > Decimal("0"):
                balances[bal["asset"]] = total

        return balances

    def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Fetch open orders from the real Binance account (read-only).

        Args:
            symbol: Optional trading pair in ``BTCUSDT`` format.
                If ``None``, fetches open orders for all symbols.

        Returns:
            List of raw order dicts from the Binance API.

        Raises:
            RuntimeError: If the API call fails.
        """
        _logger.info("Fetching real account open orders%s", f" for {symbol}" if symbol else " (all)")
        try:
            if symbol:
                return self._client.get_open_orders(symbol=symbol.upper())
            return self._client.get_open_orders()
        except BinanceAPIException as exc:
            raise RuntimeError(f"Real account open orders error: {exc}") from exc

    def get_current_price(self, pair: str) -> Decimal:
        """Fetch the latest ticker price for *pair* from Binance.

        Args:
            pair: Trading pair in ``BTC/USDT`` format.

        Returns:
            Current price as a :class:`Decimal`.

        Raises:
            RuntimeError: If the API call fails.
        """
        symbol = pair.replace("/", "").upper()
        _logger.info("Fetching real account current price for %s", symbol)
        try:
            ticker = self._client.get_symbol_ticker(symbol=symbol)
            return Decimal(ticker["price"])
        except BinanceAPIException as exc:
            raise RuntimeError(f"Real account price error for {symbol}: {exc}") from exc

    def get_account_snapshot(self) -> dict[str, Any]:
        """Fetch a full account snapshot including asset valuation.

        Calls ``GET /sapi/v1/accountSnapshot`` (read-only, requires
        spot snapshot permission on the API key).

        Returns:
            Raw snapshot dict from Binance.  Empty dict on failure
            (the snapshot endpoint may not be available on all keys).

        Raises:
            RuntimeError: If the API call fails.
        """
        _logger.info("Fetching real account snapshot")
        try:
            return self._client.get_account_snapshot(type="SPOT")
        except BinanceAPIException as exc:
            _logger.warning("Account snapshot not available: %s", exc)
            return {}
        except Exception as exc:
            _logger.warning("Account snapshot failed: %s", exc)
            return {}

    def get_account_status(self) -> int:
        """Ping the real account and return the current timestamp.

        Uses ``GET /api/v3/ping`` (no auth required) + ``GET /api/v3/time``
        to verify API connectivity.

        Returns:
            Server timestamp in milliseconds.

        Raises:
            RuntimeError: If the API is unreachable.
        """
        try:
            self._client.ping()
            server_time = self._client.get_server_time()
            return int(server_time["serverTime"])
        except Exception as exc:
            raise RuntimeError(f"Real account API unreachable: {exc}") from exc
