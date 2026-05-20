"""ML Signals page for the AlphaCore Streamlit dashboard.

Displays signal summaries, a formatted signal table with direction
indicators, sentiment gauges per symbol, and confidence history
over time.
"""

import os
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st

from src.dashboard.components.charts import sentiment_gauge_chart

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _safe_get(url: str) -> Any:
    """GET an API endpoint and return JSON, or ``None`` on failure."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def render() -> None:
    """Build and display the ML signals page."""
    latest: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/signals/latest"
    )
    summary: dict[str, Any] | None = _safe_get(
        f"{API_BASE_URL}/signals/summary"
    )
    history: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/signals/history?limit=100"
    )

    if latest is None and summary is None and history is None:
        st.error(
            "API server not reachable. Start with: uvicorn src.api.main:app"
        )
        return

    st.title("AlphaCore — ML Signals")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # ── Summary counts ──────────────────────────────────────────
    if summary:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "Bullish",
                summary.get("bullish_count", 0),
                delta_color="off",
            )
            st.markdown(
                f'<p style="color:#2ecc71;font-size:12px;">▲ Up signals</p>',
                unsafe_allow_html=True,
            )
        with col2:
            st.metric(
                "Bearish",
                summary.get("bearish_count", 0),
                delta_color="off",
            )
            st.markdown(
                f'<p style="color:#e74c3c;font-size:12px;">▼ Down signals</p>',
                unsafe_allow_html=True,
            )
        with col3:
            st.metric(
                "Neutral",
                summary.get("neutral_count", 0),
                delta_color="off",
            )
            st.markdown(
                f'<p style="color:#95a5a6;font-size:12px;">● Neutral</p>',
                unsafe_allow_html=True,
            )
    else:
        st.info("No signal summary available.")

    # ── Latest signals table ─────────────────────────────────────
    st.subheader("Latest Signals")
    if latest:
        df = pd.DataFrame(latest)
        df["direction"] = df["direction"].apply(
            lambda d: "🟢" if d == "up" else ("🔴" if d == "down" else "⚪")
        )
        display_cols = [
            "symbol", "direction", "confidence", "sentiment_score",
            "sentiment_label", "fear_greed_value",
        ]
        df_display = df[display_cols].copy()
        df_display.columns = [
            "Symbol", "Direction", "Confidence", "Sentiment",
            "Label", "Fear & Greed",
        ]
        df_display["Confidence"] = df_display["Confidence"].apply(
            lambda x: f"{x:.1%}"
        )
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("No signals available yet.")

    # ── Sentiment gauges ─────────────────────────────────────────
    if latest:
        st.subheader("Sentiment by Symbol")
        cols = st.columns(len(latest))
        for col, sig in zip(cols, latest):
            with col:
                fig = sentiment_gauge_chart(
                    sig.get("sentiment_score", 0),
                    sig.get("symbol", ""),
                )
                st.plotly_chart(fig, use_container_width=True)

    # ── Signal history chart ─────────────────────────────────────
    st.subheader("Confidence Over Time")
    if history:
        hist_df = pd.DataFrame(history)
        symbols = sorted(hist_df["symbol"].unique()) if "symbol" in hist_df.columns else []
        selected = st.selectbox("Filter by symbol", ["All"] + symbols)

        if selected != "All":
            hist_df = hist_df[hist_df["symbol"] == selected]

        if "created_at" in hist_df.columns and "confidence" in hist_df.columns:
            chart_df = hist_df[["created_at", "confidence", "symbol"]].copy()
            chart_df["created_at"] = pd.to_datetime(chart_df["created_at"])
            chart_df = chart_df.sort_values("created_at")
            pivot = chart_df.pivot_table(
                index="created_at",
                columns="symbol",
                values="confidence",
                aggfunc="mean",
            )
            st.line_chart(pivot, use_container_width=True)
        else:
            st.info("Signal history data is incomplete.")
    else:
        st.info("No signal history available.")
