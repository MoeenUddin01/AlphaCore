"""Real-trading safety controls page for the AlphaCore Streamlit dashboard.

Displays the kill-switch status, hard-limit configuration, and current
usage.  The kill switch can be toggled via a button + confirmation text
input (must type ``CONFIRM``) for deliberate action only.
"""

from __future__ import annotations

import streamlit as st

from src.database.real_crud import (
    get_real_daily_loss,
    get_real_safety_status,
    get_real_trades_today_count,
    get_real_trading_halted,
    set_real_trading_halted,
)

# ── Styling constants ──────────────────────────────────────────────
_HALTED_STYLE = (
    "background: #8b0000; color: white; padding: 12px 24px; "
    "border-radius: 8px; font-weight: bold; font-size: 20px; text-align: center;"
)
_ACTIVE_STYLE = (
    "background: #006400; color: white; padding: 12px 24px; "
    "border-radius: 8px; font-weight: bold; font-size: 20px; text-align: center;"
)


def _render_kill_switch() -> None:
    """Display the current kill-switch state and toggle controls."""
    halted = get_real_trading_halted()

    if halted:
        st.markdown(f"<div style='{_HALTED_STYLE}'>⛔  REAL TRADING HALTED</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='{_ACTIVE_STYLE}'>✅  REAL TRADING ACTIVE</div>", unsafe_allow_html=True)

    st.divider()

    if halted:
        st.subheader("Enable Real Trading")
        st.caption("Only enable when you are certain market conditions are favourable.")
        confirm = st.text_input("Type **CONFIRM** to enable real trading:", key="enable_confirm")
        if st.button("Enable Trading", type="primary", disabled=(confirm != "CONFIRM")):
            set_real_trading_halted(False)
            st.success("Real trading enabled.")
            st.rerun()
    else:
        st.subheader("Halt Real Trading")
        confirm = st.text_input("Type **CONFIRM** to halt real trading:", key="halt_confirm")
        if st.button("Halt Trading", type="secondary", disabled=(confirm != "CONFIRM")):
            set_real_trading_halted(True)
            st.warning("Real trading halted.")
            st.rerun()


def _render_limits() -> None:
    """Display hard-limit configuration and current usage."""
    from src.utils.config import settings

    status = get_real_safety_status()
    limits = status["limits"]
    daily_loss = status["daily_loss"]
    trades_today = status["trades_today"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Max Position USD",
            f"${float(limits['max_position_usd']):.2f}",
        )

    with col2:
        loss_color = "inverse" if daily_loss < -settings.REAL_MAX_DAILY_LOSS_USD else "off"
        st.metric(
            "Daily Loss / Limit",
            f"${float(daily_loss):.2f} / ${float(limits['max_daily_loss_usd']):.2f}",
            delta=f"${float(daily_loss):.2f}",
            delta_color=loss_color,
        )

    with col3:
        trades_color = "inverse" if trades_today >= limits["max_trades_per_day"] else "off"
        st.metric(
            "Trades Today / Limit",
            f"{trades_today} / {limits['max_trades_per_day']}",
            delta=trades_today,
            delta_color=trades_color,
        )


def render() -> None:
    """Render the Real Safety Controls page."""
    st.title("⚠  Real Safety Controls")
    st.caption("Kill switch and hard limits for real-money trading")

    _render_kill_switch()
    st.divider()
    _render_limits()
