"""Reusable Streamlit metric card components for the AlphaCore dashboard.

Provides building-block UI elements for displaying key-value metrics,
portfolio header rows, agent status bars, and Fear & Greed gauges.
"""

import streamlit as st


def render_metric_card(
    label: str,
    value: str,
    delta: str | None = None,
    delta_color: str = "normal",
) -> None:
    """Render a single metric card using Streamlit's built-in metric.

    Args:
        label: Short description displayed above the value.
        value: Primary metric value (formatted as a string).
        delta: Optional change indicator shown below the value.
        delta_color: Colour for the delta arrow —
            ``"normal"`` (green up / red down), ``"inverse"``,
            or ``"off"``.
    """
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def render_portfolio_header(portfolio_data: dict) -> None:
    """Display a row of four portfolio-level metric cards.

    Cards show Total Value, Total P&L, Drawdown, and Open Positions
    in a horizontal layout using ``st.columns(4)``.

    Args:
        portfolio_data: Dict with keys ``total_value``, ``unrealised_pnl``,
            ``realised_pnl``, ``drawdown_pct``, and ``num_positions``.
    """
    total_value = portfolio_data.get("total_value", 0)
    total_pnl = portfolio_data.get("unrealised_pnl", 0) + portfolio_data.get("realised_pnl", 0)
    drawdown = portfolio_data.get("drawdown_pct", 0)
    num_positions = portfolio_data.get("num_positions", 0)

    delta_sign = "inverse" if total_pnl < 0 else "normal"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card("Total Value", f"${float(total_value):,.2f}")
    with col2:
        render_metric_card(
            "Total P&L",
            f"${float(total_pnl):+,.2f}",
            delta_color=delta_sign,
        )
    with col3:
        render_metric_card(
            "Drawdown",
            f"{float(drawdown):.2f}%",
            delta=f"{float(drawdown):.2f}%" if float(drawdown) > 0 else None,
            delta_color="inverse",
        )
    with col4:
        render_metric_card("Open Positions", str(num_positions))


def render_agent_status_bar(cycle_log: list[str]) -> None:
    """Display a horizontal agent status bar with colour-coded indicators.

    Four columns representing Manager, Risk, Execution, and Monitor agents.
    Each box turns **green** if the corresponding log entry contains no
    errors, or **red** if an error-level message is found.

    Args:
        cycle_log: List of timestamped log strings from the agent pipeline.
    """
    agent_names = ["Manager", "Risk", "Execution", "Monitor"]

    statuses: dict[str, str] = {}
    for name in agent_names:
        matching = [msg for msg in cycle_log if name in msg]
        statuses[name] = "error" if any("error" in msg.lower() for msg in matching) else "ok"

    cols = st.columns(4)
    for col, name in zip(cols, agent_names):
        colour = "#2ecc71" if statuses[name] == "ok" else "#e74c3c"
        with col:
            st.markdown(
                f"""
                <div style="
                    background-color: {colour};
                    color: white;
                    padding: 8px;
                    border-radius: 6px;
                    text-align: center;
                    font-weight: bold;
                    font-size: 14px;
                ">
                    {name}
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_fear_greed_gauge(value: int, classification: str) -> None:
    """Render a colour-coded horizontal gauge for the Fear & Greed Index.

    The progress bar fills to ``value`` percent and is coloured according
    to the standard Fear & Greed zones:

        - **Red** (0–25): Extreme Fear
        - **Orange** (26–45): Fear
        - **Yellow** (46–55): Neutral
        - **Light green** (56–75): Greed
        - **Green** (76–100): Extreme Greed

    Args:
        value: Fear & Greed Index value (0–100).
        classification: Text label for the zone (e.g. ``"Fear"``).
    """
    clamped = max(0, min(100, value))

    if clamped <= 25:
        colour = "#e74c3c"
    elif clamped <= 45:
        colour = "#e67e22"
    elif clamped <= 55:
        colour = "#f1c40f"
    elif clamped <= 75:
        colour = "#2ecc71"
    else:
        colour = "#27ae60"

    st.markdown(
        f"""
        <div style="margin-bottom: 4px; font-weight: bold;">
            Fear & Greed: {classification} ({clamped})
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.progress(clamped / 100)

    st.markdown(
        f"""
        <div style="
            background-color: {colour};
            height: 6px;
            width: 100%;
            border-radius: 3px;
            margin-top: -18px;
            opacity: 0.5;
        "></div>
        """,
        unsafe_allow_html=True,
    )
