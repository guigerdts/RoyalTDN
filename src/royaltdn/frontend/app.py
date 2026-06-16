"""
RoyalTDN — Streamlit Frontend Entry Point.

Fase 6 — Frontend Streamlit.
Uses st.navigation for multipage support.
"""

import streamlit as st

st.set_page_config(
    page_title="RoyalTDN",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

dashboard = st.Page(
    "pages/dashboard.py",
    title="📊 Dashboard",
    icon="📊",
    default=True,
)
scanner = st.Page(
    "pages/scanner.py",
    title="🔍 Scanner",
    icon="🔍",
)
estrategias = st.Page(
    "pages/estrategias.py",
    title="⚙️ Estrategias",
    icon="⚙️",
)
trades = st.Page(
    "pages/trades.py",
    title="📈 Trades",
    icon="📈",
)
logs = st.Page(
    "pages/logs.py",
    title="📋 Logs",
    icon="📋",
)

nav = st.navigation([dashboard, scanner, estrategias, trades, logs])
nav.run()
