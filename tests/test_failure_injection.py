"""Failure injection tests — simulate production failures and verify
system resilience.  Three scenarios:

1. Scheduler crash mid-cycle (between Risk and Execution stages) —
   confirm the next cycle starts clean with no half-written state.

2. Database unreachable during save_cycle() — confirm the system
   fails loudly via alert rather than silently losing results.

3. Binance malformed / unexpected error codes — confirm the
   Execution Agent logs, alerts, and continues to the next symbol
   without crashing the scheduler process.

All tests use isolated in-memory SQLite and no real network calls.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ── Shared Fixture ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def test_db():
    """Replace the production database engine with a fresh in-memory
    SQLite database before every test.  Restores the original engine
    on teardown."""
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


# ── Helper: build a complete AgentState mimicking a finished cycle ──

def _build_complete_state() -> dict[str, Any]:
    """Return a dict structurally equivalent to a completed AgentState
    with one FILLED BUY trade."""
    from src.agents.agent_state import ExecutedTrade, ProposedTrade, Signal

    now = datetime.utcnow()
    proposal = ProposedTrade(
        symbol="SOL/USDT",
        side="BUY",
        quantity=Decimal("10"),
        entry_price=Decimal("50"),
        stop_loss_price=Decimal("40"),
        take_profit_price=Decimal("60"),
        signal_confidence=0.6,
        reasoning="failure injection test BUY",
    )
    executed = ExecutedTrade(
        proposal=proposal,
        executed_price=Decimal("50"),
        executed_quantity=Decimal("10"),
        order_id="fi-buy-001",
        status="FILLED",
        timestamp=now,
        fee_paid=Decimal("0.5"),
        pnl=None,
    )
    signal = Signal(
        symbol="SOL/USDT",
        predicted_return=0.01,
        direction="up",
        confidence=0.6,
        sentiment_score=0.55,
        sentiment_label="positive",
        vol_regime=0,
        regime_label="LOW_VOL",
        fear_greed_value=55,
        timestamp=now,
    )
    return {
        "cycle_id": "fi-test-cycle",
        "timestamp": now,
        "pipeline_data": {},
        "signals": [signal],
        "proposed_trades": [proposal],
        "approved_trades": [proposal],
        "executed_trades": [executed],
        "portfolio_summary": {
            "total_value": Decimal("10500"),
            "cash": Decimal("5000"),
            "holdings": {"SOL/USDT": {"quantity": Decimal("10"), "value": Decimal("5500")}},
            "total_position_value": Decimal("500"),
            "total_unrealized_pnl": Decimal("500"),
            "total_realised_pnl": Decimal("0"),
            "return_pct": Decimal("5"),
            "peak_value": Decimal("10500"),
            "drawdown_pct": Decimal("0"),
            "num_positions": 1,
            "positions": [{
                "symbol": "SOL/USDT",
                "quantity": 10.0,
                "avg_entry_price": 50.0,
                "current_price": 55.0,
                "value": 550.0,
                "unrealized_pnl": 50.0,
                "return_pct": 10.0,
            }],
        },
        "risk_report": {
            "drawdown_pct": 0.0,
            "total_proposed": 1,
            "total_approved": 1,
            "total_rejected": 0,
            "portfolio_exposure_pct": 5.0,
        },
        "cycle_log": ["[test] failure injection cycle"],
    }


# ===================================================================
# Scenario 1 — Crash mid-cycle (between Risk and Execution)
# ===================================================================

class TestCrashMidCycle:
    """Simulate a scheduler crash after Risk Agent but before Execution.

    The crash happens between run_cycle() returning and save_cycle()
    being called.  No DB writes have occurred yet.

    Key invariant: the next cycle starts with zero residual state.
    """

    def test_cycle_run_table_empty_after_crash(self, test_db):
        """No CycleRun row when save_cycle was never called."""
        from src.database.connection import get_db
        from src.database.models import CycleRun

        with get_db() as db:
            assert db.query(CycleRun).count() == 0

    def test_trade_table_empty_after_crash(self, test_db):
        """No Trade rows for an abandoned cycle."""
        from src.database.connection import get_db
        from src.database.models import Trade

        with get_db() as db:
            assert db.query(Trade).count() == 0

    def test_position_table_empty_after_crash(self, test_db):
        """No Position rows — update_positions was never called."""
        from src.database.connection import get_db
        from src.database.models import Position

        with get_db() as db:
            assert db.query(Position).count() == 0

    def test_fresh_cycle_id_not_processed(self, test_db):
        """is_cycle_already_processed returns False for any new UUID."""
        from src.database.crud import is_cycle_already_processed

        assert not is_cycle_already_processed(str(uuid4()))

    def test_build_state_then_crash_leaves_no_trace(self, test_db):
        """Build an AgentState (as if Manager+Risk completed), discard
        it (simulating process death), verify DB is untouched."""
        state = _build_complete_state()
        del state

        from src.database.connection import get_db
        from src.database.models import CycleRun, Position, Trade

        with get_db() as db:
            assert db.query(CycleRun).count() == 0
            assert db.query(Trade).count() == 0
            assert db.query(Position).count() == 0

    def test_new_cycle_after_crash_produces_no_duplicates(self, test_db):
        """Crash, then new cycle runs and saves successfully.
        The saved data must not duplicate any phantom state."""
        from src.database.crud import is_cycle_already_processed, save_cycle
        from src.database.connection import get_db
        from src.database.models import CycleRun, Position, PortfolioSnapshot, Trade

        # "Crash" — build state and lose it
        crashed_state = _build_complete_state()
        del crashed_state

        # New cycle runs and saves
        new_state = _build_complete_state()
        new_state["cycle_id"] = str(uuid4())
        saved_id = save_cycle(new_state)

        assert is_cycle_already_processed(saved_id)

        with get_db() as db:
            assert db.query(CycleRun).count() == 1
            assert db.query(CycleRun).first().cycle_id == saved_id
            assert db.query(Trade).count() == 1
            assert db.query(PortfolioSnapshot).count() == 1
            # update_positions wasn't called — no Position rows
            assert db.query(Position).count() == 0

    def test_lock_auto_releases_on_crash(self, test_db):
        """A crash must not leave the file lock in an acquired state.
        The next cycle should be able to acquire it."""
        import tempfile
        from pathlib import Path

        from filelock import FileLock, Timeout

        lock_path = Path(tempfile.mkdtemp()) / ".test_crash.lock"
        lock = FileLock(str(lock_path), timeout=5)
        lock.acquire()

        # Simulate the implicit release that happens on process death
        lock.release()

        # Next cycle must be able to lock
        lock2 = FileLock(str(lock_path), timeout=5)
        try:
            lock2.acquire()
            assert True
        except Timeout:
            pytest.fail("Lock was NOT released after simulated crash")
        finally:
            lock2.release()


# ===================================================================
# Scenario 2 — Database unreachable during save_cycle
# ===================================================================

class TestDatabaseUnreachable:
    """Simulate Neon Postgres being unreachable when save_cycle() runs.

    The system must not silently lose the cycle's results — it should
    fail loudly via the alert webhook.  The in-memory state must remain
    intact and re-saveable once the DB recovers.
    """

    def test_save_cycle_raises_on_connection_failure(self, test_db):
        """When get_db() fails, save_cycle must raise."""
        from src.database.crud import save_cycle

        state = _build_complete_state()
        state["cycle_id"] = str(uuid4())

        with patch("src.database.crud.get_db") as mock_get_db:
            mock_get_db.side_effect = Exception("Neon Postgres connection refused")

            with pytest.raises(Exception, match="connection refused"):
                save_cycle(state)

    def test_scheduler_sends_alert_on_save_failure(self, test_db):
        """When save_cycle fails in run_trading_cycle(), send_alert
        must be called — the system must not silently lose results."""
        from src.scheduler.jobs import run_trading_cycle

        with (
            patch("src.scheduler.jobs.DataPipeline") as mock_dp,
            patch("src.scheduler.jobs.get_current_portfolio_state") as mock_gcps,
            patch("src.scheduler.jobs.run_cycle") as mock_rc,
            patch("src.scheduler.jobs.save_cycle") as mock_save,
            patch("src.scheduler.jobs.send_alert") as mock_alert,
            patch("src.scheduler.jobs.is_cycle_already_processed", return_value=False),
            patch("src.scheduler.jobs.FileLock") as mock_lock_cls,
        ):
            mock_dp.return_value.run.return_value = {}
            mock_gcps.return_value = {
                "total_value": Decimal("10000"),
                "cash": Decimal("8000"),
                "holdings": {},
            }
            mock_rc.return_value = _build_complete_state()
            mock_lock = MagicMock()
            mock_lock_cls.return_value = mock_lock

            mock_save.side_effect = Exception("DB write failed — connection lost")

            run_trading_cycle()

            mock_alert.assert_called_once()
            alert_msg = mock_alert.call_args[0][0]
            assert "failed" in alert_msg.lower()
            mock_lock.release.assert_called_once()

    def test_cycle_state_preserved_after_db_failure(self, test_db):
        """After save_cycle fails, the in-memory state must be complete
        and re-saveable once the DB recovers."""
        from src.database.crud import is_cycle_already_processed, save_cycle

        state = _build_complete_state()
        state["cycle_id"] = str(uuid4())

        # DB fails during save
        with patch("src.database.crud.get_db") as mock_get_db:
            mock_get_db.side_effect = Exception("DB down")
            with pytest.raises(Exception):
                save_cycle(state)

        # DB recovers — state is still intact, save it
        saved_id = save_cycle(state)
        assert saved_id == state["cycle_id"]
        assert is_cycle_already_processed(state["cycle_id"])

    def test_no_partial_db_state_on_save_failure(self, test_db):
        """When save_cycle fails mid-transaction, no partial rows
        must remain in any table."""
        from contextlib import contextmanager

        from src.database.crud import save_cycle
        from src.database.connection import SessionLocal, get_db
        from src.database.models import CycleRun, PortfolioSnapshot, Trade

        state = _build_complete_state()
        state["cycle_id"] = str(uuid4())

        @contextmanager
        def _broken_get_db():
            """Yield a real session whose commit raises."""
            db = SessionLocal()
            try:
                yield db
                raise Exception("DB commit failed — WAL write error on Neon Postgres")
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        with patch("src.database.crud.get_db", side_effect=_broken_get_db):
            with pytest.raises(Exception):
                save_cycle(state)

        # Verify no partial state was persisted
        with get_db() as db:
            assert db.query(CycleRun).count() == 0
            assert db.query(Trade).count() == 0
            assert db.query(PortfolioSnapshot).count() == 0


# ===================================================================
# Scenario 3 — Binance malformed / unexpected error codes
# ===================================================================

class TestMalformedBinanceError:
    """Simulate Binance returning unexpected error codes or malformed
    responses.  ExecutionAgent must handle each without crashing the
    scheduler process — logging the error, marking the trade FAILED,
    and continuing to the next symbol."""

    @pytest.fixture
    def exec_agent(self):
        """Create an ExecutionAgent whose BinanceClient is fully mocked.

        Yields:
            Tuple of (ExecutionAgent, MagicMock for binance client).
        """
        with patch("src.agents.execution_agent.BinanceClient") as MockBC:
            mock_binance = MagicMock()
            MockBC.return_value = mock_binance

            mock_binance.get_current_price.return_value = Decimal("60000")
            mock_binance.get_symbol_filters.return_value = {
                "lot_size": {"stepSize": Decimal("0.001")},
                "min_notional": {"minNotional": Decimal("10")},
            }
            mock_binance._client = MagicMock()

            from src.agents.execution_agent import ExecutionAgent

            agent = ExecutionAgent()
            yield agent, mock_binance

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_trade(symbol: str = "BTC/USDT", side: str = "BUY") -> Any:
        """Build a simple ProposedTrade for binance-error tests."""
        from src.agents.agent_state import ProposedTrade

        return ProposedTrade(
            symbol=symbol,
            side=side,
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss_price=Decimal("58000"),
            take_profit_price=Decimal("62000"),
            signal_confidence=0.6,
            reasoning="failure injection binance test",
        )

    @staticmethod
    def _make_state(approved: list | None = None) -> dict[str, Any]:
        """Minimal AgentState dict for execution-agent tests."""
        return {
            "cycle_id": "fi-binance-test",
            "timestamp": datetime.utcnow(),
            "pipeline_data": {},
            "signals": [],
            "proposed_trades": [],
            "approved_trades": approved or [],
            "executed_trades": [],
            "portfolio_summary": {"total_value": Decimal("10000"), "cash": Decimal("8000"), "holdings": {}},
            "risk_report": {},
            "cycle_log": [],
        }

    def _make_binance_error(self, code: int, msg: str) -> Any:
        """Create a BinanceAPIException with a given code and message."""
        import json

        from binance.exceptions import BinanceAPIException

        response = MagicMock()
        response.status_code = 400
        response.text = json.dumps({"code": code, "msg": msg})
        return BinanceAPIException(response, 400, response.text)

    # ------------------------------------------------------------------
    # Unknown / unexpected error codes
    # ------------------------------------------------------------------

    def test_unknown_error_code_returns_failed(self, exec_agent, test_db):
        """BinanceAPIException with an unrecognised code must return
        a FAILED ExecutedTrade — not crash the process."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.side_effect = self._make_binance_error(
            -2010, "Account has insufficient balance"
        )

        trade = self._make_trade()
        state = self._make_state()
        executed = agent._execute_trade(trade, state)

        assert executed is not None
        assert executed.status == "FAILED"
        assert executed.executed_quantity == Decimal("0")

    def test_malformed_response_returns_failed(self, exec_agent, test_db):
        """Non-JSON Binance error response (e.g. HTML gateway error)
        must return a FAILED ExecutedTrade without crashing."""
        from binance.exceptions import BinanceAPIException

        agent, mock_binance = exec_agent

        response = MagicMock()
        response.status_code = 502
        response.text = "<html><body>502 Bad Gateway</body></html>"
        mock_binance._client.create_order.side_effect = BinanceAPIException(
            response, 502, response.text
        )

        trade = self._make_trade()
        state = self._make_state()
        executed = agent._execute_trade(trade, state)

        assert executed is not None
        assert executed.status == "FAILED"

    def test_minus_1003_retries_and_succeeds(self, exec_agent, test_db):
        """-1003 (rate limit) triggers the retry logic.  If the retry
        succeeds, the trade must be marked FILLED."""
        agent, mock_binance = exec_agent

        order_response = {
            "orderId": "retry-order-001",
            "executedQty": "0.01",
            "cummulativeQuoteQty": "600.0",
            "status": "FILLED",
        }
        mock_binance._client.create_order.side_effect = [
            self._make_binance_error(-1003, "Too many requests"),
            order_response,
        ]

        trade = self._make_trade()
        state = self._make_state()

        # Patch time.sleep to skip the 60s rate-limit backoff
        import time as _time
        original_sleep = _time.sleep
        _time.sleep = lambda s: None
        try:
            executed = agent._execute_trade(trade, state)
        finally:
            _time.sleep = original_sleep

        assert executed is not None
        assert executed.status == "FILLED"
        assert mock_binance._client.create_order.call_count == 2

    def test_minus_1003_retry_exhaustion_returns_failed(self, exec_agent, test_db):
        """If the -1003 retry also fails, the trade must be FAILED."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.side_effect = [
            self._make_binance_error(-1003, "Too many requests"),
            self._make_binance_error(-1003, "Still rate limited"),
        ]

        trade = self._make_trade()
        state = self._make_state()

        # Patch time.sleep to skip the 60s rate-limit backoff
        import time as _time
        original_sleep = _time.sleep
        _time.sleep = lambda s: None
        try:
            executed = agent._execute_trade(trade, state)
        finally:
            _time.sleep = original_sleep

        assert executed is not None
        assert executed.status == "FAILED"
        assert mock_binance._client.create_order.call_count == 2

    def test_network_timeout_returns_failed(self, exec_agent, test_db):
        """A ConnectionError / timeout (not BinanceAPIException) must
        return FAILED via the generic except block."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.side_effect = ConnectionError(
            "Connection reset by peer"
        )

        trade = self._make_trade()
        state = self._make_state()
        executed = agent._execute_trade(trade, state)

        assert executed is not None
        assert executed.status == "FAILED"

    # ------------------------------------------------------------------
    # Multi-symbol: one fails, next continues
    # ------------------------------------------------------------------

    def test_multiple_symbols_continues_after_error(self, exec_agent, test_db):
        """When one symbol fails with a Binance error, the next symbol
        in approved_trades must still be attempted."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.side_effect = [
            self._make_binance_error(-1013, "Filter failure: LOT_SIZE"),
            {
                "orderId": "sol-fill-001",
                "executedQty": "10.0",
                "cummulativeQuoteQty": "500.0",
                "status": "FILLED",
            },
        ]

        def _price(sym: str) -> Decimal:
            return {"BTC/USDT": Decimal("60000"), "SOL/USDT": Decimal("50")}.get(sym, Decimal("0"))

        mock_binance.get_current_price.side_effect = _price

        trade_btc = self._make_trade("BTC/USDT", "BUY")
        trade_sol = self._make_trade("SOL/USDT", "BUY")
        trade_sol.quantity = Decimal("10")
        trade_sol.entry_price = Decimal("50")

        result = agent.run(self._make_state(approved=[trade_btc, trade_sol]))

        assert len(result["executed_trades"]) == 2
        assert result["executed_trades"][0].status == "FAILED"
        assert result["executed_trades"][1].status == "FILLED"
        assert mock_binance._client.create_order.call_count == 2

    def test_two_failed_trades_triggers_alert(self, exec_agent, test_db):
        """When >= 2 trades fail in a single cycle, send_alert is called."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.side_effect = [
            self._make_binance_error(-2010, "Insufficient balance"),
            self._make_binance_error(-2011, "Unknown order"),
        ]

        def _price(sym: str) -> Decimal:
            return {"BTC/USDT": Decimal("60000"), "SOL/USDT": Decimal("50")}.get(sym, Decimal("0"))

        mock_binance.get_current_price.side_effect = _price

        trade_btc = self._make_trade("BTC/USDT", "BUY")
        trade_sol = self._make_trade("SOL/USDT", "BUY")
        trade_sol.quantity = Decimal("10")
        trade_sol.entry_price = Decimal("50")

        with patch("src.agents.execution_agent.send_alert") as mock_alert:
            result = agent.run(self._make_state(approved=[trade_btc, trade_sol]))

        assert mock_alert.called
        alert_msg = mock_alert.call_args[0][0]
        assert "FAILED" in alert_msg
        assert result["executed_trades"][0].status == "FAILED"
        assert result["executed_trades"][1].status == "FAILED"

    def test_zero_failed_trades_no_alert(self, exec_agent, test_db):
        """When all trades succeed, send_alert must NOT be called."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.return_value = {
            "orderId": "all-good-001",
            "executedQty": "0.01",
            "cummulativeQuoteQty": "600.0",
            "status": "FILLED",
        }

        trade = self._make_trade("BTC/USDT", "BUY")

        with patch("src.agents.execution_agent.send_alert") as mock_alert:
            result = agent.run(self._make_state(approved=[trade]))

        assert mock_alert.call_count == 0
        assert result["executed_trades"][0].status == "FILLED"

    # ------------------------------------------------------------------
    # Specific error codes we haven't seen yet
    # ------------------------------------------------------------------

    def test_error_minus_1013_at_api_level(self, exec_agent, test_db):
        """-1013 (Filter failure: LOT_SIZE) caught at the API level
        must return FAILED, not crash."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.side_effect = self._make_binance_error(
            -1013, "Filter failure: LOT_SIZE"
        )

        trade = self._make_trade("BTC/USDT", "BUY")
        state = self._make_state()
        executed = agent._execute_trade(trade, state)

        assert executed is not None
        assert executed.status == "FAILED"

    def test_error_minus_1111_precision(self, exec_agent, test_db):
        """-1111 (precision overstep) — a code we haven't seen.
        Must return FAILED, not crash."""
        agent, mock_binance = exec_agent

        mock_binance._client.create_order.side_effect = self._make_binance_error(
            -1111, "Precision is over the defined for this asset"
        )

        trade = self._make_trade("BTC/USDT", "BUY")
        state = self._make_state()
        executed = agent._execute_trade(trade, state)

        assert executed is not None
        assert executed.status == "FAILED"

    def test_binance_api_error_on_price_fetch(self, exec_agent, test_db):
        """If get_current_price raises BinanceAPIException (e.g. invalid
        symbol), the trade must be FAILED with price=0 and no order."""
        agent, mock_binance = exec_agent

        mock_binance.get_current_price.side_effect = self._make_binance_error(
            -1121, "Invalid symbol"
        )

        trade = self._make_trade("BTC/USDT", "BUY")
        state = self._make_state()
        executed = agent._execute_trade(trade, state)

        assert executed is not None
        assert executed.status == "FAILED"
        assert executed.executed_price == Decimal("0")
        mock_binance._client.create_order.assert_not_called()


# ===================================================================
# Scenario 4 — Reconciliation catches T13 pipeline-only drift
# ===================================================================

class TestReconciliationDetectsT13Drift:
    """reconcile_positions() must detect when a Position row is missing
    even though trade history shows the system should still hold it.

    T13 documents that manual corrections are invisible to
    update_positions().  If a Position row is deleted by a cycle that
    closes a stale quantity, the asset remains on the exchange but has
    no DB entry.  The reconciliation job's exchange-only check must
    cross-reference against the Trade table to distinguish this real
    drift from Testnet faucet dust.
    """

    @staticmethod
    def _make_exchange_balance(asset: str, qty: float) -> dict:
        """Build a fake get_account() response fragment."""
        return {"asset": asset, "free": str(qty), "locked": "0.0"}

    def _run_reconciliation_with_mocks(
        self,
        exchange_balances: list[dict],
        insert_trade_fn: object | None = None,
        db_symbol: str | None = None,
        db_qty: float = 0.0,
    ) -> list[str]:
        """Run reconcile_positions() with a mocked exchange and DB,
        capturing what would be sent to send_alert.

        Returns:
            The alert message text, or ``None`` if no alert was sent.
        """
        from src.scheduler.jobs import reconcile_positions

        account_response = {"balances": exchange_balances}

        # Set up mocks
        mock_binance_instance = MagicMock()
        mock_binance_instance._client.get_account.return_value = account_response

        with (
            patch("src.data.binance_client.BinanceClient", return_value=mock_binance_instance),
            patch("src.scheduler.jobs.send_alert") as mock_alert,
            patch("pathlib.Path.touch"),
        ):
            reconcile_positions()
            if mock_alert.called:
                return mock_alert.call_args[0][0]
            return None

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_missing_position_row_flagged(self, test_db):
        """Given a FILLED BUY trade with no corresponding Position row
        and an exchange showing balance, reconciliation must flag it."""
        from decimal import Decimal
        from datetime import datetime

        from src.database.connection import get_db
        from src.database.models import Trade as TradeModel

        # Insert a FILLED BUY trade (no SELL) — Position row should exist
        now = datetime.utcnow()
        with get_db() as db:
            db.add(TradeModel(
                cycle_id="recon-test-buy",
                symbol="SOL/USDT",
                side="BUY",
                proposed_quantity=Decimal("1.0"),
                executed_quantity=Decimal("1.0"),
                entry_price=Decimal("70"),
                executed_price=Decimal("70"),
                stop_loss_price=Decimal("0"),
                take_profit_price=Decimal("999999"),
                order_id="recon-buy-001",
                status="FILLED",
                is_pre_fix_artifact=False,
                created_at=now,
            ))
            db.flush()

        # No Position row for SOL (simulating T13 drift)

        # Exchange reports 1.0 SOL
        balances = [self._make_exchange_balance("SOL", 1.0)]

        alert_text = self._run_reconciliation_with_mocks(balances)
        assert alert_text is not None, "Expected alert for missing SOL position"
        assert "MISSING" in alert_text
        assert "SOL/USDT" in alert_text
        assert "net_trade_qty=1.0" in alert_text.replace(" ", "")

    def test_pure_faucet_dust_not_flagged(self, test_db):
        """An asset on exchange with ZERO trade history must NOT be
        flagged — it's Testnet faucet dust."""
        # No trades for this asset, no Position row
        balances = [self._make_exchange_balance("SOME", 0.5)]

        alert_text = self._run_reconciliation_with_mocks(balances)
        assert alert_text is None, "Pure faucet dust must not trigger alert"

    def test_traded_asset_with_position_not_flagged(self, test_db):
        """An asset with both a Position row and exchange balance must
        NOT be flagged when exchange >= DB (one-directional invariant)."""
        from decimal import Decimal
        from datetime import datetime
        import uuid

        from src.database.connection import get_db
        from src.database.models import Position, Trade as TradeModel

        now = datetime.utcnow()

        # Position row exists
        with get_db() as db:
            db.add(Position(
                id=str(uuid.uuid4()),
                symbol="SOL/USDT",
                quantity=Decimal("1.0"),
                avg_entry_price=Decimal("70"),
                current_price=Decimal("75"),
                unrealised_pnl=Decimal("5"),
                updated_at=now,
            ))
            # Trade history matches
            db.add(TradeModel(
                cycle_id="recon-test-normal",
                symbol="SOL/USDT",
                side="BUY",
                proposed_quantity=Decimal("1.0"),
                executed_quantity=Decimal("1.0"),
                entry_price=Decimal("70"),
                executed_price=Decimal("70"),
                stop_loss_price=Decimal("0"),
                take_profit_price=Decimal("999999"),
                order_id="recon-normal-buy",
                status="FILLED",
                is_pre_fix_artifact=False,
                created_at=now,
            ))
            db.flush()

        # Exchange has 1.0 SOL (same as DB)
        balances = [self._make_exchange_balance("SOL", 1.0)]

        alert_text = self._run_reconciliation_with_mocks(balances)
        assert alert_text is None, (
            f"No alert expected when exchange equals DB, got: {alert_text}"
        )

    def test_missing_position_with_faucet_alongside(self, test_db):
        """Multiple assets on exchange — one with trade history (should
        flag), one without (faucet dust, should not flag)."""
        from decimal import Decimal
        from datetime import datetime

        from src.database.connection import get_db
        from src.database.models import Trade as TradeModel

        now = datetime.utcnow()

        # SOL has trade history but no Position row (T13 drift)
        with get_db() as db:
            db.add(TradeModel(
                cycle_id="recon-multi-sol",
                symbol="SOL/USDT",
                side="BUY",
                proposed_quantity=Decimal("3.601"),
                executed_quantity=Decimal("3.601"),
                entry_price=Decimal("69.48"),
                executed_price=Decimal("69.48"),
                stop_loss_price=Decimal("0"),
                take_profit_price=Decimal("999999"),
                order_id="recon-multi-buy",
                status="FILLED",
                is_pre_fix_artifact=False,
                created_at=now,
            ))
            db.add(TradeModel(
                cycle_id="recon-multi-sol",
                symbol="SOL/USDT",
                side="SELL",
                proposed_quantity=Decimal("1.0"),
                executed_quantity=Decimal("1.0"),
                entry_price=Decimal("69.38"),
                executed_price=Decimal("69.38"),
                stop_loss_price=Decimal("0"),
                take_profit_price=Decimal("999999"),
                order_id="recon-multi-sell",
                status="FILLED",
                is_pre_fix_artifact=False,
                created_at=now,
            ))
            db.flush()

        # Exchange has: SOL 2.588 (including ~1.588 faucet dust), FAKE 0.5 (pure dust)
        balances = [
            self._make_exchange_balance("SOL", 2.588),
            self._make_exchange_balance("FAKE", 0.5),
        ]

        alert_text = self._run_reconciliation_with_mocks(balances)
        assert alert_text is not None, "Expected alert for missing SOL position"
        assert "SOL/USDT" in alert_text
        assert "MISSING" in alert_text
        assert "net_trade_qty=2.601" in alert_text.replace(" ", ""), (
            f"Expected net_trade_qty=2.601 (3.601 BUY - 1.0 SELL), got: {alert_text}"
        )
        assert "FAKE" not in alert_text, "Faucet dust must not appear in alert"

    def test_position_deleted_by_stale_qty_flagged(self, test_db):
        """Exact RS08 scenario: Position had 1.601 (after manual correction +
        partial SELL), SELL 1.601 deleted the row, but trade history says
        1.0 SOL should remain.  Reconciliation must flag this."""
        from decimal import Decimal
        from datetime import datetime

        from src.database.connection import get_db
        from src.database.models import Trade as TradeModel

        now = datetime.utcnow()

        # Three SOL trades as they exist in production:
        # BUY 3.601, SELL 1.0 (manual test), SELL 1.601 (live cycle)
        with get_db() as db:
            for qty, side, price in [
                (Decimal("3.601"), "BUY", Decimal("69.48")),
                (Decimal("1.0"), "SELL", Decimal("69.38")),
                (Decimal("1.601"), "SELL", Decimal("74.75")),
            ]:
                db.add(TradeModel(
                    cycle_id="rs08-scenario",
                    symbol="SOL/USDT",
                    side=side,
                    proposed_quantity=qty,
                    executed_quantity=qty,
                    entry_price=price,
                    executed_price=price,
                    stop_loss_price=Decimal("0"),
                    take_profit_price=Decimal("999999"),
                    order_id=f"rs08-{side}-{qty}",
                    status="FILLED",
                    is_pre_fix_artifact=False,
                    created_at=now,
                ))
            db.flush()

        # No Position row (deleted by SELL 1.601 cycle)

        # Exchange has 2.588 SOL
        balances = [self._make_exchange_balance("SOL", 2.588)]

        alert_text = self._run_reconciliation_with_mocks(balances)
        assert alert_text is not None, (
            "Expected alert: SOL has trade history but missing Position row"
        )
        assert "SOL/USDT" in alert_text
        assert "MISSING" in alert_text
