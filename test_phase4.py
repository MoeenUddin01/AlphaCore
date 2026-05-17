#!/usr/bin/env python3
"""Temporary test script for Phase 4 agent pipeline."""

from decimal import Decimal

from src.agents import run_cycle
from src.data.data_pipeline import DataPipeline

print("=== Phase 4 Agent Pipeline Test ===")
print("Step 1: Fetching pipeline data...")
pipeline = DataPipeline()
pipeline_data = pipeline.run()

portfolio_summary = {
    "total_value": Decimal("10000"),
    "cash": Decimal("10000"),
    "holdings": {},
    "peak_value": Decimal("10000"),
    "drawdown_pct": 0.0,
}

print("Step 2: Running agent cycle...")
final_state = run_cycle(pipeline_data, portfolio_summary)

print(f"\n=== Results ===")
print(f"  Signals generated:     {len(final_state['signals'])}")
print(f"  Proposed trades:       {len(final_state['proposed_trades'])}")
print(f"  Approved trades:       {len(final_state['approved_trades'])}")
print(f"  Executed trades:       {len(final_state['executed_trades'])}")

print(f"\n  Risk report:")
for k, v in final_state["risk_report"].items():
    print(f"    {k}: {v}")

print(f"\n  Portfolio summary:")
for k, v in final_state["portfolio_summary"].items():
    print(f"    {k}: {v}")

print(f"\n  Cycle log:")
for line in final_state["cycle_log"]:
    print(f"    {line}")

print("\nPhase 4 agents OK")
