"""Scheduled job definitions for the AlphaCore trading system.

Defines the recurring jobs that APScheduler runs:
    - Trading cycle (1h)
    - Exit-condition check (configurable, default 15m)
    - Data cache refresh (30m)
    - Health check (5m)
    - Model training (once on startup)
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from filelock import FileLock, Timeout

from src.agents import run_cycle
from src.agents.agent_state import AgentState, ProposedTrade
from src.data.binance_client import BinanceClient
from src.data.data_pipeline import DataPipeline
from src.database.connection import check_db_connection, get_db, init_db
from src.database.crud import get_current_portfolio_state, get_total_realised_pnl, is_cycle_already_processed, save_cycle, update_positions
from src.database.models import PortfolioSnapshot, Position as PositionModel, Trade as TradeModel
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance, send_alert
from src.utils.logger import get_logger

_logger = get_logger(__name__)

_LOCK_PATH = f"{settings.DATA_CACHE_DIR}/.trading_cycle.lock"
_EXIT_LOCK_PATH = f"{settings.DATA_CACHE_DIR}/.exit_check.lock"

_SANE_PORTFOLIO_MIN = Decimal("0")
_SANE_PORTFOLIO_MAX_MULTIPLIER = Decimal("10")


def validate_cycle_integrity(final_state: dict[str, Any]) -> list[str]:
    """Check the completed cycle for data integrity violations.

    Inspects the final agent state and the database for:
      - FILLED trades missing executed_price or executed_quantity
      - Closed positions (SELL matching a prior BUY) with null PnL
      - Portfolio total_value outside a sane range
      - peak_value that decreased since the previous cycle

    Args:
        final_state: The completed ``AgentState`` after the pipeline run.

    Returns:
        A list of human-readable violation strings. Empty list = all good.
    """
    violations: list[str] = []

    # --- 1. Check FILLED trades in this cycle have fill details ---
    initial_capital = settings.PORTFOLIO_INITIAL_CAPITAL
    for et in final_state.get("executed_trades", []):
        if et.status == "FILLED":
            if et.executed_price is None or et.executed_price <= Decimal("0"):
                violations.append(
                    f"FILLED trade {et.proposal.symbol} {et.proposal.side} "
                    f"(order={et.order_id}) has null/zero executed_price={et.executed_price}"
                )
            if et.executed_quantity is None or et.executed_quantity <= Decimal("0"):
                violations.append(
                    f"FILLED trade {et.proposal.symbol} {et.proposal.side} "
                    f"(order={et.order_id}) has null/zero executed_quantity={et.executed_quantity}"
                )

        # --- 2. Check all DB FILLED trades have complete fill data ---
    from src.database.connection import get_db

    with get_db() as db:
        filled_trades = (
            db.query(TradeModel)
            .filter(TradeModel.status == "FILLED", TradeModel.is_pre_fix_artifact == False)
            .all()
        )
        for t in filled_trades:
            if t.executed_price is None or t.executed_price <= Decimal("0"):
                violations.append(
                    f"DB FILLED trade #{t.id} {t.symbol} {t.side} "
                    f"missing executed_price={t.executed_price}"
                )
            if t.executed_quantity is None or t.executed_quantity <= Decimal("0"):
                violations.append(
                    f"DB FILLED trade #{t.id} {t.symbol} {t.side} "
                    f"missing executed_quantity={t.executed_quantity}"
                )

        # --- 3. Closed positions with null or zero PnL ---
        sell_trades = (
            db.query(TradeModel)
            .filter(
                TradeModel.side == "SELL",
                TradeModel.status == "FILLED",
                TradeModel.is_pre_fix_artifact == False,
            )
            .all()
        )
        for s in sell_trades:
            if s.pnl is None or s.pnl == 0:
                violations.append(
                    f"Closed SELL trade #{s.id} {s.symbol} has "
                    f"{'null' if s.pnl is None else 'zero'} pnl "
                    f"(executed_price={s.executed_price}, qty={s.executed_quantity})"
                )

    # --- 4. Portfolio sanity ---
    ps = final_state.get("portfolio_summary", {})
    total_value = Decimal(str(ps.get("total_value", "0")))
    peak_value = Decimal(str(ps.get("peak_value", "0")))

    if total_value < _SANE_PORTFOLIO_MIN:
        violations.append(
            f"Portfolio total_value={total_value} is negative "
            f"(min allowed={_SANE_PORTFOLIO_MIN})"
        )

    max_sane = initial_capital * _SANE_PORTFOLIO_MAX_MULTIPLIER
    if total_value > max_sane:
        violations.append(
            f"Portfolio total_value={total_value} exceeds "
            f"{_SANE_PORTFOLIO_MAX_MULTIPLIER}x initial capital "
            f"({max_sane}) in a single cycle — likely a data error"
        )

    # --- 5. peak_value never decreases (against stored PortfolioState) ---
    from src.database.models import PortfolioState as PortfolioStateModel

    with get_db() as db:
        pstate = (
            db.query(PortfolioStateModel)
            .filter(PortfolioStateModel.id == "singleton")
            .first()
        )
        if pstate is not None and peak_value < pstate.peak_value - Decimal("0.01"):
            violations.append(
                f"peak_value decreased from stored {pstate.peak_value} "
                f"to {peak_value} — state corruption detected"
            )

        # --- 6. SUM(Trade.pnl) === latest PortfolioSnapshot.realised_pnl ---
        latest_snap = (
            db.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.created_at.desc())
            .first()
        )
        if latest_snap is not None:
            db_pnl_total = get_total_realised_pnl()
            snap_pnl = latest_snap.realised_pnl if latest_snap.realised_pnl else Decimal("0")
            # Allow ±$0.01 for rounding
            if abs(db_pnl_total - snap_pnl) > Decimal("0.01"):
                violations.append(
                    f"SUM(Trade.pnl)={db_pnl_total} diverges from "
                    f"latest snapshot realised_pnl={snap_pnl} "
                    f"(diff={db_pnl_total - snap_pnl}) — the two ledgers disagree"
                )

    if violations:
        _logger.error(
            "Cycle integrity VIOLATIONS (%d):\n%s",
            len(violations),
            "\n".join(f"  [{i+1}] {v}" for i, v in enumerate(violations)),
        )
        send_alert(
            f"Cycle integrity check FAILED with {len(violations)} violation(s):\n"
            + "\n".join(f"• {v}" for v in violations),
            level="error",
        )

    return violations


def run_trading_cycle() -> None:
    """Execute one full trading cycle: data → agents → persist.

    Called every hour by APScheduler. Fetches fresh pipeline data,
    runs the LangGraph agent pipeline, and persists the results.
    Never raises — all errors are caught and logged.
    """
    _logger.info("=== TRADING CYCLE START ===")

    lock = FileLock(_LOCK_PATH, timeout=5)
    try:
        lock.acquire()
    except Timeout:
        _logger.warning(
            "Cannot acquire trading cycle lock at %s — "
            "another cycle is already running. Skipping this tick.",
            _LOCK_PATH,
        )
        return

    cycle_id = str(uuid4())
    if is_cycle_already_processed(cycle_id):
        _logger.warning("Cycle %s already processed — skipping", cycle_id)
        return

    try:
        pipeline_data = DataPipeline().run()
        portfolio_summary: dict[str, Any] = get_current_portfolio_state()

        _logger.info(
            "Portfolio state loaded — total_value=%s, holdings=%s",
            portfolio_summary.get("total_value"),
            list(portfolio_summary.get("holdings", {}).keys()),
        )

        final_state = run_cycle(pipeline_data, portfolio_summary)
        cycle_id = save_cycle(final_state)
        update_positions(final_state)

        validate_cycle_integrity(final_state)

        signals_count = len(final_state.get("signals", []))
        trades_count = len(final_state.get("executed_trades", []))
        ps = final_state.get("portfolio_summary", {})
        portfolio_value = ps.get("total_value", Decimal("0"))

        _logger.info(
            "=== CYCLE %s DONE — signals=%d, trades=%d, portfolio_value=%s ===",
            cycle_id, signals_count, trades_count, portfolio_value,
        )
    except Exception:
        _logger.exception("Trading cycle failed — full traceback below")
        send_alert("Trading cycle failed — see scheduler logs for details", level="error")
    finally:
        lock.release()
        _logger.debug("Released trading cycle lock at %s", _LOCK_PATH)


def run_exit_check() -> None:
    """Check SL/TP for every open position and execute triggered exits.

    Runs independently of the full trading cycle at a configurable interval
    (``EXIT_CHECK_INTERVAL_MINUTES``, default 15 min). For each open position:
    fetches the live price, compares against stop-loss / take-profit thresholds,
    and if triggered, places a market SELL order via the Binance Testnet,
    persists the trade, and removes/reduces the Position row.

    Uses a separate lock file to avoid conflicting with the trading cycle.
    """
    _logger.info("=== EXIT CHECK START ===")

    lock = FileLock(_EXIT_LOCK_PATH, timeout=5)
    try:
        lock.acquire()
    except Timeout:
        _logger.warning(
            "Cannot acquire exit-check lock — another exit check is already running. Skipping."
        )
        return

    try:
        portfolio_summary: dict[str, Any] = get_current_portfolio_state()
        holdings: dict[str, Any] = portfolio_summary.get("holdings", {})
        if not holdings:
            _logger.info("No open positions — nothing to check")
            return

        binance = BinanceClient()
        from src.agents.execution_agent import ExecutionAgent
        execution_agent = ExecutionAgent()
        now = datetime.utcnow()

        exit_count = 0
        weight_estimate = 0

        for symbol, hdata in holdings.items():
            if not isinstance(hdata, dict):
                continue

            try:
                current_price = binance.get_current_price(symbol)
                weight_estimate += 1
            except Exception as exc:
                _logger.warning(
                    "Exit check: failed to fetch price for %s: %s", symbol, exc
                )
                continue

            qty = Decimal(str(hdata.get("quantity", 0)))
            entry_price = Decimal(str(hdata.get("avg_entry_price", 0)))
            sl_price = Decimal(str(hdata.get("stop_loss_price", 0)))
            tp_price = Decimal(str(hdata.get("take_profit_price", 0)))

            if qty <= Decimal("0"):
                continue

            hit_sl = sl_price > Decimal("0") and current_price <= sl_price
            hit_tp = tp_price > Decimal("0") and current_price >= tp_price

            if not hit_sl and not hit_tp:
                continue

            reason = "stop loss" if hit_sl else "take profit"
            pnl_pct = (
                ((current_price - entry_price) / entry_price * 100)
                if entry_price > 0
                else Decimal("0")
            )

            auto_exit = ProposedTrade(
                symbol=symbol,
                side="SELL",
                quantity=qty,
                entry_price=entry_price,
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
                signal_confidence=1.0,
                reasoning=(
                    f"AUTO-EXIT: {reason} triggered at {float(current_price):.2f}"
                ),
                is_sentiment_driven=False,
                is_auto_exit=True,
                trade_origin="bot_auto_exit",
            )

            state_stub: AgentState = {
                "timestamp": now,
            }

            executed = execution_agent._execute_trade(auto_exit, state_stub)
            if executed is None:
                continue

            if executed.status == "FILLED":
                exit_count += 1
                weight_estimate += 10

            cycle_id = f"exit-check-{uuid4()}"

            with get_db() as db:
                db.add(
                    TradeModel(
                        cycle_id=cycle_id,
                        symbol=symbol,
                        side="SELL",
                        proposed_quantity=qty,
                        executed_quantity=executed.executed_quantity,
                        entry_price=entry_price,
                        executed_price=executed.executed_price,
                        stop_loss_price=sl_price,
                        take_profit_price=tp_price,
                        order_id=executed.order_id,
                        status=executed.status,
                        is_sentiment_driven=False,
                        trade_origin="bot_auto_exit",
                        signal_confidence=1.0,
                        reasoning=(
                            f"AUTO-EXIT: {reason} triggered at "
                            f"{float(current_price):.2f}"
                        ),
                        pnl=executed.pnl,
                        fee_paid=executed.fee_paid,
                        created_at=now,
                    )
                )

                position = (
                    db.query(PositionModel)
                    .filter(PositionModel.symbol == symbol)
                    .first()
                )
                if position:
                    position.quantity -= executed.executed_quantity
                    if position.quantity <= Decimal("0"):
                        db.delete(position)
                        _logger.info(
                            "Position fully closed (exit check): %s", symbol
                        )
                    else:
                        position.updated_at = now
                        _logger.info(
                            "Position reduced (exit check): %s qty=%s",
                            symbol, position.quantity,
                        )
                else:
                    _logger.warning(
                        "Exit check: SELL executed for %s but no open Position row found",
                        symbol,
                    )

            _logger.info(
                "AUTO-EXIT %s — %s triggered. "
                "entry=%.2f exit=%.2f pnl=%.2f%% qty=%s",
                symbol, reason,
                float(entry_price), float(executed.executed_price),
                float(pnl_pct), executed.executed_quantity,
            )

        _logger.info(
            "Exit check rate-limit headroom — "
            "estimated %d weight consumed this cycle. "
            "Binance limit: 1200 weight/min. "
            "At %d-min frequency, %d cycle(s)/hr with 5 positions + potential orders = "
            "negligible impact.",
            weight_estimate,
            settings.EXIT_CHECK_INTERVAL_MINUTES,
            60 // settings.EXIT_CHECK_INTERVAL_MINUTES,
        )

        if exit_count == 0:
            _logger.info("No exit conditions triggered")
        else:
            _logger.info("Exit check: %d position(s) closed", exit_count)
    except Exception:
        _logger.exception("Exit check failed — full traceback below")
    finally:
        lock.release()
        _logger.debug("Released exit-check lock")

    _logger.info("=== EXIT CHECK DONE ===")


def reconcile_positions() -> None:
    """Daily reconciliation: compare DB positions against Binance actual balances.

    Calls Binance's account balance endpoint and compares every asset
    balance against what the Position table thinks we hold. If any
    mismatch exceeds a small rounding tolerance, sends a critical alert
    and auto-pauses trading.

    Runs independently of the trading cycle — this is the belt-and-suspenders
    check against the exact class of state corruption bugs that have
    historically caused the worst losses in autonomous trading systems.
    """
    _logger.info("=== POSITION RECONCILIATION START ===")

    from pathlib import Path

    from src.data.binance_client import BinanceClient
    from src.database.connection import get_db
    from src.database.models import Position as PositionModel

    _PAUSE_FLAG = Path("data_cache/.trading_paused")
    binance = BinanceClient()
    mismatches: list[str] = []

    _TRACKED_ASSETS: set[str] = {
        pair.split("/")[0] for pair in settings.TRADING_PAIRS
    }

    try:
        account = binance._client.get_account()
        balances: dict[str, float] = {}
        for b in account.get("balances", []):
            asset = b["asset"]
            if asset not in _TRACKED_ASSETS:
                continue
            bal = float(b.get("free", 0)) + float(b.get("locked", 0))
            if bal > 0.000001:
                balances[asset] = bal
    except Exception as exc:
        msg = f"Failed to fetch Binance account balances: {exc}"
        _logger.error(msg)
        send_alert(msg, level="error")
        return

    db_positions_data: list[dict[str, Any]] = []
    with get_db() as db:
        for p in db.query(PositionModel).all():
            db_positions_data.append({
                "symbol": p.symbol,
                "quantity": float(p.quantity),
            })

    for pos in db_positions_data:
        asset = pos["symbol"].replace("/USDT", "")
        db_qty = pos["quantity"]
        exchange_qty = balances.pop(asset, 0.0)

        if db_qty <= 0.000001 and exchange_qty <= 0.000001:
            continue

        # One-directional check: exchange must have at least what DB expects.
        # Extra on exchange (faucet dust on Testnet) is fine — only flag if
        # a position went missing (real state corruption).
        shortfall = Decimal(str(db_qty)) - Decimal(str(exchange_qty))
        tolerance = Decimal(str(db_qty)) * Decimal("0.05")
        if shortfall > tolerance:
            mismatches.append(
                f"{pos['symbol']}: DB={db_qty:.8f} Exchange={exchange_qty:.8f} "
                f"(shortfall={float(shortfall):.8f})"
            )

    # --- Exchange-only check: cross-reference against Trade table ---
    # Assets remaining in `balances` exist on exchange but have no
    # Position row.  Most of the time this is Testnet faucet dust and
    # should be ignored.  However, a Position row can also go missing
    # due to the T13 pipeline-only limitation — if a manual intervention
    # adjusted the Position table and update_positions() later closed
    # out a stale remaining qty, the row is deleted even though trade
    # history still shows net positive quantity.
    #
    # Distinguish the two cases by querying the Trade table: if there
    # is net positive trade quantity for this symbol (BUYs > SELLs) and
    # the exchange balance is material, the Position row is genuinely
    # missing — flag it.
    from sqlalchemy import case as sql_case, func as sql_func

    for orphaned_asset, orphaned_qty in list(balances.items()):
        if orphaned_qty <= 0.000001:
            continue
        orphaned_pair = f"{orphaned_asset}/USDT"
        with get_db() as db:
            net_trade_result = (
                db.query(
                    sql_func.sum(
                        sql_case(
                            (TradeModel.side == "BUY", TradeModel.executed_quantity),
                            (TradeModel.side == "SELL", -TradeModel.executed_quantity),
                            else_=0,
                        )
                    )
                )
                .filter(
                    TradeModel.symbol == orphaned_pair,
                    TradeModel.status == "FILLED",
                )
                .scalar()
            )
        net_trade_qty = float(net_trade_result) if net_trade_result is not None else 0.0
        if net_trade_qty > 0.001:
            mismatches.append(
                f"{orphaned_pair}: Position MISSING (DB=0, Exchange={orphaned_qty:.8f}, "
                f"net_trade_qty={net_trade_qty:.8f}) — trade history shows this asset "
                f"should have a Position row but none exists. Possible T13 pipeline-only drift."
            )

    if mismatches:
        _logger.error(
            "Position reconciliation FAILED — %d mismatch(es):\n%s",
            len(mismatches), "\n".join(f"  • {m}" for m in mismatches),
        )
        try:
            _PAUSE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            _PAUSE_FLAG.touch()
            _logger.warning("Trading auto-paused due to reconciliation failure")
        except Exception as exc:
            _logger.error("Failed to write pause flag: %s", exc)

        send_alert(
            f"🚨 POSITION RECONCILIATION FAILED — {len(mismatches)} mismatch(es). "
            f"Trading auto-paused.\n" + "\n".join(f"• {m}" for m in mismatches),
            level="error",
        )
    else:
        _logger.info("Position reconciliation PASSED — all balances match")

    _logger.info("=== POSITION RECONCILIATION DONE ===")


def run_data_cache_refresh() -> None:
    """Refresh cached OHLCV data without running agents.

    Called every 30 minutes. Fetches fresh pipeline data which
    automatically writes CSVs to ``data_cache/``. Does not execute
    any trades or persist anything to the database.
    """
    _logger.info("=== DATA CACHE REFRESH START ===")
    try:
        DataPipeline().run()
        _logger.info("=== DATA CACHE REFRESH DONE ===")
    except Exception:
        _logger.exception("Data cache refresh failed — full traceback below")


def health_check_job() -> None:
    """Verify the database connection is alive.

    Called every 5 minutes. Logs OK or FAILED based on the result
    of ``check_db_connection()``.
    """
    ok = check_db_connection()
    if ok:
        _logger.info("=== HEALTH CHECK OK ===")
    else:
        _logger.error("=== HEALTH CHECK FAILED ===")


def run_model_training() -> None:
    """Train two models per trading pair on startup: a direction
    classifier (LSTMModel) and a volatility-regime classifier (LSTMClassifier).

    Fetches 1h candles from Binance, engineers technical features,
    and creates two binary targets:
      - ``direction``: 1 if the next candle's return >= 0, else 0.
      - ``target_vol_regime``: 1 if the next 4-candle range exceeds
        the rolling 24-candle median range, else 0.
    Features are min-max normalised using training-set statistics,
    chronologically split 80/10/10, and each model is trained for up
    to 50 epochs with early stopping. Scaler parameters saved to
    ``artifacts/`` so the Predictor can normalise at inference time.
    Total training time for all models is logged at the end.

    All model imports are kept local to avoid circular imports at
    module load time.
    """
    _logger.info("=== MODEL TRAINING START ===")
    _logger.info("Initialising database before training")
    try:
        init_db()
    except Exception:
        _logger.exception("Database initialisation failed — aborting training")
        return

    import json
    import time
    from pathlib import Path

    try:
        import torch
        from torch.utils.data import DataLoader

        from src.data.binance_client import BinanceClient
        from src.data.feature_engineer import FeatureEngineer
        from src.models.lstm_model import LSTMClassifier, LSTMModel, create_sequences
        from src.models.trainer import LSTMClassifierTrainer, LSTMTrainer
        from src.utils.helpers import format_pair_for_binance

        binance = BinanceClient()
        engineer = FeatureEngineer()

        feature_cols = [
            "rsi", "macd", "macd_signal",
            "bb_upper", "bb_middle", "bb_lower",
            "atr", "ema_20", "ema_50",
            "returns", "log_returns", "volatility",
        ]
        seq_len = 24
        batch_size = 32
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "feature_cols": feature_cols,
            "target_cols": ["direction", "target_vol_regime"],
            "seq_len": seq_len,
            "epochs": 50,
            "batch_size": batch_size,
            "learning_rate": 0.001,
        }
        config_path = artifacts_dir / "training_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        _train_start = time.monotonic()

        for pair in settings.TRADING_PAIRS:
            _logger.info("Training models for %s", pair)
            try:
                # Training uses Mainnet read-only historical data (deeper history).
                # Live trading remains exclusively on Testnet.
                ohlcv = binance.get_historical_ohlcv_mainnet(pair, interval="1h", limit=3000)
                features = engineer.compute_features(ohlcv)
                features["direction"] = (features["close"].pct_change().shift(-1) >= 0).astype(int)
                features = features.dropna()

                row_count = len(features)
                if row_count < 500:
                    _logger.warning(
                        "%s: insufficient data (%d rows) — skipping training, "
                        "will use untrained model with safe defaults",
                        pair, row_count,
                    )
                    continue

                # Class balance check
                if row_count > 0:
                    dir_zeros = int((features["direction"] == 0).sum())
                    dir_ones = int((features["direction"] == 1).sum())
                    dir_zero_pct = dir_zeros / row_count * 100
                    dir_one_pct = dir_ones / row_count * 100
                    _logger.info(
                        "Direction class balance for %s — 0=%d (%.1f%%), 1=%d (%.1f%%)",
                        pair, dir_zeros, dir_zero_pct, dir_ones, dir_one_pct,
                    )
                    if dir_zero_pct > 90 or dir_one_pct > 90:
                        _logger.warning(
                            "Severe class imbalance for direction target on %s "
                            "(0: %.1f%%, 1: %.1f%%) — classifier may not learn meaningfully",
                            pair, dir_zero_pct, dir_one_pct,
                        )

                    if "target_vol_regime" in features.columns:
                        v_zeros = int((features["target_vol_regime"] == 0).sum())
                        v_ones = int((features["target_vol_regime"] == 1).sum())
                        v_zero_pct = v_zeros / (v_zeros + v_ones) * 100 if (v_zeros + v_ones) > 0 else 0
                        v_one_pct = v_ones / (v_zeros + v_ones) * 100 if (v_zeros + v_ones) > 0 else 0
                        if v_zero_pct > 90 or v_one_pct > 90:
                            _logger.warning(
                                "Severe class imbalance for volatility target on %s "
                                "(0: %.1f%%, 1: %.1f%%) — classifier may not learn meaningfully",
                                pair, v_zero_pct, v_one_pct,
                            )

                total = len(features)
                train_end = int(total * 0.8)
                val_end = int(total * 0.9)

                train_df = features.iloc[:train_end]
                val_df = features.iloc[train_end:val_end]
                test_df = features.iloc[val_end:]

                train_norm, scalers = engineer.normalize_features(train_df, feature_cols)
                val_norm = engineer.apply_scalers(val_df, feature_cols, scalers)
                test_norm = engineer.apply_scalers(test_df, feature_cols, scalers)

                sym_safe = format_pair_for_binance(pair)

                # --- LSTM direction classifier (with L2 regularisation) ---
                _logger.info("Training direction model for %s", pair)
                dir_train_ds = create_sequences(train_norm, feature_cols, "direction", seq_len, classification=True)
                dir_val_ds = create_sequences(val_norm, feature_cols, "direction", seq_len, classification=True)
                dir_test_ds = create_sequences(test_norm, feature_cols, "direction", seq_len, classification=True)

                dir_train_loader = DataLoader(dir_train_ds, batch_size=batch_size, shuffle=True)
                dir_val_loader = DataLoader(dir_val_ds, batch_size=batch_size, shuffle=False)
                dir_test_loader = DataLoader(dir_test_ds, batch_size=batch_size, shuffle=False)

                model = LSTMModel(input_size=len(feature_cols))
                trainer = LSTMTrainer(
                    model=model,
                    learning_rate=0.001,
                    checkpoint_dir=settings.MODEL_CHECKPOINT_DIR,
                )
                trainer.optimizer = torch.optim.Adam(
                    model.parameters(), lr=0.001, weight_decay=1e-5,
                )
                dir_history = trainer.train(
                    train_loader=dir_train_loader,
                    val_loader=dir_val_loader,
                    epochs=50,
                    symbol=pair,
                    min_epochs=10,
                )

                dir_test_loss, dir_test_acc = trainer.evaluate(dir_test_loader)

                scaler_path = artifacts_dir / f"scaler_{sym_safe}.json"
                with open(scaler_path, "w") as f:
                    json.dump(scalers, f, indent=2)

                metrics_path = artifacts_dir / f"metrics_{sym_safe}.json"

                up_c = up_t = down_c = down_t = 0
                with torch.no_grad():
                    for batch_f, batch_t in dir_test_loader:
                        preds = model(batch_f).argmax(dim=1)
                        for p, a in zip(preds, batch_t):
                            if a.item() == 1:
                                up_t += 1
                                if p.item() == a.item():
                                    up_c += 1
                            else:
                                down_t += 1
                                if p.item() == a.item():
                                    down_c += 1

                total_test = up_t + down_t
                dir_metrics = {
                    "train_loss": dir_history["train_loss"][-1] if dir_history.get("train_loss") else 0,
                    "val_loss": dir_history["val_loss"][-1] if dir_history.get("val_loss") else 0,
                    "test_loss": dir_test_loss,
                    "test_accuracy_pct": round(dir_test_acc, 2),
                    "up_correct": up_c,
                    "up_total": up_t,
                    "down_correct": down_c,
                    "down_total": down_t,
                    "test_samples": total_test,
                }
                with open(metrics_path, "w") as f:
                    json.dump(dir_metrics, f, indent=2)

                last_val = dir_metrics["val_loss"]
                _logger.info(
                    "Direction model for %s — val_loss=%.6f, test_loss=%.6f, test_acc=%.1f%% (%d/%d up, %d/%d down)",
                    pair, last_val, dir_test_loss, dir_test_acc,
                    up_c, up_t, down_c, down_t,
                )

                if last_val > 0.68 and dir_test_acc < 55:
                    _logger.info(
                        "Direction LSTM shows no learnable signal in current feature set "
                        "for %s. Recommend continuing with sentiment-primary strategy.",
                        pair,
                    )

                # --- LSTMClassifier: volatility regime ---
                _logger.info("Training volatility classifier for %s", pair)
                clf_train_ds = create_sequences(train_norm, feature_cols, "target_vol_regime", seq_len, classification=False)
                clf_val_ds = create_sequences(val_norm, feature_cols, "target_vol_regime", seq_len, classification=False)
                clf_test_ds = create_sequences(test_norm, feature_cols, "target_vol_regime", seq_len, classification=False)

                clf_train_loader = DataLoader(clf_train_ds, batch_size=batch_size, shuffle=True)
                clf_val_loader = DataLoader(clf_val_ds, batch_size=batch_size, shuffle=False)
                clf_test_loader = DataLoader(clf_test_ds, batch_size=batch_size, shuffle=False)

                classifier = LSTMClassifier(input_size=len(feature_cols))
                clf_trainer = LSTMClassifierTrainer(
                    model=classifier,
                    learning_rate=0.001,
                    checkpoint_dir=settings.MODEL_CHECKPOINT_DIR,
                )
                clf_history = clf_trainer.train(
                    train_loader=clf_train_loader,
                    val_loader=clf_val_loader,
                    epochs=50,
                    symbol=pair,
                    min_epochs=10,
                )

                clf_test_loss = clf_trainer.evaluate(clf_test_loader)
                clf_test_acc = clf_trainer.evaluate_accuracy(clf_test_loader)

                clf_metrics_path = artifacts_dir / f"metrics_{sym_safe}_classifier.json"
                clf_metrics = {
                    "train_loss": clf_history["train_loss"][-1] if clf_history.get("train_loss") else 0,
                    "val_loss": clf_history["val_loss"][-1] if clf_history.get("val_loss") else 0,
                    "test_loss": clf_test_loss,
                    "test_accuracy_pct": round(clf_test_acc * 100, 2),
                }
                with open(clf_metrics_path, "w") as f:
                    json.dump(clf_metrics, f, indent=2)

                _logger.info(
                    "Volatility classifier for %s — test_loss=%.6f, test_acc=%.1f%%",
                    pair, clf_test_loss, clf_test_acc * 100,
                )
            except Exception:
                _logger.exception("Training failed for %s — skipping", pair)

        _elapsed = time.monotonic() - _train_start
        _logger.info("=== MODEL TRAINING DONE in %.1fs ===", _elapsed)
    except Exception:
        _logger.exception("Model training job failed — full traceback below")
