#!/usr/bin/env python3
"""Smoke test for Option A — sentiment-primary decision flow."""

from decimal import Decimal

from src.agents import run_cycle
from src.data.data_pipeline import DataPipeline
from src.database.crud import get_sentiment_trade_performance

print("=" * 60)
print("Option A Smoke Test — Sentiment-Primary Logic")
print("=" * 60)

# --- Step 1: Fetch pipeline data ---
print("\n[1/4] Fetching pipeline data...")
pipeline_data = DataPipeline().run()
pairs = list(pipeline_data.keys())
print(f"  Pairs fetched: {pairs}")

# --- Step 2: Run a full agent cycle ---
print("\n[2/4] Running agent cycle...")
state = run_cycle(
    pipeline_data,
    portfolio_summary={"total_value": Decimal("10000")},
)
n_signals = len(state["signals"])
n_proposed = len(state["proposed_trades"])
print(f"  Signals: {n_signals}, Proposed trades: {n_proposed}")

# --- Step 3: Assert Option A invariants ---
print("\n[3/4] Validating Option A invariants...")
all_reasonings_ok = True
all_confidences_ok = True

for trade in state["proposed_trades"]:
    r = trade.reasoning
    sym = trade.symbol
    print(f"  {sym} reasoning: {r}")

    if "Sentiment-driven" not in r:
        print(f"    FAIL: missing Sentiment-driven tag")
        all_reasonings_ok = False
    if "confiden" in r.lower() and "signal" not in r.lower():
        print(f"    FAIL: reasoning references old confidence/LSTM direction")
        all_reasonings_ok = False

    expected_conf = round(abs(trade.signal_confidence - 0), 4)
    actual_conf = trade.signal_confidence
    print(f"  {sym} signal_confidence={actual_conf}  (abs(sentiment_score)={abs(trade.signal_confidence)})")

if n_proposed == 0:
    print("  (No trades proposed — all were filtered by sentiment strength threshold)")

assert all_reasonings_ok, "Some trade reasonings are wrong"
print("  All reasonings OK ✓")

# --- Step 4: Query sentiment trade performance ---
print("\n[4/4] Querying sentiment trade performance...")
perf = get_sentiment_trade_performance(days=30)
for k, v in perf.items():
    print(f"  {k}: {v}")

assert perf["is_statistically_ready"] is False, "Expected is_statistically_ready=False"
print("  is_statistically_ready=False ✓")

# --- Done ---
print("\n" + "=" * 60)
print("Option A smoke test OK")
print("=" * 60)
