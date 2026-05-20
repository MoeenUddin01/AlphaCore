"""Trade history page for the AlphaCore Streamlit dashboard.

Displays trade statistics, a filterable trade table, P&L bar chart,
and best/worst trade highlights.
"""

import os
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st

from src.dashboard.components.charts import pnl_bar_chart

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _safe_get(url: str) -> Any:
    """GET an API endpoint and return JSON, or ``None`` on failure."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def _format_pnl(pnl: float | None) -> str:
    """Format a P&L value as a dollar string with sign."""
    if pnl is None:
        return "-"
    return f"${pnl:+,.2f}"


def render() -> None:
    """Build and display the trade history page."""
    trades: list[dict[str, Any]] | None = _safe_get(
        f"{API_BASE_URL}/trades/history?limit=200"
    )
    stats: dict[str, Any] | None = _safe_get(
        f"{API_BASE_URL}/trades/stats"
    )

    if trades is None and stats is None:
        st.error(
            "API server not reachable. Start with: uvicorn src.api.main:app"
        )
        return

    st.title("AlphaCore — Trade History")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # ── Stats row ────────────────────────────────────────────────
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Trades", stats.get("total_trades", 0))
        with col2:
            filled = stats.get("total_filled", 0)
            total = stats.get("total_trades", 0)
            win_rate = (filled / total * 100) if total > 0 else 0.0
            st.metric("Win Rate", f"{win_rate:.1f}%")
        with col3:
            st.metric("Total Realised P&L", f"${stats.get('total_realised_pnl', 0):,.2f}")
        with col4:
            st.metric("Most Traded", stats.get("most_traded_symbol", "-"))
    else:
        st.info("No trade stats available.")

    # ── Filters ──────────────────────────────────────────────────
    st.subheader("Trade Log")
    df = pd.DataFrame(trades) if trades else pd.DataFrame()

    symbols = sorted(df["symbol"].unique()) if not df.empty else []
    statuses = ["ALL", "FILLED", "FAILED"]

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        selected_symbol = st.selectbox("Filter by symbol", ["ALL"] + symbols)
    with col_f2:
        selected_status = st.selectbox("Filter by status", statuses)

    filtered = df.copy()
    if not filtered.empty:
        if selected_symbol != "ALL":
            filtered = filtered[filtered["symbol"] == selected_symbol]
        if selected_status != "ALL":
            filtered = filtered[filtered["status"] == selected_status]

    # ── Trade table ──────────────────────────────────────────────
    if not filtered.empty:
        display_df = filtered[[
            "symbol", "side", "status", "executed_price",
            "executed_quantity", "pnl", "created_at",
        ]].copy()

        display_df.columns = [
            "Symbol", "Side", "Status", "Price", "Qty", "PnL", "Date",
        ]
        display_df["Price"] = display_df["Price"].apply(
            lambda x: f"${x:,.2f}" if pd.notna(x) else "-"
        )
        display_df["Qty"] = display_df["Qty"].apply(
            lambda x: f"{x:.6f}" if pd.notna(x) else "-"
        )
        display_df["PnL"] = display_df["PnL"].apply(
            lambda x: _format_pnl(x)
        )

        html_rows = ""
        for _, row in filtered.iterrows():
            side_colour = "#2ecc71" if row.get("side") == "BUY" else "#e74c3c"
            html_rows += (
                f"<tr>"
                f"<td>{row.get('symbol', '')}</td>"
                f"<td style='color:{side_colour};font-weight:bold;'>{row.get('side', '')}</td>"
                f"<td>{row.get('status', '')}</td>"
                f"<td>${row.get('executed_price', 0):,.2f}</td>"
                f"<td>{row.get('executed_quantity', 0):.6f}</td>"
                f"<td>{_format_pnl(row.get('pnl'))}</td>"
                f"<td>{row.get('created_at', '')}</td>"
                f"</tr>"
            )

        table_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
                <tr style="border-bottom:2px solid #555;">
                    <th style="padding:6px;text-align:left;">Symbol</th>
                    <th style="padding:6px;text-align:left;">Side</th>
                    <th style="padding:6px;text-align:left;">Status</th>
                    <th style="padding:6px;text-align:left;">Price</th>
                    <th style="padding:6px;text-align:left;">Qty</th>
                    <th style="padding:6px;text-align:left;">PnL</th>
                    <th style="padding:6px;text-align:left;">Date</th>
                </tr>
            </thead>
            <tbody>
                {html_rows}
            </tbody>
        </table>
        """
        st.markdown(table_html, unsafe_allow_html=True)
    else:
        st.info("No trades match the current filters.")

    # ── P&L chart ────────────────────────────────────────────────
    st.subheader("P&L per Trade Over Time")
    if not filtered.empty:
        chart_data = filtered[filtered["pnl"].notna()].copy()
        chart_data = chart_data.rename(columns={"created_at": "created_at", "pnl": "realised_pnl"})
        fig = pnl_bar_chart(chart_data.to_dict("records"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No P&L data to display.")

    # ── Best / Worst trade ──────────────────────────────────────
    if not filtered.empty and "pnl" in filtered.columns:
        pnl_values = filtered["pnl"].dropna()
        if not pnl_values.empty:
            best = pnl_values.max()
            worst = pnl_values.min()
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Best Trade", f"${best:+,.2f}")
            with c2:
                st.metric("Worst Trade", f"${worst:+,.2f}")
