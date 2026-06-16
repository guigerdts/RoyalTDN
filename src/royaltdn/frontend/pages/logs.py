"""
RoyalTDN — Logs Page.

Fase 6 — Hito 4: Visor de logs en vivo con filtros por nivel,
módulo y texto. Auto-refresh cada 2 segundos.
"""

import time
from pathlib import Path

import streamlit as st

from royaltdn.frontend.components.loaders import read_log_tail

# ── Page ─────────────────────────────────────────────────────────

st.title("📋 Logs")

# ── Filters ──────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    show_debug = st.checkbox("DEBUG", value=False)
    show_info = st.checkbox("INFO", value=True)
with col2:
    show_warning = st.checkbox("WARNING", value=True)
    show_error = st.checkbox("ERROR", value=True)
with col3:
    module_filter = st.text_input("Module filter", placeholder="e.g. scanner")
with col4:
    search_text = st.text_input("Search", placeholder="text to find")
    if st.button("Clear view"):
        st.session_state["log_lines"] = []
        st.rerun()

# ── Initialise session state ─────────────────────────────────────

if "log_lines" not in st.session_state:
    st.session_state["log_lines"] = []

# ── Build level filter string ────────────────────────────────────

# We use the level parameter from read_log_tail for the first pass,
# then filter further client-side for multi-level support.
selected_levels = []
if show_debug:
    selected_levels.append("DEBUG")
if show_info:
    selected_levels.append("INFO")
if show_warning:
    selected_levels.append("WARNING")
if show_error:
    selected_levels.append("ERROR")

# ── Read log file ───────────────────────────────────────────────

raw_lines = read_log_tail(
    filepath=Path("logs/bot.log"),
    lines=200,
    module_filter=module_filter if module_filter else None,
    search_text=search_text if search_text else None,
)

if not raw_lines:
    st.info("Log file not found at logs/bot.log")
    time.sleep(2)
    st.rerun()

# ── Apply level filters (client-side) ────────────────────────────

if selected_levels and selected_levels != ["DEBUG", "INFO", "WARNING", "ERROR"]:
    filtered = [
        line for line in raw_lines
        if any(f" - {lvl} - " in line for lvl in selected_levels)
    ]
else:
    filtered = list(raw_lines)

# ── Display ──────────────────────────────────────────────────────

st.session_state["log_lines"] = filtered[-200:]
display_text = "".join(st.session_state["log_lines"])
st.code(display_text, language="log", line_numbers=True)

# ── Auto-refresh ─────────────────────────────────────────────────

time.sleep(2)
st.rerun()
