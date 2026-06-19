"""Strategy validation page for the AlphaCore Streamlit dashboard.

Fetches sentiment trade performance data from the API and displays
win-rate, sample-size progress, and sentiment-score comparisons to
help decide whether the strategy is ready for live deployment.
"""

import os
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _safe_get(url: str) -> Any:
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def render() -> None:
    data: dict[str, Any] | None = _safe_get(
        f"{API_BASE_URL}/portfolio/sentiment-validation?days=30"
    )

    if data is None:
        st.error("API server not reachable. Start with: uvicorn src.api.main:app")
        return

    st.title("AlphaCore — Strategy Validation")
    st.caption(
        "Track whether sentiment-driven trading has real edge before going live"
    )

    total = data["total_sentiment_trades"]
    win_rate = data["win_rate_pct"]

    if win_rate < 45:
        colour = "red"
        delta = "⬇ needs improvement"
    elif win_rate <= 55:
        colour = "orange"
        delta = "⬇ borderline"
    else:
        colour = "green"
        delta = "⬆ looking good"

    st.markdown(
        f"<h2 style='color:{colour};'>Win Rate: {win_rate:.1f}%</h2>",
        unsafe_allow_html=True,
    )
    st.metric("Trades Analysed", total, delta=delta)

    st.subheader("Sample Size Progress")
    fraction = min(total / 30, 1.0)
    st.progress(fraction)
    st.caption(f"{total}/30 trades needed for reliable validation")

    if not data["is_statistically_ready"]:
        st.warning("Not enough trades yet for reliable validation. Keep paper trading.")
    elif win_rate > 55:
        st.success("Sentiment signal shows real edge. Consider reviewing for live readiness.")
    else:
        st.error("Sentiment signal is underperforming. Do not go live. Review strategy.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Avg Win Amount", f"${data['avg_win_amount']:,.2f}")
    with col2:
        st.metric("Avg Loss Amount", f"${data['avg_loss_amount']:,.2f}")
    with col3:
        st.metric("Total P&L", f"${data['total_pnl']:,.2f}")

    st.subheader("Sentiment Score: Winners vs Losers")
    score_df = pd.DataFrame({
        "Group": ["Winners", "Losers"],
        "Avg Sentiment Score": [
            data["avg_sentiment_score_winners"],
            data["avg_sentiment_score_losers"],
        ],
    })
    fig = px.bar(
        score_df,
        x="Group",
        y="Avg Sentiment Score",
        color="Group",
        color_discrete_map={"Winners": "#2ecc71", "Losers": "#e74c3c"},
        title="Is stronger sentiment correlated with winning?",
    )
    st.plotly_chart(fig, use_container_width=True)
