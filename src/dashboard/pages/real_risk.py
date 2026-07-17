"""Real-money risk page for the AlphaCore Streamlit dashboard.

Displays drawdown tracking, peak value, and risk alerts from the real
account's portfolio snapshots — with a red/amber "LIVE MONEY" scheme.
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


def _compute_drawdown_series(history: list[Any]) -> list[dict]:
    peak = 0.0
    result: list[dict] = []
    for h in history:
        v = float(h.total_value) if h.total_value else 0.0
        peak = max(peak, v)
        dd = ((peak - v) / peak * 100) if peak > 0 else 0.0
        result.append({"created_at": h.created_at, "drawdown": dd})
    return result


def render() -> None:
    st.markdown(_LIVE_BANNER, unsafe_allow_html=True)
    st.title("REAL Account — Risk Dashboard")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    try:
        snap = get_real_latest_snapshot()
        history = get_real_portfolio_history(limit=200)
    except Exception:
        st.error("Database connection failed — real tables may not exist yet.")
        return

    if snap is None:
        st.info("No risk data available yet. Real account sync has not run.")
        return

    current_dd = float(snap.drawdown_pct) if snap.drawdown_pct else 0.0
    peak_value = float(snap.peak_value) if snap.peak_value else 0.0
    total_value = float(snap.total_value) if snap.total_value else 0.0
    realised_pnl = float(snap.realised_pnl) if snap.realised_pnl else 0.0

    # ── Risk metric cards ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        dd_colour = "inverse" if current_dd > 5 else "normal"
        st.metric("Current Drawdown", f"{current_dd:.2f}%", delta_color=dd_colour)
    with c2:
        st.metric("Peak Value", f"${peak_value:,.2f}")
    with c3:
        st.metric("Current Value", f"${total_value:,.2f}")
    with c4:
        pnl_colour = "inverse" if realised_pnl < 0 else "normal"
        st.metric("Realised P&L", f"${realised_pnl:+,.2f}", delta_color=pnl_colour)

    # ── Drawdown chart ──
    st.subheader("Drawdown Over Time")
    if history:
        dd_series = _compute_drawdown_series(history)
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
        st.info("No snapshot history for drawdown chart.")

    # ── Risk alerts ──
    st.subheader("Risk Alerts")
    if current_dd > 15:
        st.error(
            f"🚨 **Critical drawdown alert!** "
            f"Current drawdown is {current_dd:.2f}% — "
            f"exceeds the 15% hard limit. "
            f"Consider pausing the real account sync immediately."
        )
    elif current_dd > 10:
        st.warning(
            f"⚠️ **Drawdown warning.** "
            f"Current drawdown is {current_dd:.2f}% — "
            f"exceeds the 10% soft limit."
        )
    else:
        st.success(
            f"✅ Drawdown is {current_dd:.2f}% — "
            f"within acceptable thresholds."
        )
