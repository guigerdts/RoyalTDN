"""
RoyalTDN — Trades Page.

Fase 6 — Hito 4: Historial completo de trades con filtros,
métricas resumen, gráficos P&L y exportación CSV.
Auto-refresh cada 5 segundos.
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from royaltdn.frontend.components.charts import (
    build_pnl_by_trade,
    build_pnl_distribution,
)
from royaltdn.frontend.components.loaders import load_trades

# ── Page ─────────────────────────────────────────────────────────

st.title("📈 Trades")

trades_data = load_trades()
trades_list = trades_data.get("trades", [])

# ── Filters ──────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    date_from = st.date_input("From", value=datetime.now() - timedelta(days=30))
with col2:
    date_to = st.date_input("To", value=datetime.now())
with col3:
    symbols = sorted(set(t.get("symbol", "") for t in trades_list)) if trades_list else []
    filter_symbol = st.selectbox("Symbol", ["All"] + symbols)
with col4:
    filter_result = st.radio("Result", ["All", "Win", "Loss"], horizontal=True)

# ── Apply filters ────────────────────────────────────────────────

filtered: list[dict] = list(trades_list)

if filter_symbol and filter_symbol != "All":
    filtered = [t for t in filtered if t.get("symbol") == filter_symbol]

if filter_result == "Win":
    filtered = [t for t in filtered if t.get("pnl", 0) > 0]
elif filter_result == "Loss":
    filtered = [t for t in filtered if t.get("pnl", 0) <= 0]

# ── Summary metrics ──────────────────────────────────────────────

if filtered:
    total = len(filtered)
    wins = sum(1 for t in filtered if t.get("pnl", 0) > 0)
    total_pnl = sum(t.get("pnl", 0) for t in filtered)
    win_rate = wins / total * 100 if total > 0 else 0.0
    gross_profit = sum(t["pnl"] for t in filtered if t.get("pnl", 0) > 0)
    gross_loss = abs(sum(t["pnl"] for t in filtered if t.get("pnl", 0) < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_pnl = total_pnl / total if total > 0 else 0.0
    best = max(t.get("pnl", 0) for t in filtered)
    worst = min(t.get("pnl", 0) for t in filtered)

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Total Trades", total)
    m2.metric("Win Rate", f"{win_rate:.1f}%")
    m3.metric("Profit Factor", f"{profit_factor:.2f}")
    m4.metric("Total P&L", f"${total_pnl:+,.2f}")
    m5.metric("Avg P&L", f"${avg_pnl:+,.2f}")
    m6.metric("Best", f"${best:+,.2f}")
    m7.metric("Worst", f"${worst:+,.2f}")

    # ── Trade table ──────────────────────────────────────────────
    df = pd.DataFrame(filtered)
    
    def _colour_pnl_row(row) -> list[str]:
        pnl = row.get("pnl", 0)
        if pnl > 0:
            return ["background-color: #d4edda"] * len(row)
        elif pnl < 0:
            return ["background-color: #f8d7da"] * len(row)
        return [""] * len(row)
    
    st.dataframe(
        df.style.apply(_colour_pnl_row, axis=1),
        width='stretch',
        hide_index=True,
    )

    # ── Charts ───────────────────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        fig_pnl = build_pnl_by_trade({"trades": filtered})
        st.plotly_chart(fig_pnl, width='stretch')
    with col_b:
        fig_hist = build_pnl_distribution({"trades": filtered})
        st.plotly_chart(fig_hist, width='stretch')

    # ── CSV export ───────────────────────────────────────────────
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"trades_export_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
else:
    if not trades_list:
        st.info("No trades executed this session")
    else:
        st.info("No trades match the filters")

# ── Auto-refresh ─────────────────────────────────────────────────

time.sleep(5)
st.rerun()
