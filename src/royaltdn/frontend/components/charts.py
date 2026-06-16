"""
RoyalTDN — Frontend Charts: Plotly chart builders for bot metrics.

Fase 6 — Hito 2: loaders y charts para frontend Streamlit.

All functions return a go.Figure ready for st.plotly_chart().
Never raise exceptions — return empty chart on missing data.
"""

import logging
from collections import Counter
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

logger = logging.getLogger("royaltdn.frontend.charts")

# ── Empty chart layout ──────────────────────────────────────────

EMPTY_CHART_LAYOUT: dict = dict(
    xaxis=dict(visible=False),
    yaxis=dict(visible=False),
    annotations=[dict(
        text="No data available",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=16, color="gray"),
    )],
)


def _empty_figure(title: str = "") -> go.Figure:
    """Return an empty figure with a 'No data available' message."""
    fig = go.Figure()
    layout = {**EMPTY_CHART_LAYOUT}
    if title:
        layout["title"] = title
    fig.update_layout(**layout)
    return fig


# ── Chart builders ──────────────────────────────────────────────

def build_equity_curve(equity_data: dict) -> go.Figure:
    """Plotly line chart from equity.json equity_curve[].

    Args:
        equity_data: dict with 'equity_curve' key containing list of
                     {timestamp: str, equity: float}.

    Returns:
        go.Figure with line chart or empty annotation.
    """
    curve = equity_data.get("equity_curve", [])
    if not curve:
        return _empty_figure(title="Equity Curve")

    try:
        df = pd.DataFrame(curve)
        if df.empty:
            return _empty_figure(title="Equity Curve")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")

        fig = px.line(
            df,
            x="timestamp",
            y="equity",
            title="Equity Curve",
            labels={"equity": "Equity ($)", "timestamp": ""},
        )
        fig.update_traces(line=dict(color="#00cc96", width=2))
        fig.update_layout(
            hovermode="x unified",
            yaxis=dict(tickprefix="$", tickformat=","),
            height=400,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        return fig
    except Exception as e:
        logger.warning("Error building equity curve chart: %s", e)
        return _empty_figure(title="Equity Curve")


def build_drawdown_chart(equity_data: dict) -> go.Figure:
    """Plotly filled area chart of drawdown from equity curve.

    Calculates drawdown as % below running maximum.

    Args:
        equity_data: dict with 'equity_curve' key.

    Returns:
        go.Figure with filled area chart or empty annotation.
    """
    curve = equity_data.get("equity_curve", [])
    if not curve:
        return _empty_figure(title="Drawdown")

    try:
        df = pd.DataFrame(curve)
        if df.empty:
            return _empty_figure(title="Drawdown")
        df["peak"] = df["equity"].cummax()
        df["drawdown_pct"] = ((df["equity"] - df["peak"]) / df["peak"]) * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(df["timestamp"], utc=True, format="mixed"),
            y=df["drawdown_pct"],
            fill="tozeroy",
            line=dict(color="#ef553b", width=1),
            name="Drawdown",
            hovertemplate="%{y:.2f}%<extra></extra>",
        ))
        fig.update_layout(
            title="Drawdown",
            yaxis=dict(ticksuffix="%"),
            height=250,
            hovermode="x unified",
            margin=dict(l=0, r=0, t=40, b=0),
        )
        return fig
    except Exception as e:
        logger.warning("Error building drawdown chart: %s", e)
        return _empty_figure(title="Drawdown")


def build_pnl_distribution(trades_data: dict) -> go.Figure:
    """Histogram of trade P&L distribution.

    Args:
        trades_data: dict with 'trades' key containing list of trade dicts
                     with 'pnl' field.

    Returns:
        go.Figure with histogram or empty annotation.
    """
    trades = trades_data.get("trades", []) if isinstance(trades_data, dict) else []
    if not trades:
        return _empty_figure(title="Return Distribution")

    try:
        df = pd.DataFrame(trades)
        if df.empty or "pnl" not in df.columns:
            return _empty_figure(title="Return Distribution")

        fig = px.histogram(
            df,
            x="pnl",
            title="Return Distribution",
            labels={"pnl": "P&L ($)"},
            nbins=20,
            color_discrete_sequence=["#636efa"],
        )
        fig.update_layout(
            height=250,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        fig.add_vline(x=0, line_dash="dash", line_color="red")
        return fig
    except Exception as e:
        logger.warning("Error building P&L distribution chart: %s", e)
        return _empty_figure(title="Return Distribution")


def build_scanner_distribution(scanner_data: dict) -> go.Figure:
    """Bar chart of signal count per strategy.

    Args:
        scanner_data: dict with 'top_signals' key containing list of signal
                     dicts with 'strategy' field. Also supports the
                     'last_scan' → 'top_signals' nested shape.

    Returns:
        go.Figure with bar chart or empty annotation.
    """
    # Support both flat and nested shapes
    if isinstance(scanner_data, dict):
        signals = scanner_data.get("top_signals", [])
        if not signals:
            signals = scanner_data.get("last_scan", {}).get("top_signals", [])
    else:
        signals = []

    if not signals:
        return _empty_figure(title="Signals by Strategy")

    try:
        counts = Counter(s.get("strategy", "unknown") for s in signals)
        df = pd.DataFrame(counts.most_common(), columns=["Strategy", "Count"])

        fig = px.bar(
            df,
            x="Strategy",
            y="Count",
            title="Signals by Strategy",
            color="Strategy",
            color_discrete_sequence=px.colors.qualitative.Vivid,
        )
        fig.update_layout(
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            showlegend=False,
        )
        return fig
    except Exception as e:
        logger.warning("Error building scanner distribution chart: %s", e)
        return _empty_figure(title="Signals by Strategy")


def build_pnl_by_trade(trades_data: dict) -> go.Figure:
    """Bar chart of P&L per trade, green for winning, red for losing.

    Args:
        trades_data: dict with 'trades' key containing list of trade dicts
                     with 'pnl', 'symbol', and 'side' fields.

    Returns:
        go.Figure with bar chart or empty annotation.
    """
    trades = trades_data.get("trades", []) if isinstance(trades_data, dict) else []
    if not trades:
        return _empty_figure(title="P&L per Trade")

    try:
        df = pd.DataFrame(trades)
        if df.empty or "pnl" not in df.columns:
            return _empty_figure(title="P&L per Trade")

        df["color"] = df["pnl"].apply(lambda x: "#00cc96" if x >= 0 else "#ef553b")
        df["label"] = df.apply(
            lambda r: f"{r.get('symbol', '?')} {r.get('side', '?')}",
            axis=1,
        )

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=list(range(len(df))),
            y=df["pnl"],
            marker_color=df["color"],
            text=df["label"],
            hovertemplate="%{text}<br>P&L: $%{y:,.2f}<extra></extra>",
        ))
        fig.update_layout(
            title="P&L per Trade",
            yaxis=dict(tickprefix="$", tickformat=","),
            xaxis=dict(visible=False),
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            showlegend=False,
        )
        return fig
    except Exception as e:
        logger.warning("Error building P&L by trade chart: %s", e)
        return _empty_figure(title="P&L per Trade")
