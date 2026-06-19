"""Streamlit application entry point for the AlphaCore dashboard.

Configures the page layout, builds the sidebar navigation, and routes
to the correct page renderer. Includes auto-refresh every 60 seconds.
"""

import os
from datetime import datetime

import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.dashboard.pages.overview import render as render_overview
from src.dashboard.pages.risk import render as render_risk
from src.dashboard.pages.signals import render as render_signals
from src.dashboard.pages.trades import render as render_trades
from src.dashboard.pages.validation import render as render_validation

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="AlphaCore",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _api_reachable() -> bool:
    """Check whether the FastAPI backend is reachable."""
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def main() -> None:
    """Render the sidebar and route to the selected page."""
    st_autorefresh(interval=60000, key="autorefresh")

    st.sidebar.title("AlphaCore 📈")
    st.sidebar.caption("Autonomous Crypto Quant System")

    page = st.sidebar.selectbox(
        "Navigate",
        ["Overview", "ML Signals", "Trade History", "Risk Dashboard", "Validation"],
    )

    st.sidebar.divider()

    online = _api_reachable()
    status_emoji = "🟢" if online else "🔴"
    st.sidebar.markdown(f"**System Info**")
    st.sidebar.markdown(f"API Status: {status_emoji}")
    st.sidebar.markdown(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")

    if st.sidebar.button("Refresh Data"):
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("**Trading Controls**")

    col1, col2 = st.sidebar.columns(2)
    if col1.button("⏸ Pause"):
        try:
            r = requests.post(f"{API_BASE_URL}/portfolio/pause-trading", timeout=5)
            st.sidebar.success(r.json().get("message", "Paused"))
        except requests.RequestException:
            st.sidebar.error("API unreachable")

    if col2.button("▶ Resume"):
        try:
            r = requests.post(f"{API_BASE_URL}/portfolio/resume-trading", timeout=5)
            st.sidebar.success(r.json().get("message", "Resumed"))
        except requests.RequestException:
            st.sidebar.error("API unreachable")

    st.sidebar.divider()
    st.sidebar.caption("v1.0.0")

    try:
        if page == "Overview":
            render_overview()
        elif page == "ML Signals":
            render_signals()
        elif page == "Trade History":
            render_trades()
        elif page == "Risk Dashboard":
            render_risk()
        elif page == "Validation":
            render_validation()
    except Exception:
        st.exception("An unhandled error occurred on this page.")


if __name__ == "__main__":
    main()
