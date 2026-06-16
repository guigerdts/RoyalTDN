"""Plotly chart functions for backtesting results.

Each function returns a ``plotly.graph_objects.Figure`` ready to render
with ``st.plotly_chart``.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_equity_curve(
    equity_data: list[float],
    buy_hold_data: list[float],
    dates: list[str],
) -> go.Figure:
    """Strategy equity vs buy & hold."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=equity_data,
        mode="lines", name="Strategy",
        line=dict(color="#00cc96", width=2),
    ))
    if buy_hold_data:
        fig.add_trace(go.Scatter(
            x=dates, y=buy_hold_data,
            mode="lines", name="Buy & Hold",
            line=dict(color="#b0b0b0", width=2, dash="dash"),
        ))
    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        hovermode="x unified",
        height=350,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def plot_drawdown(drawdown_data: list[float], dates: list[str]) -> go.Figure:
    """Drawdown area chart."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=drawdown_data,
        mode="lines", name="Drawdown",
        fill="tozeroy",
        line=dict(color="#ef553b", width=1),
        fillcolor="rgba(239, 85, 59, 0.3)",
    ))
    fig.update_layout(
        title="Drawdown",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        hovermode="x unified",
        height=200,
        margin=dict(l=10, r=10, t=40, b=10),
        yaxis=dict(tickformat=".1%"),
    )
    return fig


def plot_trade_distribution(trades: list[dict]) -> go.Figure:
    """Histogram of trade returns."""
    if not trades:
        fig = go.Figure()
        fig.add_annotation(text="No trades", showarrow=False)
        fig.update_layout(height=200)
        return fig

    pnl_pcts = [t.get("return_pct", 0) for t in trades]
    colors = ["#00cc96" if p >= 0 else "#ef553b" for p in pnl_pcts]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(range(len(pnl_pcts))),
        y=pnl_pcts,
        marker_color=colors,
        name="Trade P&L %",
    ))
    fig.update_layout(
        title="Trade Returns (%)",
        xaxis_title="Trade #",
        yaxis_title="Return %",
        height=200,
        margin=dict(l=10, r=10, t=40, b=10),
        showlegend=False,
    )
    return fig


def plot_monthly_heatmap(daily_returns: list[float], dates: list[str]) -> go.Figure:
    """Monthly return heatmap."""
    if not daily_returns or not dates:
        fig = go.Figure()
        fig.add_annotation(text="No return data", showarrow=False)
        fig.update_layout(height=300)
        return fig

    df = pd.DataFrame({"return": daily_returns, "date": pd.to_datetime(dates)})
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    monthly = df.groupby(["year", "month"])["return"].sum() * 100
    monthly = monthly.unstack(level="month")

    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig = go.Figure(data=go.Heatmap(
        z=monthly.values,
        x=[month_labels[m - 1] for m in monthly.columns],
        y=monthly.index,
        colorscale="RdYlGn",
        zmid=0,
        text=monthly.map("{:.1f}%".format).values if hasattr(monthly, "map") else None,
        texttemplate="%{text}",
        textfont=dict(size=9),
        hovertemplate="%{y}-%{x}: %{z:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Monthly Returns (%)",
        height=250,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(side="bottom"),
    )
    return fig


def render_metrics_cards(metrics: dict) -> None:
    """Render Streamlit metric cards in a 3x3 grid."""
    import streamlit as st

    if not metrics or "error" in metrics:
        st.warning(metrics.get("error", "No metrics available"))
        return

    row1 = st.columns(3)
    with row1[0]:
        st.metric("Total Return", f"{metrics.get('total_return', 0) * 100:.2f}%")
    with row1[1]:
        st.metric("CAGR", f"{metrics.get('cagr', 0) * 100:.2f}%")
    with row1[2]:
        st.metric("Sharpe", f"{metrics.get('sharpe', 0):.2f}")

    row2 = st.columns(3)
    with row2[0]:
        st.metric("Sortino", f"{metrics.get('sortino', 0):.2f}")
    with row2[1]:
        st.metric("Max DD", f"{metrics.get('max_drawdown', 0) * 100:.2f}%")
    with row2[2]:
        st.metric("Trades", f"{metrics.get('num_trades', 0)}")

    if metrics.get("num_trades", 0) > 0:
        row3 = st.columns(3)
        with row3[0]:
            st.metric("Win Rate", f"{metrics.get('win_rate', 0) * 100:.1f}%")
        with row3[1]:
            st.metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
        with row3[2]:
            st.metric("Avg Trade", f"{metrics.get('avg_trade', 0):.2f}")
