"""Real-money positions page for the AlphaCore Streamlit dashboard.

Displays open positions from the real Binance account with a red/amber
"LIVE MONEY" colour scheme. All data sourced from RealPosition table.
"""

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.database.real_crud import get_real_positions

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
    st.title("REAL Account — Open Positions")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    try:
        positions = get_real_positions()
    except Exception:
        st.error("Database connection failed — real tables may not exist yet.")
        return

    if not positions:
        st.info("No open positions in the real account.")
        return

    rows: list[dict[str, Any]] = []
    for p in positions:
        unrealised = float(p.unrealised_pnl) if p.unrealised_pnl else 0.0
        entry = float(p.avg_entry_price) if p.avg_entry_price else 0.0
        current = float(p.current_price) if p.current_price else 0.0
        change_pct = ((current - entry) / entry * 100) if entry > 0 else 0.0

        rows.append({
            "Symbol": p.symbol,
            "Quantity": float(p.quantity) if p.quantity else 0.0,
            "Avg Entry": f"${entry:,.2f}",
            "Current Price": f"${current:,.2f}",
            "Unrealised P&L": f"${unrealised:+,.2f}",
            "Change %": f"{change_pct:+.2f}%",
            "Updated": p.updated_at.strftime("%Y-%m-%d %H:%M") if p.updated_at else "-",
        })

    df = pd.DataFrame(rows)

    def _colour_pnl(val: str) -> str:
        try:
            num = float(val.replace("$", "").replace(",", ""))
            return "#ff6b6b" if num < 0 else "#69db7c" if num > 0 else "inherit"
        except (ValueError, AttributeError):
            return "inherit"

    styled = df.style.map(_colour_pnl, subset=["Unrealised P&L", "Change %"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    total_upnl = sum(float(p.unrealised_pnl) for p in positions if p.unrealised_pnl)
    total_value = sum(
        float(p.quantity) * float(p.current_price)
        for p in positions if p.quantity and p.current_price
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Open Positions", len(positions))
    with c2:
        st.metric("Total Value", f"${total_value:,.2f}")
    with c3:
        colour = "inverse" if total_upnl < 0 else "normal"
        st.metric("Total Unrealised P&L", f"${total_upnl:+,.2f}", delta_color=colour)
    with c4:
        st.metric("Symbols", ", ".join(p.symbol.replace("/USDT", "") for p in positions))
