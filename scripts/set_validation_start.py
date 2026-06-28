"""RS01 — Set validation_start_date to now, resetting the sentiment trade counter.

Usage:
    python scripts/set_validation_start.py
"""

from datetime import datetime
from decimal import Decimal

from src.database.connection import get_db
from src.database.models import PortfolioState


def set_validation_start() -> None:
    with get_db() as db:
        pstate = db.query(PortfolioState).filter(PortfolioState.id == "singleton").first()
        if pstate is None:
            pstate = PortfolioState(
                id="singleton",
                peak_value=Decimal("0"),
                updated_at=datetime.utcnow(),
            )
            db.add(pstate)

        pstate.validation_start_date = datetime.utcnow()
        db.commit()

        print(f"validation_start_date set to: {pstate.validation_start_date}")
        return pstate.validation_start_date


if __name__ == "__main__":
    print("Setting validation_start_date to now...")
    dt = set_validation_start()
    print(f"Done. Trades created before {dt} will be excluded from sentiment validation.")
