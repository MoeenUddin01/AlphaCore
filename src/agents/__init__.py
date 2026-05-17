"""LangGraph agent pipeline builder and cycle runner.

Wires the four agents (Manager, Risk, Execution, Portfolio Monitor)
into a sequential StateGraph and provides ``run_cycle()`` as the
top-level entry point for the trading loop.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from langgraph.graph import END, StateGraph

from src.agents.agent_state import AgentState
from src.agents.execution_agent import ExecutionAgent
from src.agents.manager_agent import ManagerAgent
from src.agents.portfolio_monitor import PortfolioMonitor
from src.agents.risk_agent import RiskAgent
from src.utils.logger import get_logger

_logger = get_logger(__name__)


def build_agent_pipeline() -> StateGraph:
    """Build and compile the LangGraph agent pipeline.

    Nodes execute in strict order:

        START → manager → risk → execution → monitor → END

    Returns:
        A compiled :class:`StateGraph` ready for ``.invoke()``.
    """
    _logger.info("Building agent pipeline")

    manager = ManagerAgent()
    risk = RiskAgent()
    execution = ExecutionAgent()
    monitor = PortfolioMonitor()

    graph = StateGraph(AgentState)

    graph.add_node("manager", manager.run)
    graph.add_node("risk", risk.run)
    graph.add_node("execution", execution.run)
    graph.add_node("monitor", monitor.run)

    graph.set_entry_point("manager")
    graph.add_edge("manager", "risk")
    graph.add_edge("risk", "execution")
    graph.add_edge("execution", "monitor")
    graph.add_edge("monitor", END)

    compiled = graph.compile()
    _logger.info("Agent pipeline compiled successfully")
    return compiled


def run_cycle(
    pipeline_data: dict[str, Any],
    portfolio_summary: dict[str, Any] | None = None,
) -> AgentState:
    """Execute one full trading cycle through all four agents.

    Args:
        pipeline_data: Output from ``DataPipeline.run()`` keyed by pair.
        portfolio_summary: Previous cycle's portfolio summary dict, or
            an empty dict for the first cycle.

    Returns:
        Final :class:`AgentState` after the entire pipeline completes.
    """
    cycle_id = str(uuid4())
    now = datetime.utcnow()
    _logger.info("Starting cycle %s", cycle_id)

    initial_state: AgentState = {
        "cycle_id": cycle_id,
        "timestamp": now,
        "pipeline_data": pipeline_data,
        "signals": [],
        "proposed_trades": [],
        "approved_trades": [],
        "executed_trades": [],
        "portfolio_summary": portfolio_summary or {},
        "risk_report": {},
        "cycle_log": [
            f"[{now.isoformat()}] Cycle {cycle_id} started",
        ],
    }

    graph = build_agent_pipeline()
    final_state = graph.invoke(initial_state)
    _logger.info("Cycle %s completed", cycle_id)
    return final_state
