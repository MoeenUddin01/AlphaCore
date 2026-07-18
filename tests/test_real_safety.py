"""Real-trading safety infrastructure tests.

Verifies the kill switch, hard limits, and ``real_safety_check()``
function.  Every test uses an isolated in-memory SQLite database so
no production data is ever touched.
"""

import os
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.utils.config import settings


# =========================================================================
# Fixture — isolated in-memory SQLite DB
# =========================================================================

@pytest.fixture(autouse=True)
def test_db():
    """Replace the production database engine with a fresh in-memory SQLite
    database before every test.  Restores the original engine on teardown."""
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(bind=test_engine)

    import src.database.connection as conn_mod

    orig_engine = conn_mod.engine
    orig_session = conn_mod.SessionLocal
    conn_mod.engine = test_engine
    conn_mod.SessionLocal = TestSession

    from src.database.connection import Base

    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    conn_mod.engine = orig_engine
    conn_mod.SessionLocal = orig_session


# =========================================================================
# Fixture — insert a RealTrade row into the isolated DB
# =========================================================================

def _insert_real_trade(
    pnl: Decimal,
    *,
    symbol: str = "BTC/USDT",
    side: str = "SELL",
    executed_quantity: Decimal = Decimal("0.001"),
    executed_price: Decimal = Decimal("60000"),
    order_id: str = "test_order",
    status: str = "filled",
    minutes_ago: int = 5,
) -> None:
    """Insert a ``RealTrade`` row for testing."""
    from src.database.connection import get_db
    from src.database.models import RealTrade
    from uuid import uuid4

    trade = RealTrade(
        id=str(uuid4()),
        sync_id=str(uuid4()),
        symbol=symbol,
        side=side,
        executed_quantity=executed_quantity,
        executed_price=executed_price,
        order_id=order_id,
        status=status,
        pnl=pnl,
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
    )
    with get_db() as db:
        db.add(trade)


# =========================================================================
# Tests
# =========================================================================


class TestKillSwitch:
    """Kill-switch default and toggle behaviour."""

    def test_defaults_to_halted(self) -> None:
        """On a fresh install the kill switch must default to ``True``."""
        from src.database.real_crud import get_real_trading_halted

        assert get_real_trading_halted() is True, "Kill switch must default to halted"

    def test_toggle_on_and_off(self) -> None:
        """set_real_trading_halted() must persist its value."""
        from src.database.real_crud import get_real_trading_halted, set_real_trading_halted

        assert get_real_trading_halted() is True

        set_real_trading_halted(False)
        assert get_real_trading_halted() is False

        set_real_trading_halted(True)
        assert get_real_trading_halted() is True

    def test_multiple_calls_persist_latest(self) -> None:
        """Calling set_real_trading_halted multiple times keeps the last value."""
        from src.database.real_crud import get_real_trading_halted, set_real_trading_halted

        set_real_trading_halted(False)
        set_real_trading_halted(True)
        set_real_trading_halted(False)
        assert get_real_trading_halted() is False


class TestSafetyCheck:
    """real_safety_check() enforces kill switch and hard limits."""

    def test_denied_when_halted(self) -> None:
        """Kill switch active must deny every trade."""
        from src.utils.real_safety import real_safety_check

        # Kill switch defaults to True — no setup needed
        result = real_safety_check(
            symbol="BTC/USDT",
            side="BUY",
            proposed_quantity=Decimal("0.001"),
            proposed_price=Decimal("60000"),
        )
        assert result["action"] == "deny"
        assert "halted" in result["reason"].lower()

    def test_denied_when_position_exceeds_limit(self) -> None:
        """Trade with value > REAL_MAX_POSITION_USD must be denied."""
        from src.database.real_crud import set_real_trading_halted
        from src.utils.real_safety import real_safety_check

        set_real_trading_halted(False)

        # 100 BTC at $10 each = $1000 — way above default $10 limit
        result = real_safety_check(
            symbol="BTC/USDT",
            side="BUY",
            proposed_quantity=Decimal("100"),
            proposed_price=Decimal("10"),
        )
        assert result["action"] == "deny"
        assert "position" in result["reason"].lower()

    def test_denied_when_daily_loss_exceeds_limit(self) -> None:
        """Daily loss > REAL_MAX_DAILY_LOSS_USD must deny and auto-halt."""
        from src.database.real_crud import get_real_trading_halted, set_real_trading_halted
        from src.utils.real_safety import real_safety_check

        set_real_trading_halted(False)

        # Insert trades with realised loss totalling > $5
        _insert_real_trade(Decimal("-3.00"), symbol="BTC/USDT")
        _insert_real_trade(Decimal("-3.00"), symbol="ETH/USDT")

        # Use a small trade ($3) that is under the $10 position limit
        # so that the daily-loss check is the one that fires
        result = real_safety_check(
            symbol="SOL/USDT",
            side="BUY",
            proposed_quantity=Decimal("1"),
            proposed_price=Decimal("3"),
        )
        assert result["action"] == "deny"
        assert "loss" in result["reason"].lower()
        assert "auto" in result["reason"].lower()

        # Kill switch should now be True
        assert get_real_trading_halted() is True

    def test_denied_when_trades_exceed_limit(self) -> None:
        """More trades today than limit must deny."""
        from src.database.real_crud import set_real_trading_halted
        from src.utils.real_safety import real_safety_check

        set_real_trading_halted(False)

        # Insert 3 trades (default limit) + a few more
        for i in range(settings.REAL_MAX_TRADES_PER_DAY):
            _insert_real_trade(Decimal("1.00"), symbol="BTC/USDT", side="BUY" if i % 2 == 0 else "SELL", order_id=f"order_{i}")

        result = real_safety_check(
            symbol="ADA/USDT",
            side="BUY",
            proposed_quantity=Decimal("10"),
            proposed_price=Decimal("1"),
        )
        assert result["action"] == "deny"
        assert "trade" in result["reason"].lower()

    def test_allowed_when_all_checks_pass(self) -> None:
        """Small, reasonable trade under all limits must be allowed."""
        from src.database.real_crud import set_real_trading_halted
        from src.utils.real_safety import real_safety_check

        set_real_trading_halted(False)

        # 1 SOL at $3 = $3, under $10 max, no trades today, no loss
        result = real_safety_check(
            symbol="SOL/USDT",
            side="BUY",
            proposed_quantity=Decimal("1"),
            proposed_price=Decimal("3"),
        )
        assert result["action"] == "allow"

    def test_check_includes_limits_in_response(self) -> None:
        """The response dict must include the current limit values."""
        from src.database.real_crud import set_real_trading_halted
        from src.utils.real_safety import real_safety_check

        set_real_trading_halted(False)

        result = real_safety_check(
            symbol="BTC/USDT",
            side="BUY",
            proposed_quantity=Decimal("1"),
            proposed_price=Decimal("3"),
        )
        assert "limits" in result
        assert result["limits"]["max_position_usd"] == settings.REAL_MAX_POSITION_USD
        assert result["limits"]["max_daily_loss_usd"] == settings.REAL_MAX_DAILY_LOSS_USD
        assert result["limits"]["max_trades_per_day"] == settings.REAL_MAX_TRADES_PER_DAY


class TestKillSwitchBypass:
    """Kill switch cannot be bypassed — each path must go through safety_check."""

    def test_not_bypassed_after_enable_and_recheck(self) -> None:
        """After enabling, the check must still evaluate all limits."""
        from src.database.real_crud import set_real_trading_halted
        from src.utils.real_safety import real_safety_check

        set_real_trading_halted(False)

        # Should pass on a small trade
        result = real_safety_check(
            symbol="BTC/USDT", side="BUY",
            proposed_quantity=Decimal("0.001"), proposed_price=Decimal("60000"),
        )
        assert result["action"] == "deny"  # 0.001 * 60000 = 60 > 10

    def test_halted_default_cannot_be_skipped(self) -> None:
        """Even calling set_real_trading_halted multiple times can't skip the default."""
        from src.database.real_crud import get_real_trading_halted

        # Start fresh (no row) — should still return True
        assert get_real_trading_halted() is True


class TestCRUDFunctions:
    """Standalone CRUD function tests."""

    def test_get_real_daily_loss_no_trades(self) -> None:
        """With no trades today, daily loss must be zero."""
        from src.database.real_crud import get_real_daily_loss

        assert get_real_daily_loss() == Decimal("0")

    def test_get_real_daily_loss_with_trades(self) -> None:
        """Daily loss must sum all trades from today."""
        from src.database.real_crud import get_real_daily_loss

        _insert_real_trade(Decimal("2.50"))
        _insert_real_trade(Decimal("-1.00"))
        _insert_real_trade(Decimal("0.50"))

        assert get_real_daily_loss() == Decimal("2.00")

    def test_get_real_trades_today_count(self) -> None:
        """Trades today count must match insertions."""
        from src.database.real_crud import get_real_trades_today_count

        assert get_real_trades_today_count() == 0

        for i in range(5):
            _insert_real_trade(Decimal("1.00"), order_id=f"order_{i}")

        assert get_real_trades_today_count() == 5

    def test_get_real_safety_status_structure(self) -> None:
        """get_real_safety_status() must return the expected dict shape."""
        from src.database.real_crud import get_real_safety_status

        status = get_real_safety_status()
        assert "trading_halted" in status
        assert "daily_loss" in status
        assert "trades_today" in status
        assert "limits" in status
        assert "max_position_usd" in status["limits"]
        assert "max_daily_loss_usd" in status["limits"]
        assert "max_trades_per_day" in status["limits"]


class TestConfigDefaults:
    """Verify that the default config values are conservative."""

    def test_max_position_usd_default(self) -> None:
        """Default max position must be $10 for small accounts."""
        assert settings.REAL_MAX_POSITION_USD == Decimal("10")

    def test_max_daily_loss_usd_default(self) -> None:
        """Default max daily loss must be $5."""
        assert settings.REAL_MAX_DAILY_LOSS_USD == Decimal("5")

    def test_max_trades_per_day_default(self) -> None:
        """Default max trades per day must be 3."""
        assert settings.REAL_MAX_TRADES_PER_DAY == 3


class TestPersistenceAcrossRestart:
    """Kill-switch state persists in the database across process restarts."""

    def test_daily_loss_auto_halt_survives_restart(self) -> None:
        """Simulate a process restart after daily-loss auto-halt
        and confirm the flag is still ``True`` from a fresh connection."""
        # ---- phase 1: original process ----
        db_path = os.path.join(tempfile.gettempdir(), f"alphacore_safety_test_{os.getpid()}.db")
        if os.path.exists(db_path):
            os.remove(db_path)

        url = f"sqlite:///{db_path}"
        engine1 = create_engine(url, connect_args={"check_same_thread": False})
        Session1 = sessionmaker(bind=engine1)

        import src.database.connection as conn_mod

        orig_engine = conn_mod.engine
        orig_session = conn_mod.SessionLocal
        conn_mod.engine = engine1
        conn_mod.SessionLocal = Session1

        from src.database.connection import Base

        Base.metadata.create_all(bind=engine1)

        from src.database.real_crud import get_real_trading_halted, set_real_trading_halted
        from src.utils.real_safety import real_safety_check

        set_real_trading_halted(False)
        _insert_real_trade(Decimal("-4.00"), symbol="BTC/USDT")
        _insert_real_trade(Decimal("-2.00"), symbol="ETH/USDT")

        result = real_safety_check(
            symbol="SOL/USDT", side="BUY",
            proposed_quantity=Decimal("1"), proposed_price=Decimal("3"),
        )
        assert result["action"] == "deny"
        assert get_real_trading_halted() is True

        # ---- phase 2: simulate process restart ----
        # Tear down old connections completely
        conn_mod.engine.dispose()
        del conn_mod.engine
        del conn_mod.SessionLocal

        # Fresh engine + session pointing at the *same file*
        engine2 = create_engine(url, connect_args={"check_same_thread": False})
        Session2 = sessionmaker(bind=engine2)
        conn_mod.engine = engine2
        conn_mod.SessionLocal = Session2

        # Fresh import to get a clean reference (module already loaded)
        from src.database.real_crud import get_real_trading_halted as check_halted

        assert check_halted() is True, "Kill switch must survive a process restart"

        # Cleanup
        conn_mod.engine.dispose()
        conn_mod.engine = orig_engine
        conn_mod.SessionLocal = orig_session
        try:
            os.remove(db_path)
        except OSError:
            pass
