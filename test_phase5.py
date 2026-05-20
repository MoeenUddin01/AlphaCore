"""Phase 5 smoke test — real agent cycle with database persistence."""

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from src.database.connection import init_db, check_db_connection
from src.database.crud import save_cycle, get_portfolio_history, get_performance_metrics
from src.data.data_pipeline import DataPipeline
from src.agents import run_cycle

# 1. Initialise database
init_db()
print("init_db() complete")

# 2. Check connection
ok = check_db_connection()
print(f"check_db_connection() -> {ok}")

# 3. Run a real agent cycle
print("Fetching pipeline data ...")
pipeline = DataPipeline()
pipeline_data = pipeline.run()

print("Running agent cycle ...")
initial_portfolio = {
    "cash": 10000.0,
    "total_value": 10000.0,
    "total_position_value": 0.0,
    "total_unrealized_pnl": 0.0,
    "total_realised_pnl": 0.0,
    "peak_value": 10000.0,
    "drawdown_pct": 0.0,
    "num_positions": 0,
    "positions": [],
}
final_state = run_cycle(pipeline_data, initial_portfolio)
print(f"Agent cycle completed — {len(final_state.get('signals', []))} signals, {len(final_state.get('executed_trades', []))} trades")

# 4. Persist to database
cycle_id = save_cycle(final_state)
print(f"save_cycle() -> {cycle_id}")

# 5. Query portfolio history
history = get_portfolio_history(limit=5)
print(f"get_portfolio_history(limit=5) -> {history}")

# 6. Query performance metrics
metrics = get_performance_metrics()
print(f"get_performance_metrics() -> {metrics}")

print("Phase 5 database OK")
