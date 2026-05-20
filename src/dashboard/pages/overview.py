"""Overview page for the AlphaCore Streamlit dashboard.

Displays portfolio value, asset allocation, agent status, sentiment,
and signal confidence — all sourced from the FastAPI backend.
"""

import os
from datetime import datetime
from typing import Any

import requests
import streamlit as st

from src.dashboard.components.charts import (
    asset_allocation_pie,
    portfolio_value_chart,
    signal_confidence_chart,
)
from src.dashboard.components.metrics import (
    render_agent_status_bar,
    render_fear_greed_gauge,
    render_portfolio_header,
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _fear_greed_classification(value: int) -> str:
    """Map a Fear & Greed Index value to its classification label."""
    if value <= 25:
        return "Extreme Fear"
    if value <= 45:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 75:
        return "Greed"
    return "Extreme Greed"


def _safe_get(url: str) -> Any:
    """GET an API endpoint and return JSON, or ``None`` on failure."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def render() -> None:
    """Build and display the full portfolio overview page."""
    history: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/history?limit=100"
    )
    metrics: dict[str, Any] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/metrics"
    )
    signals: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/signals/latest"
    )
    positions: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/positions"
    )
    cycles: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/cycles?limit=1"
    )

    if history is None and metrics is None and signals is None:
        st.error(
            "API server not reachable. Start with: uvicorn src.api.main:app"
        )
        return

    st.title("AlphaCore — Portfolio Overview")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    latest_snapshot: dict[str, Any] | None = None
    if history:
        latest_snapshot = history[0] if len(history) > 0 else None

    if latest_snapshot:
        portfolio_data = {
            "total_value": latest_snapshot.get("total_value", 0),
            "unrealised_pnl": latest_snapshot.get("unrealised_pnl", 0),
            "realised_pnl": latest_snapshot.get("realised_pnl", 0),
            "drawdown_pct": latest_snapshot.get("drawdown_pct", 0),
            "num_positions": len(positions) if positions else 0,
        }
        render_portfolio_header(portfolio_data)
    else:
        st.info("No portfolio data available yet.")

    col_left, col_right = st.columns(2)
    with col_left:
        fig_value = portfolio_value_chart(history or [])
        st.plotly_chart(fig_value, use_container_width=True)
    with col_right:
        fig_allocation = asset_allocation_pie(positions or [])
        st.plotly_chart(fig_allocation, use_container_width=True)

    cycle_log: list[str] | None = None
    if cycles and len(cycles) > 0:
        cycle_log = cycles[0].get("cycle_log")
    render_agent_status_bar(cycle_log or [])

    st.subheader("Market Sentiment")
    if signals and len(signals) > 0:
        fg_value = signals[0].get("fear_greed_value", 50)
        classification = _fear_greed_classification(fg_value)
        render_fear_greed_gauge(fg_value, classification)
    else:
        st.info("No signals available yet.")

    st.subheader("Signal Confidence")
    fig_signals = signal_confidence_chart(signals or [])
    st.plotly_chart(fig_signals, use_container_width=True)
