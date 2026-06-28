"""R09 + R10 — Backfill artifact Trade.pnl and recompute all PortfolioSnapshots.

Usage:
    python scripts/backfill_pnl.py
"""

from decimal import Decimal
from datetime import datetime

from src.database.connection import get_db
from src.database.models import Trade, PortfolioSnapshot
from sqlalchemy import text


def backfill_artifacts() -> list[dict]:
    """Backfill 9 artifact SELL trades with real PnL = (sell_price - avg_entry) * qty.

    All 9 artifact BTC SELLs share the same single BTC BUY at avg_entry=$63,704.29.
    No fees were recorded for artifact trades.
    """
    BTC_AVG_ENTRY = Decimal("63704.29")

    with get_db() as db:
        artifacts = (
            db.query(Trade)
            .filter(
                Trade.is_pre_fix_artifact == True,
                Trade.side == "SELL",
                Trade.status == "FILLED",
            )
            .order_by(Trade.created_at)
            .all()
        )

        print(f"Found {len(artifacts)} artifact trades to backfill")

        results = []
        for t in artifacts:
            qty = t.executed_quantity
            price = t.executed_price
            pnl = (price - BTC_AVG_ENTRY) * qty
            old_pnl = t.pnl
            t.pnl = pnl
            results.append({
                "id": str(t.id)[:8],
                "qty": qty,
                "price": price,
                "old_pnl": old_pnl,
                "new_pnl": pnl,
            })
            print(f"  {str(t.id)[:8]} qty={qty} price={price} pnl: {old_pnl} -> {pnl}")

        db.commit()

        # Verify
        total = (
            db.query(Trade.pnl)
            .filter(
                Trade.status == "FILLED",
                Trade.side == "SELL",
                Trade.pnl.isnot(None),
            )
            .all()
        )
        grand_total = sum((r[0] or Decimal("0")) for r in total)
        print(f"\nSUM(Trade.pnl) for ALL FILLED SELLs after backfill: {grand_total}")

    return results


def recompute_snapshots() -> None:
    """R10 — Recompute every PortfolioSnapshot.realised_pnl from Trade.pnl.

    For each snapshot ordered chronologically, realised_pnl = SUM(Trade.pnl)
    for all FILLED SELLs with created_at <= snapshot.created_at.
    """
    with get_db() as db:
        snapshots = (
            db.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.created_at)
            .all()
        )

        print(f"\nRecomputing {len(snapshots)} snapshots...")

        for snap in snapshots:
            total = (
                db.query(Trade.pnl)
                .filter(
                    Trade.status == "FILLED",
                    Trade.side == "SELL",
                    Trade.pnl.isnot(None),
                    Trade.created_at <= snap.created_at,
                )
                .all()
            )
            new_realised = sum((r[0] or Decimal("0")) for r in total)
            old_realised = snap.realised_pnl
            snap.realised_pnl = new_realised
            print(
                f"  {str(snap.cycle_id)[:8]:<10} {str(snap.created_at)[:22]:<24} "
                f"realised_pnl: {old_realised} -> {new_realised}"
            )

        db.commit()

    # Final verification
    with get_db() as db:
        final_snap = (
            db.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.created_at.desc())
            .first()
        )
        final_trades = (
            db.query(Trade.pnl)
            .filter(
                Trade.status == "FILLED",
                Trade.side == "SELL",
                Trade.pnl.isnot(None),
            )
            .all()
        )
        grand_total = sum((r[0] or Decimal("0")) for r in final_trades)
        print(f"\nFinal verification:")
        print(f"  Latest snapshot realised_pnl: {final_snap.realised_pnl}")
        print(f"  SUM(Trade.pnl) all SELLs:      {grand_total}")
        print(f"  Match: {final_snap.realised_pnl == grand_total}")


if __name__ == "__main__":
    print("=" * 60)
    print("R09 — Backfilling 9 artifact trades with real PnL")
    print("=" * 60)
    backfill_artifacts()

    print("\n" + "=" * 60)
    print("R10 — Recomputing all PortfolioSnapshot rows from Trade.pnl")
    print("=" * 60)
    recompute_snapshots()

    print("\nDone.")
