"""Reusable Plotly chart components for the AlphaCore dashboard.

Provides five chart factories that return ``go.Figure`` objects with
a consistent dark theme — background ``#0e1117``, white text, no
gridlines. Charts are never rendered inside this file; calling code
passes the figure to ``st.plotly_chart``.
"""

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_DARK_BG = "#0e1117"
_WHITE = "#ffffff"
_GREEN = "#2ecc71"
_RED = "#e74c3c"
_BLUE = "#3498db"

_BASE_AXIS: dict[str, Any] = {"showgrid": False, "color": _WHITE}

_THEME_LAYOUT: dict[str, Any] = {
    "plot_bgcolor": _DARK_BG,
    "paper_bgcolor": _DARK_BG,
    "font": {"color": _WHITE, "size": 12},
    "margin": {"l": 60, "r": 20, "t": 30, "b": 40},
    "legend": {"font": {"color": _WHITE}},
}


def portfolio_value_chart(history: list[dict]) -> go.Figure:
    """Line chart of portfolio total value over time.

    Args:
        history: List of snapshot dicts with ``created_at`` and
            ``total_value`` keys, ordered chronologically.

    Returns:
        A Plotly figure with a green filled line chart.
    """
    df = pd.DataFrame(history)
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_THEME_LAYOUT, title="Portfolio Value (no data)")
        return fig

    df = df.sort_values("created_at")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["created_at"],
            y=df["total_value"],
            mode="lines",
            line={"color": _GREEN, "width": 2},
            fill="tozeroy",
            fillcolor="rgba(46, 204, 113, 0.15)",
            name="Portfolio Value",
        )
    )
    fig.update_layout(
        **_THEME_LAYOUT,
        title="Portfolio Value Over Time",
        xaxis={**_BASE_AXIS},
        yaxis={**_BASE_AXIS, "tickprefix": "$"},
    )
    return fig


def pnl_bar_chart(history: list[dict]) -> go.Figure:
    """Bar chart of realised P&L per cycle snapshot.

    Bars are coloured **green** for positive P&L and **red** for
    negative.

    Args:
        history: List of snapshot dicts with ``created_at`` and
            ``realised_pnl`` keys.

    Returns:
        A Plotly figure with colour-coded bars.
    """
    df = pd.DataFrame(history)
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_THEME_LAYOUT, title="P&L per Cycle (no data)")
        return fig

    df = df.sort_values("created_at")
    colours = [_GREEN if v >= 0 else _RED for v in df["realised_pnl"]]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["created_at"],
            y=df["realised_pnl"],
            marker_color=colours,
            name="Realised P&L",
        )
    )
    fig.update_layout(
        **_THEME_LAYOUT,
        title="P&L per Cycle",
        xaxis={**_BASE_AXIS},
        yaxis={**_BASE_AXIS, "tickprefix": "$"},
    )
    return fig


def signal_confidence_chart(signals: list[dict]) -> go.Figure:
    """Horizontal bar chart of signal confidence per symbol.

    Bars are coloured **blue** for ``up`` direction and **red** for
    ``down`` direction.

    Args:
        signals: List of signal dicts with ``symbol``, ``confidence``,
            and ``direction`` keys.

    Returns:
        A Plotly horizontal bar figure.
    """
    df = pd.DataFrame(signals)
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_THEME_LAYOUT, title="Signal Confidence (no data)")
        return fig

    colours = [_BLUE if d == "up" else _RED for d in df["direction"]]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["confidence"],
            y=df["symbol"],
            orientation="h",
            marker_color=colours,
            name="Confidence",
        )
    )
    fig.update_layout(
        **_THEME_LAYOUT,
        title="Signal Confidence by Symbol",
        xaxis={**_BASE_AXIS, "tickformat": ".0%"},
        yaxis={**_BASE_AXIS},
    )
    return fig


def sentiment_gauge_chart(sentiment_score: float, symbol: str) -> go.Figure:
    """Gauge chart showing FinBERT sentiment score on a -1 to +1 scale.

    The gauge background is red in the negative zone and green in the
    positive zone. A needle points at the current score.

    Args:
        sentiment_score: Composite sentiment score in range ``[-1, 1]``.
        symbol: Trading pair label for the chart title.

    Returns:
        A Plotly gauge indicator figure.
    """
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=sentiment_score,
            number={"suffix": "", "font": {"color": _WHITE, "size": 24}},
            title={
                "text": f"Sentiment — {symbol}",
                "font": {"color": _WHITE, "size": 14},
            },
            gauge={
                "axis": {
                    "range": [-1, 1],
                    "tickwidth": 1,
                    "tickcolor": _WHITE,
                    "tickfont": {"color": _WHITE},
                },
                "bar": {"color": _WHITE, "thickness": 0.3},
                "bgcolor": _DARK_BG,
                "borderwidth": 0,
                "steps": [
                    {"range": [-1, 0], "color": "rgba(231, 76, 60, 0.4)"},
                    {"range": [0, 1], "color": "rgba(46, 204, 113, 0.4)"},
                ],
                "threshold": {
                    "line": {"color": _WHITE, "width": 3},
                    "thickness": 0.6,
                    "value": sentiment_score,
                },
            },
        )
    )
    layout = {**_THEME_LAYOUT, "height": 250, "margin": {"l": 40, "r": 40, "t": 50, "b": 20}}
    fig.update_layout(**layout)
    return fig


def asset_allocation_pie(positions: list[dict]) -> go.Figure:
    """Donut pie chart of current portfolio allocation by asset.

    Includes a ``Cash`` slice calculated as the difference between
    total portfolio value and the sum of all position values.

    Args:
        positions: List of position dicts, each with ``symbol`` and
            ``value`` keys.

    Returns:
        A Plotly donut pie figure.
    """
    if not positions:
        fig = go.Figure()
        fig.update_layout(**_THEME_LAYOUT, title="Asset Allocation (no positions)")
        return fig

    labels = [p.get("symbol", "Unknown") for p in positions]
    values = [float(p.get("value", 0)) for p in positions]

    total_value = sum(values)
    cash = max(0, total_value * 0.1)

    if cash > 0:
        labels.append("Cash")
        values.append(cash)

    colours_palette = px.colors.qualitative.Set2[: len(labels)]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker={"colors": colours_palette, "line": {"color": _DARK_BG, "width": 2}},
            textfont={"color": _WHITE},
            hovertemplate="%{label}<br>%{value:$,.2f}<extra></extra>",
        )
    )
    layout = {**_THEME_LAYOUT, "title": "Asset Allocation", "showlegend": True}
    fig.update_layout(**layout)
    return fig
