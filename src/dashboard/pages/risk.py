"""Risk metrics page for the AlphaCore Streamlit dashboard.

Displays drawdown tracking, peak value, win rate, average P&L,
a drawdown chart over time, cycle performance table, and risk
alerts for breach thresholds.
"""

import os
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _safe_get(url: str) -> Any:
    """GET an API endpoint and return JSON, or ``None`` on failure."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def _compute_drawdown_from_history(history: list[dict]) -> list[dict]:
    """Compute drawdown percentage at each snapshot.

    Drawdown at step *i* is ``(peak_so_far - current) / peak_so_far * 100``.

    Args:
        history: List of snapshot dicts (chronological order recommended).

    Returns:
        List of dicts with ``created_at`` and ``drawdown`` keys.
    """
    peak = 0.0
    result: list[dict] = []
    for snap in history:
        value = float(snap.get("total_value", 0))
        peak = max(peak, value)
        dd = ((peak - value) / peak * 100) if peak > 0 else 0.0
        result.append({"created_at": snap.get("created_at"), "drawdown": dd})
    return result


def render() -> None:
    """Build and display the risk dashboard page."""
    metrics: dict[str, Any] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/metrics"
    )
    history: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/history?limit=200"
    )
    cycles: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/cycles?limit=20"
    )

    if metrics is None and history is None:
        st.error(
            "API server not reachable. Start with: uvicorn src.api.main:app"
        )
        return

    st.title("AlphaCore — Risk Dashboard")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # ── Risk metric cards ────────────────────────────────────────
    drawdown = metrics.get("current_drawdown", 0) if metrics else 0
    peak_value = 0.0
    if history:
        peak_value = max(float(s.get("total_value", 0)) for s in history)

    win_rate = metrics.get("win_rate", 0) if metrics else 0
    avg_pnl = metrics.get("avg_pnl", 0) if metrics else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        dd_colour = "inverse" if float(drawdown) > 5 else "normal"
        st.metric(
            "Current Drawdown",
            f"{float(drawdown):.2f}%",
            delta_color=dd_colour,
        )
    with col2:
        st.metric("Peak Portfolio Value", f"${peak_value:,.2f}")
    with col3:
        st.metric("Win Rate", f"{float(win_rate) * 100:.1f}%")
    with col4:
        st.metric("Avg P&L per Trade", f"${float(avg_pnl):+,.2f}")

    # ── Drawdown chart ───────────────────────────────────────────
    st.subheader("Drawdown Over Time")
    if history:
        dd_series = _compute_drawdown_from_history(history)
        dd_df = pd.DataFrame(dd_series)
        if not dd_df.empty:
            dd_df["created_at"] = pd.to_datetime(dd_df["created_at"])
            dd_df = dd_df.sort_values("created_at").set_index("created_at")
            st.line_chart(
                dd_df["drawdown"],
                use_container_width=True,
                color="#e74c3c",
            )
    else:
        st.info("No portfolio history available for drawdown chart.")

    # ── Cycle performance table ──────────────────────────────────
    st.subheader("Cycle Performance")
    if cycles:
        df = pd.DataFrame(cycles)
        display_cols = [
            "cycle_id", "signals_count", "approved_count",
            "executed_count", "portfolio_value", "drawdown_pct",
        ]
        df_display = df[display_cols].copy()
        df_display.columns = [
            "Cycle ID", "Signals", "Approved",
            "Executed", "Portfolio Value", "Drawdown %",
        ]
        df_display["Portfolio Value"] = df_display["Portfolio Value"].apply(
            lambda x: f"${x:,.2f}" if pd.notna(x) else "-"
        )
        df_display["Drawdown %"] = df_display["Drawdown %"].apply(
            lambda x: f"{x:.2f}%" if pd.notna(x) else "-"
        )
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("No cycle data available.")

    # ── Risk alerts ──────────────────────────────────────────────
    st.subheader("Risk Alerts")
    current_dd = float(drawdown)
    if current_dd > 15:
        st.error(
            f"🚨 **Critical drawdown alert!** "
            f"Current drawdown is {current_dd:.2f}% — "
            f"exceeds the 15% hard limit. "
            f"Consider halting trading immediately."
        )
    elif current_dd > 10:
        st.warning(
            f"⚠️ **Drawdown warning.** "
            f"Current drawdown is {current_dd:.2f}% — "
            f"exceeds the 10% soft limit. "
            f"Review risk exposure and tighten stop-losses."
        )
    else:
        st.success(
            f"✅ Drawdown is {current_dd:.2f}% — "
            f"within acceptable thresholds."
        )
