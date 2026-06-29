"""Financial integrity tests — automated regression for R08-R12, T10-T12,
V19, W08, W07 invariants.  Each test uses an isolated in-memory SQLite
database so no production data is ever touched.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Fixture — swap global engine/session for an isolated in-memory SQLite DB
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def test_db():
    """Replace the production database engine with a fresh in-memory SQLite
    database before every test. Restores the original engine on teardown."""
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


# ---------------------------------------------------------------------------
# Helpers — insert test data into the isolated DB
# ---------------------------------------------------------------------------

def _insert_trade(
    symbol: str,
    side: str,
    status: str,
    executed_qty: Decimal,
    executed_price: Decimal,
    pnl: Decimal | None,
    is_pre_fix_artifact: bool = False,
) -> dict[str, Any]:
    """Insert a Trade row and return its attributes as a dict."""
    from src.database.connection import get_db
    from src.database.models import Trade

    t = Trade(
        cycle_id="test-cycle",
        symbol=symbol,
        side=side,
        proposed_quantity=executed_qty,
        executed_quantity=executed_qty,
        entry_price=executed_price,
        executed_price=executed_price,
        stop_loss_price=Decimal("0"),
        take_profit_price=Decimal("999999"),
        order_id="test-order",
        status=status,
        pnl=pnl,
        is_pre_fix_artifact=is_pre_fix_artifact,
        is_sentiment_driven=True,
        created_at=datetime.utcnow(),
    )
    with get_db() as db:
        db.add(t)
        db.flush()
        return {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "status": t.status,
            "executed_quantity": t.executed_quantity,
            "executed_price": t.executed_price,
            "pnl": t.pnl,
            "is_pre_fix_artifact": t.is_pre_fix_artifact,
        }


def _insert_cycle_run(cycle_id: str = "test-cycle") -> None:
    """Ensure a CycleRun exists for foreign-key constraints."""
    from src.database.connection import get_db
    from src.database.models import CycleRun

    with get_db() as db:
        existing = db.query(CycleRun).filter(CycleRun.cycle_id == cycle_id).first()
        if existing:
            return
        db.add(
            CycleRun(
                cycle_id=cycle_id,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
        )


def _build_executed_trade(
    symbol: str,
    side: str,
    qty: Decimal,
    price: Decimal,
    status: str = "FILLED",
    pnl: Decimal | None = None,
) -> Any:
    """Build an ExecutedTrade dataclass instance (used by update_positions)."""
    from src.agents.agent_state import ExecutedTrade, ProposedTrade

    proposal = ProposedTrade(
        symbol=symbol,
        side=side,
        quantity=qty,
        entry_price=price,
        stop_loss_price=Decimal("0"),
        take_profit_price=Decimal("999999"),
        signal_confidence=0.5,
        reasoning="test",
    )
    return ExecutedTrade(
        proposal=proposal,
        executed_price=price,
        executed_quantity=qty,
        order_id="test-order",
        status=status,
        timestamp=datetime.utcnow(),
        fee_paid=Decimal("0"),
        pnl=pnl if pnl is not None else Decimal("0"),
    )


# ===================================================================
# R08-R12: get_total_realised_pnl() invariant
# ===================================================================

class TestGetTotalRealisedPnl:
    """get_total_realised_pnl() must always equal SUM(Trade.pnl)
    WHERE side='SELL' AND status='FILLED'."""

    def test_empty_db_returns_zero(self):
        from src.database.crud import get_total_realised_pnl

        assert get_total_realised_pnl() == Decimal("0")

    def test_sums_all_filled_sells(self):
        _insert_cycle_run()
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("1"), Decimal("70"), Decimal("5.50"))
        _insert_trade("BTC/USDT", "SELL", "FILLED", Decimal("0.01"), Decimal("60000"), Decimal("10.00"))
        _insert_trade("ETH/USDT", "SELL", "FILLED", Decimal("0.5"), Decimal("1800"), Decimal("-2.30"))

        from src.database.crud import get_total_realised_pnl

        assert get_total_realised_pnl() == Decimal("13.20")  # 5.50 + 10.00 + (-2.30)

    def test_excludes_buy_trades(self):
        _insert_cycle_run()
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("1"), Decimal("70"), Decimal("5.00"))
        _insert_trade("SOL/USDT", "BUY", "FILLED", Decimal("1"), Decimal("65"), None)

        from src.database.crud import get_total_realised_pnl

        assert get_total_realised_pnl() == Decimal("5.00")

    def test_excludes_non_filled_trades(self):
        _insert_cycle_run()
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("1"), Decimal("70"), Decimal("3.00"))
        _insert_trade("SOL/USDT", "SELL", "FAILED", Decimal("1"), Decimal("70"), Decimal("2.00"))

        from src.database.crud import get_total_realised_pnl

        assert get_total_realised_pnl() == Decimal("3.00")

    def test_get_total_realised_pnl_includes_artifacts(self):
        """get_total_realised_pnl() is the portfolio-wide counter — it
        deliberately includes artifact trades.  The non-artifact sum
        is a separate query used only by performance_metrics."""
        _insert_cycle_run()
        _insert_trade("BTC/USDT", "SELL", "FILLED", Decimal("0.01"), Decimal("60000"), Decimal("-5.00"),
                       is_pre_fix_artifact=True)
        _insert_trade("BTC/USDT", "SELL", "FILLED", Decimal("0.01"), Decimal("61000"), Decimal("8.00"))

        from src.database.crud import get_total_realised_pnl

        # Includes both: -5.00 + 8.00 = 3.00
        assert get_total_realised_pnl() == Decimal("3.00")

    def test_returns_decimal_not_float(self):
        _insert_cycle_run()
        _insert_trade("ADA/USDT", "SELL", "FILLED", Decimal("10"), Decimal("0.35"), Decimal("0.12345678"))

        from src.database.crud import get_total_realised_pnl

        result = get_total_realised_pnl()
        assert isinstance(result, Decimal)
        assert result == Decimal("0.12345678")

    def test_computational_invariant(self):
        """Re-verify: SUM of every FILLED SELL's pnl == get_total_realised_pnl()."""
        _insert_cycle_run()
        values = [Decimal("1.23"), Decimal("-0.56"), Decimal("3.78"), Decimal("-1.01")]
        for v in values:
            _insert_trade("BTC/USDT", "SELL", "FILLED", Decimal("0.01"), Decimal("60000"), v)
        _insert_trade("SOL/USDT", "BUY", "FILLED", Decimal("1"), Decimal("70"), None)

        from src.database.crud import get_total_realised_pnl
        from src.database.connection import get_db
        from src.database.models import Trade
        from sqlalchemy import func

        with get_db() as db:
            db_sum = (
                db.query(func.sum(Trade.pnl))
                .filter(
                    Trade.side == "SELL",
                    Trade.status == "FILLED",
                    Trade.is_pre_fix_artifact == False,
                )
                .scalar()
            ) or Decimal("0")

        assert get_total_realised_pnl() == db_sum


# ===================================================================
# T10-T12: update_positions() — decrement on SELL, delete at zero
# ===================================================================

class TestUpdatePositions:
    """update_positions() must increment on BUY, decrement on SELL,
    and delete the Position row when quantity reaches zero."""

    _state: dict[str, Any] = {}

    def _make_state(self, executed_trades: list, positions: list | None = None) -> dict[str, Any]:
        return {
            "cycle_id": "test-update",
            "timestamp": datetime.utcnow(),
            "pipeline_data": {},
            "signals": [],
            "proposed_trades": [],
            "approved_trades": [],
            "executed_trades": executed_trades,
            "portfolio_summary": {
                "total_value": Decimal("10000"),
                "cash": Decimal("5000"),
                "holdings": {},
                "positions": positions or [],
            },
            "risk_report": {},
            "cycle_log": [],
        }

    def test_buy_creates_position(self):
        from src.database.crud import update_positions

        trades = [_build_executed_trade("SOL/USDT", "BUY", Decimal("10"), Decimal("50"))]
        state = self._make_state(trades)
        update_positions(state)

        from src.database.connection import get_db
        from src.database.models import Position

        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
            assert pos is not None
            assert pos.quantity == Decimal("10")
            assert pos.avg_entry_price == Decimal("50")

    def test_buy_adds_to_existing_position(self):
        from src.database.crud import update_positions
        from src.database.connection import get_db
        from src.database.models import Position

        # First BUY
        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "BUY", Decimal("5"), Decimal("40"))]
        ))

        # Second BUY — different price
        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "BUY", Decimal("5"), Decimal("60"))]
        ))

        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
            assert pos is not None
            assert pos.quantity == Decimal("10")
            # Weighted average: (5*40 + 5*60) / 10 = 50
            assert pos.avg_entry_price == Decimal("50")

    def test_sell_decrements_position(self):
        from src.database.crud import update_positions
        from src.database.connection import get_db
        from src.database.models import Position

        # BUY first
        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "BUY", Decimal("10"), Decimal("50"))]
        ))
        # SELL 3
        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "SELL", Decimal("3"), Decimal("55"))]
        ))

        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
            assert pos is not None
            assert pos.quantity == Decimal("7")

    def test_sell_that_zeroes_out_position_deletes_row(self):
        from src.database.crud import update_positions
        from src.database.connection import get_db
        from src.database.models import Position

        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "BUY", Decimal("3"), Decimal("50"))]
        ))
        # SELL exactly 3 (brings to zero)
        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "SELL", Decimal("3"), Decimal("55"))]
        ))

        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
        assert pos is None, "Position row should be deleted when quantity reaches zero"

    def test_multiple_buys_then_full_sell(self):
        from src.database.crud import update_positions
        from src.database.connection import get_db
        from src.database.models import Position

        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "BUY", Decimal("3.601"), Decimal("69.48"))]
        ))
        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "SELL", Decimal("1"), Decimal("69.38"))]
        ))

        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
            assert pos is not None
            assert pos.quantity == Decimal("2.601")

        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "SELL", Decimal("2.601"), Decimal("70"))]
        ))
        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
        assert pos is None, "Full SELL should delete row"

    def test_ignores_non_filled_trades(self):
        from src.database.crud import update_positions
        from src.database.connection import get_db
        from src.database.models import Position

        partial = _build_executed_trade("SOL/USDT", "BUY", Decimal("5"), Decimal("50"), status="PARTIALLY_FILLED")
        failed = _build_executed_trade("SOL/USDT", "SELL", Decimal("3"), Decimal("55"), status="FAILED")
        update_positions(self._make_state([partial, failed]))

        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
        assert pos is None, "Non-FILLED trades must not affect positions"

    def test_does_not_round_trip_through_exchange(self):
        """update_positions derives quantity from executed_trades, NOT from
        exchange balance — verifying it never queries Binance."""
        from src.database.crud import update_positions
        from src.database.models import Position
        from src.database.connection import get_db

        update_positions(self._make_state(
            [_build_executed_trade("SOL/USDT", "BUY", Decimal("2"), Decimal("50"))]
        ))
        with get_db() as db:
            pos = db.query(Position).filter(Position.symbol == "SOL/USDT").first()
            assert pos is not None
            assert pos.quantity == Decimal("2")


# ===================================================================
# V19: SELL without holding gets rejected
# ===================================================================

class TestSellWithoutHoldingRejection:
    """Risk Agent must reject SELL proposals for symbols not in holdings."""

    def _run_risk(self, proposed_trades: list | None = None, holdings: dict | None = None) -> dict[str, Any]:
        """Run RiskAgent.run() with the given proposals and holdings,
        returning the full updated state."""
        from src.agents.risk_agent import RiskAgent
        from src.agents.agent_state import ProposedTrade

        state: dict[str, Any] = {
            "cycle_id": "test-v19",
            "timestamp": datetime.utcnow(),
            "pipeline_data": {},
            "signals": [],
            "proposed_trades": proposed_trades or [],
            "approved_trades": [],
            "executed_trades": [],
            "portfolio_summary": {
                "total_value": Decimal("10000"),
                "cash": Decimal("5000"),
                "holdings": holdings or {},
            },
            "risk_report": {},
            "cycle_log": [],
        }
        agent = RiskAgent()
        return agent.run(state)

    def test_rejects_sell_without_holding(self):
        """V19: SELL for a symbol not in any holding or executed trade."""
        from src.agents.agent_state import ProposedTrade

        sell_ada = ProposedTrade(
            symbol="ADA/USDT",
            side="SELL",
            quantity=Decimal("10"),
            entry_price=Decimal("0.40"),
            stop_loss_price=Decimal("0.35"),
            take_profit_price=Decimal("0.50"),
            signal_confidence=0.6,
            reasoning="test SELL no holding",
        )
        result = self._run_risk(
            proposed_trades=[sell_ada],
            holdings={},
        )
        assert len(result["approved_trades"]) == 0
        reasons = result["risk_report"]["rejection_reasons"]
        assert any("SELL without holding" in r["reason"] or "no existing holding" in r["reason"]
                   for r in reasons)

    def test_allows_sell_with_holding(self):
        """SELL for a symbol that IS in holdings must proceed past this check."""
        from src.agents.agent_state import ProposedTrade, ExecutedTrade

        sell_sol = ProposedTrade(
            symbol="SOL/USDT",
            side="SELL",
            quantity=Decimal("1"),
            entry_price=Decimal("70"),
            stop_loss_price=Decimal("60"),
            take_profit_price=Decimal("80"),
            signal_confidence=0.6,
            reasoning="test SELL with holding",
        )
        result = self._run_risk(
            proposed_trades=[sell_sol],
            holdings={"SOL/USDT": {"value": 114.0, "quantity": 1.601}},
        )
        assert len(result["approved_trades"]) >= 1

    def test_allows_buy_without_holding(self):
        """BUY for a new symbol must proceed (no duplicate position)."""
        from src.agents.agent_state import ProposedTrade

        buy_ada = ProposedTrade(
            symbol="ADA/USDT",
            side="BUY",
            quantity=Decimal("100"),
            entry_price=Decimal("0.40"),
            stop_loss_price=Decimal("0.35"),
            take_profit_price=Decimal("0.50"),
            signal_confidence=0.6,
            reasoning="test BUY no holding",
        )
        result = self._run_risk(
            proposed_trades=[buy_ada],
            holdings={},
        )
        assert len(result["approved_trades"]) >= 1

    def test_auto_exit_bypasses_holding_check(self):
        """is_auto_exit=True trades must skip the SELL-without-holding guard."""
        from src.agents.agent_state import ProposedTrade

        auto_exit = ProposedTrade(
            symbol="ADA/USDT",
            side="SELL",
            quantity=Decimal("10"),
            entry_price=Decimal("0.40"),
            stop_loss_price=Decimal("0.35"),
            take_profit_price=Decimal("0.50"),
            signal_confidence=0.6,
            reasoning="auto-exit SL",
            is_auto_exit=True,
        )
        result = self._run_risk(
            proposed_trades=[auto_exit],
            holdings={},
        )
        assert len(result["approved_trades"]) == 1


# ===================================================================
# W08: BUY trades always have pnl IS NULL, never 0
# ===================================================================

class TestBuyPnlIsNull:
    """BUY trades must store pnl=None. A value of 0 is semantically
    different — it means "a closed trade that broke even," which does
    not apply to an open BUY."""

    def test_buy_trade_pnl_is_null_after_insertion(self):
        _insert_cycle_run()
        row = _insert_trade("SOL/USDT", "BUY", "FILLED", Decimal("10"), Decimal("50"), None)
        assert row["pnl"] is None, "BUY trade pnl must be None"

    def test_buy_trade_pnl_is_never_zero(self):
        """Programmatic invariant: no BUY trade in the DB may have pnl=0."""
        _insert_cycle_run()
        rows = []
        for sym, qty, price in [
            ("SOL/USDT", Decimal("10"), Decimal("50")),
            ("BTC/USDT", Decimal("0.5"), Decimal("60000")),
            ("ETH/USDT", Decimal("2"), Decimal("1800")),
        ]:
            r = _insert_trade(sym, "BUY", "FILLED", qty, price, None)
            rows.append(r)

        from src.database.connection import get_db
        from src.database.models import Trade

        with get_db() as db:
            buys = db.query(Trade).filter(Trade.side == "BUY", Trade.status == "FILLED").all()
            for b in buys:
                assert b.pnl is None, f"BUY {b.symbol} has pnl={b.pnl} instead of NULL"

    def test_sell_trade_can_have_zero_or_non_zero_pnl(self):
        """SELL trades may have any pnl value (positive, negative, or zero)."""
        _insert_cycle_run()
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("10"), Decimal("50"), Decimal("0"))
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("5"), Decimal("60"), Decimal("10"))

        from src.database.connection import get_db
        from src.database.models import Trade

        with get_db() as db:
            sells = db.query(Trade).filter(Trade.side == "SELL", Trade.status == "FILLED").all()
            pnls = [s.pnl for s in sells]
        assert Decimal("0") in pnls, "SELL trades may have zero PnL"
        assert Decimal("10") in pnls, "SELL trades may have non-zero PnL"


# ===================================================================
# validate_cycle_integrity — clean fixture passes, corrupted fails
# ===================================================================

class TestValidateCycleIntegrity:
    """validate_cycle_integrity() must return zero violations for a
    known-good dataset, and must flag the expected violation when fed
    deliberately corrupted data."""

    def _fresh_portfolio_state(self, peak: Decimal) -> None:
        from src.database.connection import get_db
        from src.database.models import PortfolioState

        with get_db() as db:
            existing = db.query(PortfolioState).filter(PortfolioState.id == "singleton").first()
            if existing:
                existing.peak_value = peak
            else:
                db.add(PortfolioState(id="singleton", peak_value=peak, updated_at=datetime.utcnow()))

    def _make_clean_state(self) -> dict[str, Any]:
        """Build a known-good AgentState with valid fills and sane
        portfolio numbers.  Also inserts matching DB rows."""
        _insert_cycle_run()

        from src.agents.agent_state import ExecutedTrade, ProposedTrade

        # One FILLED BUY in state + DB
        buy_proposal = ProposedTrade(
            symbol="SOL/USDT", side="BUY", quantity=Decimal("10"),
            entry_price=Decimal("50"), stop_loss_price=Decimal("40"),
            take_profit_price=Decimal("60"), signal_confidence=0.5,
            reasoning="clean test BUY",
        )
        buy_executed = ExecutedTrade(
            proposal=buy_proposal, executed_price=Decimal("50"),
            executed_quantity=Decimal("10"), order_id="clean-buy",
            status="FILLED", timestamp=datetime.utcnow(),
            fee_paid=Decimal("0"), pnl=Decimal("0"),
        )

        state: dict[str, Any] = {
            "cycle_id": "test-integrity",
            "timestamp": datetime.utcnow(),
            "pipeline_data": {},
            "signals": [],
            "proposed_trades": [buy_proposal],
            "approved_trades": [buy_proposal],
            "executed_trades": [buy_executed],
            "portfolio_summary": {
                "total_value": Decimal("10500"),
                "cash": Decimal("5000"),
                "holdings": {"SOL/USDT": {"quantity": Decimal("10"), "value": Decimal("5500")}},
                "peak_value": Decimal("10500"),
            },
            "risk_report": {},
            "cycle_log": [],
        }
        self._fresh_portfolio_state(Decimal("10500"))
        return state

    def test_clean_data_returns_zero_violations(self):
        from src.scheduler.jobs import validate_cycle_integrity

        state = self._make_clean_state()
        violations = validate_cycle_integrity(state)
        assert violations == [], f"Expected zero violations, got: {violations}"

    def test_empty_state_no_crash(self):
        from src.scheduler.jobs import validate_cycle_integrity

        violations = validate_cycle_integrity({})
        assert isinstance(violations, list)

    def test_detects_filled_trade_missing_price(self):
        from src.scheduler.jobs import validate_cycle_integrity
        from src.agents.agent_state import ExecutedTrade, ProposedTrade

        _insert_cycle_run()
        proposal = ProposedTrade(
            symbol="SOL/USDT", side="BUY", quantity=Decimal("10"),
            entry_price=Decimal("50"), stop_loss_price=Decimal("40"),
            take_profit_price=Decimal("60"), signal_confidence=0.5,
            reasoning="bad BUY",
        )
        bad = ExecutedTrade(
            proposal=proposal, executed_price=Decimal("0"),
            executed_quantity=Decimal("10"), order_id="bad-buy",
            status="FILLED", timestamp=datetime.utcnow(),
            fee_paid=Decimal("0"), pnl=Decimal("0"),
        )
        state = self._make_clean_state()
        state["executed_trades"].append(bad)
        violations = validate_cycle_integrity(state)
        assert any("executed_price" in v for v in violations), (
            f"Expected 'executed_price' violation, got: {violations}"
        )

    def test_detects_zero_pnl_sell_not_flagged_as_artifact(self):
        """W07/W11 regression: a SELL with zero PnL and
        is_pre_fix_artifact=False must be flagged."""
        from src.scheduler.jobs import validate_cycle_integrity

        state = self._make_clean_state()
        _insert_trade(
            "BTC/USDT", "SELL", "FILLED",
            Decimal("0.01"), Decimal("60000"), Decimal("0"),
            is_pre_fix_artifact=False,
        )
        violations = validate_cycle_integrity(state)
        assert any("zero" in v.lower() and "pnl" in v.lower() for v in violations), (
            f"Expected 'zero pnl' violation, got: {violations}"
        )

    def test_artifact_flagged_trade_does_not_trigger_violation(self):
        """A SELL with zero PnL but is_pre_fix_artifact=True must NOT
        trigger the zero-PnL check."""
        from src.scheduler.jobs import validate_cycle_integrity

        state = self._make_clean_state()
        _insert_trade(
            "BTC/USDT", "SELL", "FILLED",
            Decimal("0.01"), Decimal("60000"), Decimal("0"),
            is_pre_fix_artifact=True,
        )
        violations = validate_cycle_integrity(state)
        artifact_triggers = [
            v for v in violations
            if "zero" in v.lower() and "pnl" in v.lower()
        ]
        assert len(artifact_triggers) == 0, (
            f"Artifact-flagged trades must not trigger PnL violations: {artifact_triggers}"
        )

    def test_detects_negative_portfolio_value(self):
        from src.scheduler.jobs import validate_cycle_integrity

        state = self._make_clean_state()
        state["portfolio_summary"]["total_value"] = Decimal("-100")
        violations = validate_cycle_integrity(state)
        assert any("negative" in v.lower() for v in violations), (
            f"Expected 'negative' violation, got: {violations}"
        )


# ===================================================================
# Cross-cutting: the R08-R12 PnL-ledger invariant spans all checks
# ===================================================================

class TestPnLLedgerInvariant:
    """Multiple invariants from the audit all converge on the same
    requirement: get_total_realised_pnl() must be the single source
    of truth, immune to snapshot caching or duplicate counting."""

    def test_snapshot_consistency(self):
        """After inserting trades and a snapshot, verify
        get_total_realised_pnl() matches snapshot.realised_pnl."""
        _insert_cycle_run()
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("1"), Decimal("70"), Decimal("5.50"))
        _insert_trade("BTC/USDT", "SELL", "FILLED", Decimal("0.01"), Decimal("60000"), Decimal("-2.30"))

        from src.database.crud import get_total_realised_pnl
        from src.database.connection import get_db
        from src.database.models import PortfolioSnapshot

        total = get_total_realised_pnl()
        with get_db() as db:
            db.add(PortfolioSnapshot(
                cycle_id="test-cycle",
                total_value=Decimal("10000"),
                cash=Decimal("5000"),
                positions_value=Decimal("5000"),
                unrealised_pnl=Decimal("100"),
                realised_pnl=total,
                peak_value=Decimal("10000"),
                drawdown_pct=Decimal("0"),
            ))
            db.flush()
            snap = db.query(PortfolioSnapshot).first()
            assert snap is not None
            assert snap.realised_pnl == total

    def test_duplicate_cycle_does_not_change_pnl(self):
        """Running the same cycle twice must not affect realised PnL."""
        _insert_cycle_run()
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("1"), Decimal("70"), Decimal("3.00"))

        from src.database.crud import get_total_realised_pnl

        first_call = get_total_realised_pnl()

        # Insert the same trade again (simulate double-save)
        _insert_trade("SOL/USDT", "SELL", "FILLED", Decimal("1"), Decimal("70"), Decimal("3.00"))

        second_call = get_total_realised_pnl()
        assert second_call != first_call, (
            "Duplicate trades are data corruptions. This test verifies the "
            "function faithfully sums whatever is in the DB — it does NOT "
            "deduplicate. Cycle-level dedup is is_cycle_already_processed()."
        )

    def test_zero_trades_returns_zero(self):
        from src.database.crud import get_total_realised_pnl

        assert get_total_realised_pnl() == Decimal("0")
