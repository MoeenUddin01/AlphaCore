"""Real-money performance page for the AlphaCore Streamlit dashboard.

Displays trade performance from the real account: trade log, P&L per
trade, best/worst trade, and aggregate stats — with a red/amber
"LIVE MONEY" colour scheme.
"""

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.database.real_crud import get_real_trade_history

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


def _format_pnl(pnl: float | None) -> str:
    if pnl is None:
        return "-"
    return f"${pnl:+,.2f}"


def render() -> None:
    st.markdown(_LIVE_BANNER, unsafe_allow_html=True)
    st.title("REAL Account — Performance / Trades")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    try:
        trades = get_real_trade_history(limit=200)
    except Exception:
        st.error("Database connection failed — real tables may not exist yet.")
        return

    if not trades:
        st.info("No real trades synced yet.")
        return

    rows: list[dict[str, Any]] = []
    for t in trades:
        rows.append({
            "symbol": t.symbol,
            "side": t.side,
            "status": t.status,
            "executed_price": float(t.executed_price) if t.executed_price else None,
            "executed_quantity": float(t.executed_quantity) if t.executed_quantity else None,
            "pnl": float(t.pnl) if t.pnl is not None else None,
            "fee_paid": float(t.fee_paid) if t.fee_paid else None,
            "order_id": t.order_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    df = pd.DataFrame(rows)

    # ── Filters ──
    st.subheader("Trade Log")
    symbols = sorted(df["symbol"].unique()) if not df.empty else []

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        selected_symbol = st.selectbox("Filter by symbol", ["ALL"] + symbols)
    with col_f2:
        selected_status = st.selectbox("Filter by status", ["ALL", "FILLED", "SYNCED"])

    filtered = df.copy()
    if not filtered.empty:
        if selected_symbol != "ALL":
            filtered = filtered[filtered["symbol"] == selected_symbol]
        if selected_status != "ALL":
            filtered = filtered[filtered["status"] == selected_status]

    # ── Trade table ──
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
        display_df["PnL"] = display_df["PnL"].apply(_format_pnl)

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

    # ── P&L chart ──
    st.subheader("P&L per Trade")
    pnl_data = filtered[filtered["pnl"].notna()].copy()
    if not pnl_data.empty:
        pnl_vals = pnl_data["pnl"]
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Best Trade", f"${pnl_vals.max():+,.2f}")
        with c2:
            st.metric("Worst Trade", f"${pnl_vals.min():+,.2f}")

        chart_df = pnl_data[["created_at", "pnl"]].rename(
            columns={"created_at": "Date", "pnl": "PnL"}
        )
        chart_df = chart_df.sort_values("Date").set_index("Date")
        st.bar_chart(chart_df["PnL"], use_container_width=True, color="#cc0000")
    else:
        st.info("No P&L data to display.")

    # ── Aggregate stats ──
    st.subheader("Aggregate")
    filled = df[df["status"] == "FILLED"].copy()
    if not filled.empty:
        total_pnl = filled["pnl"].sum()
        wins = (filled["pnl"] > 0).sum()
        losses = (filled["pnl"] <= 0).sum()
        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0.0
        avg_pnl = filled["pnl"].mean()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Filled Trades", total)
        with c2:
            st.metric("Win Rate", f"{win_rate:.1f}%")
        with c3:
            pnl_colour = "inverse" if total_pnl < 0 else "normal"
            st.metric("Total P&L", f"${total_pnl:+,.2f}", delta_color=pnl_colour)
        with c4:
            st.metric("Avg P&L", f"${avg_pnl:+,.2f}")
    else:
        st.info("No filled trades to aggregate.")
