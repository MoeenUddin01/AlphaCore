"""AlphaCore Real — separate entry point for real-money trading infrastructure.

This module is **structurally isolated** from the paper/test trading system
(``main.py``).  It operates on its own set of database tables (``real_*``)
and uses its own Binance API credentials.

Modes:

    ``python main_real.py --mode sync``
        Run one read-only account-sync cycle and exit.

    ``python main_real.py --mode daemon``
        Start an APScheduler loop that runs the account-sync job
        every hour (ready for future real trade execution logic).

**No order placement or trade execution is implemented in this phase.**
All Binance API calls are strictly read-only.
"""

from __future__ import annotations

import argparse
import signal
import sys
from typing import Any

from src.database.connection import init_db
from src.utils.logger import get_logger

_logger = get_logger("alphacore.real")


def _print_banner(mode: str) -> None:
    """Print the real-mode startup banner."""
    banner = f"""
{'=' * 60}
  AlphaCore Real — Isolated Real-Money Infrastructure
{'=' * 60}
  Mode          : {mode}
  Read-only     : YES (no order placement)
  Tables        : real_* (isolated from paper/test)
{'=' * 60}
"""
    print(banner, flush=True)


def run_account_sync() -> dict[str, Any]:
    """Execute one read-only account-sync cycle.

    Steps:
        1. Initialise the database (create real_* tables if needed).
        2. Connect to the real Binance account via read-only API.
        3. Pull balances, positions, and current prices.
        4. Persist to ``real_positions`` and ``real_portfolio_snapshots``.
        5. Return a summary dict.

    Returns:
        Dict with keys ``success`` (bool), ``balances`` (dict),
        ``positions_count`` (int), ``total_value`` (Decimal or None),
        and ``sync_id`` (str or None).

    Raises:
        RuntimeError: If the real Binance account is not configured.
    """
    from decimal import Decimal

    from src.data.binance_real_client import BinanceRealClient
    from src.database.real_crud import save_real_sync_snapshot

    init_db()

    _logger.info("Starting real account sync")

    client = BinanceRealClient()

    # --- 1. Ping the API to verify connectivity ---
    server_time = client.get_account_status()
    _logger.info("Real Binance API reachable — server time: %d", server_time)

    # --- 2. Pull all non-zero balances ---
    balances = client.get_account_balances()
    _logger.info("Real account balances: %d non-zero asset(s)", len(balances))
    for asset, amount in sorted(balances.items(), key=lambda x: -float(x[1])):
        if amount > Decimal("0"):
            _logger.info("  %s: %s", asset, amount)

    # --- 3. Derive positions (non-USDT assets with qty > 0) ---
    usdt_balance = balances.get("USDT", Decimal("0"))
    positions_raw: list[dict[str, Any]] = []
    total_positions_value = Decimal("0")

    for asset, qty in balances.items():
        if asset == "USDT" or qty <= Decimal("0"):
            continue

        pair = f"{asset}/USDT"
        try:
            curr_price = client.get_current_price(pair)
        except Exception as exc:
            _logger.warning("Could not fetch price for %s: %s", pair, exc)
            continue

        position_value = qty * curr_price
        total_positions_value += position_value

        positions_raw.append({
            "symbol": pair,
            "quantity": qty,
            "avg_entry_price": curr_price,  # read-only: Binance doesn't expose avg entry via REST
            "current_price": curr_price,
            "unrealised_pnl": Decimal("0"),  # cannot compute without entry price
        })

    total_value = usdt_balance + total_positions_value

    _logger.info(
        "Real account summary — USDT=%.2f positions_value=%.2f total=%.2f positions=%d",
        float(usdt_balance), float(total_positions_value), float(total_value),
        len(positions_raw),
    )

    # --- 4. Persist ---
    sync_id = save_real_sync_snapshot(
        total_value=total_value,
        cash=usdt_balance,
        positions_value=total_positions_value,
        unrealised_pnl=Decimal("0"),
        realised_pnl=Decimal("0"),
        balances=balances,
        positions=positions_raw,
    )

    _logger.info("Real account sync complete — sync_id=%s", sync_id[:8])

    return {
        "success": True,
        "balances": {k: float(v) for k, v in balances.items()},
        "positions_count": len(positions_raw),
        "total_value": float(total_value),
        "sync_id": sync_id,
    }


def _run_sync() -> None:
    """Run one sync cycle and print a summary."""
    _print_banner("sync")
    result = run_account_sync()
    print("\n--- Real Account Sync Summary ---")
    print(f"  Total value : ${result['total_value']:,.2f}")
    print(f"  Positions   : {result['positions_count']}")
    print(f"  Sync ID     : {result['sync_id']}")
    print(f"  Balances    : {result['balances']}")
    print("---")


def _run_daemon() -> None:
    """Start the recurring account-sync daemon."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    _print_banner("daemon")
    _logger.info("Starting real account-sync daemon")

    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        run_account_sync,
        trigger=IntervalTrigger(hours=1),
        id="real_account_sync",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        run_account_sync,
        trigger=IntervalTrigger(minutes=1),
        id="real_account_sync_initial",
        max_instances=1,
        replace_existing=True,
    )
    # Run immediately on startup, then the hourly job takes over
    # (the second "initial" job fires once at the 1-min mark, which
    # ensures we get a snapshot quickly for verification)

    _logger.info("Real daemon jobs registered — running initial sync")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        _logger.info("Real daemon shutting down")


def main() -> None:
    """Parse CLI args and dispatch."""
    parser = argparse.ArgumentParser(
        description="AlphaCore Real — Isolated Real-Money Infrastructure (read-only)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="sync",
        choices=["sync", "daemon"],
        help="Real mode: sync = one cycle, daemon = recurring (default: sync)",
    )
    args = parser.parse_args()

    handlers = {
        "sync": _run_sync,
        "daemon": _run_daemon,
    }

    handler = handlers[args.mode]
    try:
        handler()
    except KeyboardInterrupt:
        _logger.info("Received Ctrl+C — shutting down")
        sys.exit(0)
    except Exception:
        _logger.exception("Unhandled exception in real %s mode — exiting", args.mode)
        sys.exit(1)


if __name__ == "__main__":
    main()
