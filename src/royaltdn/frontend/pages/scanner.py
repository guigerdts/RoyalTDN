"""
RoyalTDN — Scanner Page.

Fase 6 — Hito 4: Señales del scanner con tabla coloreada,
gráfico de distribución e historial de escaneos.
Auto-refresh cada 5 segundos.
"""

import time

import pandas as pd
import streamlit as st

from royaltdn.frontend.components.charts import build_scanner_distribution
from royaltdn.frontend.components.loaders import load_scanner_results

# ── Page ─────────────────────────────────────────────────────────

st.title("🔍 Scanner")

scanner_data = load_scanner_results()

if not scanner_data or not scanner_data.get("top_signals"):
    st.info("Scanner not initialized or no scan completed yet")
    time.sleep(5)
    st.rerun()

# ── Config section (visual-only) ─────────────────────────────────

with st.expander("Scanner Configuration", expanded=False):
    col_a, col_b = st.columns(2)
    with col_a:
        st.selectbox("Universe", ["etfs", "sp500", "all"], key="scan_universe")
    with col_b:
        st.number_input("Top N signals", min_value=1, max_value=20, value=5, key="scan_top_n")

# ── Signals table with coloured rows ─────────────────────────────

st.subheader("Top Signals")
signals_df = pd.DataFrame(scanner_data.get("top_signals", []))

if not signals_df.empty:
    def _colour_signal_row(row) -> list[str]:
        action = str(row.get("action", "")).upper()
        if action == "BUY":
            return ["background-color: #d4edda"] * len(row)
        elif action == "SELL":
            return ["background-color: #f8d7da"] * len(row)
        elif action == "RANK":
            return ["background-color: #cce5ff"] * len(row)
        return [""] * len(row)

    st.dataframe(
        signals_df.style.apply(_colour_signal_row, axis=1),
        width='stretch',
        hide_index=True,
    )
else:
    st.info("No signals available")

# ── Distribution chart ───────────────────────────────────────────

st.subheader("Distribution by Strategy")
fig = build_scanner_distribution(scanner_data)
st.plotly_chart(fig, width='stretch')

# ── Scan history ─────────────────────────────────────────────────

st.subheader("Scan History")
history = scanner_data.get("history", [])
if history:
    st.dataframe(pd.DataFrame(history), width='stretch', hide_index=True)
else:
    st.caption("No scan history yet")

# ── Auto-refresh ─────────────────────────────────────────────────

time.sleep(5)
st.rerun()
