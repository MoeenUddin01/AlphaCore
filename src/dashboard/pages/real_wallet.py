"""Real-money wallet / portfolio page for the AlphaCore Streamlit dashboard.

Displays the latest portfolio snapshot from the real account: total
value, cash, P&L splits, drawdown, and snapshot history chart with a
red/amber "LIVE MONEY" colour scheme.
"""

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.database.real_crud import get_real_latest_snapshot, get_real_portfolio_history

_LIVE_BANNER = """
<div style="
    background: linear-gradient(90deg, #8b0000, #cc0000, #8b0000);
    color: white;
    padding: 10px 20px;
    border-radius: 6px;
    text-align: center;
    font-weight: bold;
    font-size: 18px;
    letter-spacing: 2px;
    margin-bottom: 16px;
    border: 2px solid #ff4444;
">
    ⚠ REAL — LIVE MONEY ⚠
</div>
"""


def render() -> None:
    st.markdown(_LIVE_BANNER, unsafe_allow_html=True)
    st.title("REAL Account — Portfolio / Wallet")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    try:
        snap = get_real_latest_snapshot()
        history = get_real_portfolio_history(limit=100)
    except Exception:
        st.error("Database connection failed — real tables may not exist yet.")
        return

    if snap is None:
        st.info("No portfolio data available yet. Real account sync has not run.")
        return

    total_val = float(snap.total_value) if snap.total_value else 0.0
    cash = float(snap.cash) if snap.cash else 0.0
    pos_val = float(snap.positions_value) if snap.positions_value else 0.0
    upnl = float(snap.unrealised_pnl) if snap.unrealised_pnl else 0.0
    rpnl = float(snap.realised_pnl) if snap.realised_pnl else 0.0
    dd = float(snap.drawdown_pct) if snap.drawdown_pct else 0.0
    peak = float(snap.peak_value) if snap.peak_value else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Value", f"${total_val:,.2f}")
    with c2:
        dd_colour = "inverse" if dd > 5 else "normal"
        st.metric("Drawdown", f"{dd:.2f}%", delta_color=dd_colour)
    with c3:
        pnl_colour = "inverse" if rpnl < 0 else "normal"
        st.metric("Realised P&L", f"${rpnl:+,.2f}", delta_color=pnl_colour)
    with c4:
        st.metric("Cash", f"${cash:,.2f}")

    c1b, c2b = st.columns(2)
    with c1b:
        st.metric("Positions Value", f"${pos_val:,.2f}")
    with c2b:
        st.metric("Peak Value", f"${peak:,.2f}")

    # ── Portfolio value chart ──
    st.subheader("Portfolio Value Over Time")
    if history:
        chart_rows = []
        for h in history:
            chart_rows.append({
                "created_at": h.created_at,
                "total_value": float(h.total_value) if h.total_value else 0.0,
            })
        chart_df = pd.DataFrame(chart_rows)
        if not chart_df.empty:
            chart_df = chart_df.sort_values("created_at").set_index("created_at")
            st.line_chart(
                chart_df["total_value"],
                use_container_width=True,
                color="#cc0000",
            )
    else:
        st.info("No snapshot history available.")

    # ── Drawdown chart ──
    st.subheader("Drawdown Over Time")
    if history:
        peak_so_far = 0.0
        dd_rows = []
        for h in history:
            v = float(h.total_value) if h.total_value else 0.0
            peak_so_far = max(peak_so_far, v)
            dd_pct = ((peak_so_far - v) / peak_so_far * 100) if peak_so_far > 0 else 0.0
            dd_rows.append({"created_at": h.created_at, "drawdown": dd_pct})

        dd_df = pd.DataFrame(dd_rows)
        if not dd_df.empty:
            dd_df = dd_df.sort_values("created_at").set_index("created_at")
            st.line_chart(
                dd_df["drawdown"],
                use_container_width=True,
                color="#ff6b6b",
            )
    else:
        st.info("No drawdown data available.")
