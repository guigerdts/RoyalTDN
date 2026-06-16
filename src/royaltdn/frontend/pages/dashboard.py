"""
RoyalTDN — Dashboard Page.

Fase 6 — Hito 3: Página principal con métricas, charts y estado del bot.
Auto-refresh cada 3 segundos.
"""

import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import streamlit as st

from royaltdn.frontend.components.loaders import (
    is_stale,
    load_equity,
    load_positions,
    load_signals,
    load_status,
)
from royaltdn.frontend.components.charts import (
    build_drawdown_chart,
    build_equity_curve,
)

# ── Page config ──────────────────────────────────────────────────

st.title("📊 Dashboard")

# ── Load data ────────────────────────────────────────────────────

equity = load_equity()
positions = load_positions()
signals = load_signals()
status = load_status()

# ── Metric cards ─────────────────────────────────────────────────

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    capital = equity.get("current_equity")
    if capital is not None:
        st.metric("Capital", f"${capital:,.2f}")
    else:
        st.metric("Capital", "—")

with col2:
    pnl = equity.get("pnl_day")
    if pnl is not None:
        delta_color = "normal" if pnl >= 0 else "inverse"
        st.metric("P&L Day ($)", f"${pnl:+,.2f}", delta_color=delta_color)
    else:
        st.metric("P&L Day ($)", "—")

with col3:
    dd = equity.get("drawdown_pct")
    if dd is not None:
        st.metric("Drawdown", f"{dd:.2f}%")
    else:
        st.metric("Drawdown", "—")

with col4:
    open_pos = positions.get("total_open", 0)
    st.metric("Open Positions", open_pos)

with col5:
    sig_count = signals.get("today_count", 0)
    st.metric("Signals Today", sig_count)

with col6:
    sharpe = equity.get("sharpe")
    if sharpe is not None:
        st.metric("Sharpe", f"{sharpe:.2f}")
    else:
        st.metric("Sharpe", "—")

# ── Charts row ───────────────────────────────────────────────────

col_left, col_right = st.columns(2)

with col_left:
    fig_eq = build_equity_curve(equity)
    st.plotly_chart(fig_eq, width='stretch')

with col_right:
    fig_dd = build_drawdown_chart(equity)
    st.plotly_chart(fig_dd, width='stretch')

# ── Open positions table ─────────────────────────────────────────

st.subheader("Open Positions")
pos_list = positions.get("open_positions", [])

if pos_list:
    df_pos = pd.DataFrame(pos_list)
    
    # Calculate duration from entry_at
    if "entry_at" in df_pos.columns:
        def _calc_duration(entry_at: Optional[str]) -> str:
            if not entry_at:
                return "—"
            try:
                ts = datetime.fromisoformat(entry_at.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - ts
                total_secs = int(delta.total_seconds())
                hours, remainder = divmod(total_secs, 3600)
                minutes, _ = divmod(remainder, 60)
                return f"{hours}h {minutes}m"
            except (ValueError, TypeError):
                return "—"
        
        df_pos["duration"] = df_pos["entry_at"].apply(_calc_duration)
    
    # Colour P&L column
    if "pnl_unrealized" in df_pos.columns:
        def _color_pnl(val: float) -> str:
            if val > 0:
                return "color: #00cc96"
            elif val < 0:
                return "color: #ef553b"
            return ""
        
        styled = df_pos.style.map(_color_pnl, subset=["pnl_unrealized"])
        st.dataframe(styled, width='stretch', hide_index=True)
    else:
        st.dataframe(df_pos, width='stretch', hide_index=True)
else:
    st.info("No open positions")

# ── Bot status ───────────────────────────────────────────────────

st.subheader("Bot Status")

if not status:
    st.warning("⏳ Waiting for bot to start...")
else:
    stale_flag = is_stale(status.get("timestamp", ""), max_age_seconds=300)
    bot_status = status.get("bot_status", "OFFLINE")
    
    if stale_flag:
        st.warning("⚠️ STALE — Bot data is older than 5 minutes")
    elif bot_status == "ONLINE":
        st.success("● ONLINE")
    elif bot_status == "KILLED":
        st.error("● KILLED")
    else:
        st.error("● OFFLINE")
    
    # Status details
    details_col1, details_col2 = st.columns(2)
    with details_col1:
        st.caption(f"Mode: {status.get('mode', 'unknown')}")
        st.caption(f"Uptime: {status.get('uptime_seconds', 0)}s")
    with details_col2:
        st.caption(f"Symbols: {', '.join(status.get('symbols', []))}")
        st.caption(f"Scanner: {'✅ Enabled' if status.get('scanner_enabled') else '❌ Disabled'}")
    
    last_signal = status.get("last_signal")
    if last_signal:
        st.caption(
            f"Last signal: {last_signal.get('action', '?')} @ "
            f"{last_signal.get('symbol', '?')} — "
            f"${last_signal.get('price', 0):,.2f}"
        )
    
    last_error = status.get("last_error")
    if last_error:
        st.error(f"Last error: {last_error}")

# ── Auto-refresh ─────────────────────────────────────────────────

time.sleep(3)
st.rerun()
