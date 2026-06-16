"""
RoyalTDN — Estrategias Page.

Fase 6 — Hito 4: Listado de estrategias cargadas con expanders,
parámetros, estado de validación y conteo de señales.
Auto-refresh cada 5 segundos.
"""

import time

import pandas as pd
import streamlit as st

from royaltdn.frontend.components.loaders import load_strategies

# ── Page ─────────────────────────────────────────────────────────

st.title("⚙️ Estrategias")

strategies_data = load_strategies()
strategies = strategies_data.get("strategies", [])

if not strategies:
    st.info("No strategies loaded")
    time.sleep(5)
    st.rerun()

for s in strategies:
    name = s.get("name", "?")
    active = s.get("active", True)
    icon = "✅" if active else "⏸️"
    
    with st.expander(f"{icon} {name}", expanded=True):
        cols = st.columns([1, 1, 1])
        
        with cols[0]:
            st.checkbox("Active", value=active, key=f"active_{name}", disabled=True)
            st.caption(f"Symbol: {s.get('symbol', '—')}")
            st.caption(f"Timeframe: {s.get('timeframe', '—')}")
        
        with cols[1]:
            last_sig = s.get("last_signal")
            if last_sig:
                st.caption("Last signal")
                st.code(str(last_sig), line_numbers=False)
            else:
                st.caption("Last signal: —")
            st.caption(f"Signal count: {s.get('signal_count', 0)}")
        
        with cols[2]:
            valid = s.get("validation", False)
            st.metric("Validation", "✅" if valid else "❌")
        
        # Parameters table
        params = s.get("params", {})
        if params:
            st.subheader("Parameters")
            params_df = pd.DataFrame([
                {"Parameter": k, "Value": v}
                for k, v in params.items()
            ])
            st.dataframe(params_df, hide_index=True, width='stretch')

# ── Auto-refresh ─────────────────────────────────────────────────

time.sleep(5)
st.rerun()
