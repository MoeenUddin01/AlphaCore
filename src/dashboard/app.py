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
from src.dashboard.pages.real_controls import render as render_real_controls
from src.dashboard.pages.real_performance import render as render_real_performance
from src.dashboard.pages.real_positions import render as render_real_positions
from src.dashboard.pages.real_risk import render as render_real_risk
from src.dashboard.pages.real_signals import render as render_real_signals
from src.dashboard.pages.real_wallet import render as render_real_wallet
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


_DEMO_PAGES: dict[str, str] = {
    "Overview": "overview",
    "ML Signals": "signals",
    "Trade History": "trades",
    "Risk Dashboard": "risk",
    "Validation": "validation",
}

_REAL_PAGES: dict[str, str] = {
    "Safety Controls": "real_controls",
    "Positions": "real_positions",
    "Portfolio / Wallet": "real_wallet",
    "Signals": "real_signals",
    "Performance": "real_performance",
    "Risk": "real_risk",
}

_MODE_DEMO = "🔬 DEMO (Paper Trading)"
_MODE_REAL = "⚠ REAL (Live Money)"


def _render_real_banner() -> None:
    """Render the red 'LIVE MONEY' banner at the top of every REAL page."""
    st.markdown(
        "<div style='"
        "background: linear-gradient(90deg, #8b0000, #cc0000, #8b0000); "
        "color: white; padding: 10px 20px; border-radius: 6px; text-align: center; "
        "font-weight: bold; font-size: 18px; letter-spacing: 2px; margin-bottom: 16px; "
        "border: 2px solid #ff4444;"
        "'>⚠  REAL — LIVE MONEY  ⚠</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    """Render the sidebar and route to the selected page."""
    st_autorefresh(interval=60000, key="autorefresh")

    st.sidebar.title("AlphaCore 📈")
    st.sidebar.caption("Autonomous Crypto Quant System")

    mode = st.sidebar.radio(
        "Mode",
        [_MODE_DEMO, _MODE_REAL],
        index=0,
        label_visibility="collapsed",
    )

    if mode == _MODE_DEMO:
        page_label = st.sidebar.selectbox(
            "Page", list(_DEMO_PAGES.keys()), index=0,
        )
        page_key = _DEMO_PAGES[page_label]
    else:
        page_label = st.sidebar.selectbox(
            "Page", list(_REAL_PAGES.keys()), index=0,
        )
        page_key = _REAL_PAGES[page_label]

    st.sidebar.divider()

    online = _api_reachable()
    status_emoji = "🟢" if online else "🔴"
    st.sidebar.markdown(f"**System Info**")
    st.sidebar.markdown(f"API Status: {status_emoji}")
    st.sidebar.markdown(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")

    if st.sidebar.button("Refresh Data"):
        st.rerun()

    st.sidebar.divider()

    if mode == _MODE_DEMO:
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
    else:
        st.sidebar.warning("Read-only sync — no trading controls")

    st.sidebar.divider()
    st.sidebar.caption("v1.0.0")

    try:
        if page_key == "overview":
            render_overview()
        elif page_key == "signals":
            render_signals()
        elif page_key == "trades":
            render_trades()
        elif page_key == "risk":
            render_risk()
        elif page_key == "validation":
            render_validation()
        elif page_key == "real_controls":
            _render_real_banner()
            render_real_controls()
        elif page_key == "real_positions":
            _render_real_banner()
            render_real_positions()
        elif page_key == "real_wallet":
            _render_real_banner()
            render_real_wallet()
        elif page_key == "real_signals":
            _render_real_banner()
            render_real_signals()
        elif page_key == "real_performance":
            _render_real_banner()
            render_real_performance()
        elif page_key == "real_risk":
            _render_real_banner()
            render_real_risk()
    except Exception:
        st.exception("An unhandled error occurred on this page.")


if __name__ == "__main__":
    main()
