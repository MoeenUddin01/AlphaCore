"""Real-money signals placeholder page — ML signals are not applicable.

Sentiment and prediction signals are only generated for the paper-trading
pipeline. The real account does not produce signals; it only syncs trades
and positions from the Binance exchange.
"""

import streamlit as st

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
    st.title("REAL Account — Signals")
    st.caption("ML signals are not applicable to the real-money account.")

    st.info(
        "The real-money account is a read-only sync pipeline. It mirrors "
        "positions and trades from the real Binance account but does not "
        "generate prediction signals or sentiment scores.\n\n"
        "ML signals (LSTM price forecasts + FinBERT sentiment) are produced "
        "by the paper-trading pipeline and can be viewed under the "
        "**ML Signals** tab in the paper-trading section.\n\n"
        "When live trading is enabled in a future upgrade, the Manager "
        "Agent will consume these signals to place orders on your behalf."
    )
