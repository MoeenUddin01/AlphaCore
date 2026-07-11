"""Fake Binance client — no network, deterministic prices, filters, and order tracking.

Provides a drop-in replacement for ``BinanceClient`` that agent tests can
configure per-test case.  ``FakeOrderClient`` (``._client``) is a
``unittest.mock.MagicMock`` so tests can assert ``create_order`` call
counts, side effects, and return values.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock


class FakeBinanceClient:
    """No-network Binance client for agent isolation tests.

    Configure per-test by setting instance attributes before use.
    ``self._prices`` is a ``{symbol: Decimal}`` dict that
    ``get_current_price`` consults.  ``self._filters[key]`` overrides the
    default LOT_SIZE / MIN_NOTIONAL filter dict for a given symbol.
    ``self._client`` is a MagicMock that records every ``create_order``
    call — set its ``return_value`` or ``side_effect`` as needed.
    """

    def __init__(self) -> None:
        self._prices: dict[str, Decimal] = {}
        self._filters: dict[str, dict[str, dict[str, Decimal]]] = {}
        self._order_call_count: int = 0
        self._client = MagicMock()
        self._client.create_order.side_effect = self._record_call

    def _record_call(self, **kwargs: Any) -> Any:
        """Called by MagicMock every time create_order is invoked.

        Increments the call counter and returns the default return_value.
        Subclasses can override this to implement per-symbol behaviour.
        """
        self._order_call_count += 1
        return self._client.create_order.return_value

    def get_current_price(self, symbol: str) -> Decimal:
        return self._prices.get(symbol, Decimal("100"))

    def get_symbol_filters(self, symbol: str) -> dict:
        return self._filters.get(symbol, {
            "lot_size": {"stepSize": Decimal("0.00001")},
            "min_notional": {"minNotional": Decimal("10")},
        })
