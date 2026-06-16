"""Builder state management — session_state getters/setters for the Strategy Builder.

All state lives in st.session_state under the ``builder_`` prefix.
Exported functions are the ONLY way to mutate builder state.
"""

import json
from typing import Any, Optional


# ── Indicator definitions ──────────────────────────────────────────────
# Each entry: (display_name, key, [param_specs...])
# param_spec: (name, label, type, default, [min, max, step])

INDICATOR_DEFS: list[dict[str, Any]] = [
    {"name": "SMA",  "label": "SMA (Simple Moving Average)",  "params": [
        {"key": "period", "label": "Period", "type": "int", "default": 20, "min": 2, "max": 200},
        {"key": "source", "label": "Source", "type": "select", "default": "close",
         "options": ["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"]},
    ]},
    {"name": "EMA",  "label": "EMA (Exponential Moving Average)",  "params": [
        {"key": "period", "label": "Period", "type": "int", "default": 20, "min": 2, "max": 200},
        {"key": "source", "label": "Source", "type": "select", "default": "close",
         "options": ["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"]},
    ]},
    {"name": "RSI",  "label": "RSI (Relative Strength Index)",  "params": [
        {"key": "period", "label": "Period", "type": "int", "default": 14, "min": 2, "max": 100},
        {"key": "source", "label": "Source", "type": "select", "default": "close",
         "options": ["close", "open", "high", "low"]},
    ]},
    {"name": "MACD",  "label": "MACD",  "params": [
        {"key": "fast",   "label": "Fast period",   "type": "int", "default": 12,  "min": 2,  "max": 100},
        {"key": "slow",   "label": "Slow period",   "type": "int", "default": 26,  "min": 2,  "max": 200},
        {"key": "signal", "label": "Signal period", "type": "int", "default": 9,   "min": 2,  "max": 50},
        {"key": "source", "label": "Source", "type": "select", "default": "close",
         "options": ["close", "open", "high", "low"]},
    ]},
    {"name": "BollingerBands",  "label": "Bollinger Bands",  "params": [
        {"key": "period", "label": "Period", "type": "int",   "default": 20, "min": 2, "max": 200},
        {"key": "std",    "label": "Std Dev", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1},
        {"key": "source", "label": "Source", "type": "select", "default": "close",
         "options": ["close", "open", "high", "low"]},
    ]},
    {"name": "ATR",  "label": "ATR (Average True Range)",  "params": [
        {"key": "period", "label": "Period", "type": "int", "default": 14, "min": 2, "max": 100},
    ]},
    {"name": "Volume",  "label": "Volume",  "params": []},
    {"name": "Ichimoku",  "label": "Ichimoku Cloud",  "params": [
        {"key": "tenkan", "label": "Tenkan period", "type": "int", "default": 9,  "min": 2, "max": 100},
        {"key": "kijun",  "label": "Kijun period",  "type": "int", "default": 26, "min": 2, "max": 200},
        {"key": "senkou", "label": "Senkou period", "type": "int", "default": 52, "min": 2, "max": 200},
    ]},
    {"name": "SuperTrend",  "label": "SuperTrend",  "params": [
        {"key": "period",     "label": "Period",     "type": "int",   "default": 10, "min": 2, "max": 100},
        {"key": "multiplier", "label": "Multiplier", "type": "float", "default": 3.0, "min": 0.5, "max": 10.0, "step": 0.1},
    ]},
    {"name": "VWAP",  "label": "VWAP",  "params": [
        {"key": "anchor", "label": "Anchor", "type": "select", "default": "D", "options": ["D", "W", "M"]},
    ]},
    {"name": "ZScore",  "label": "Z-Score",  "params": [
        {"key": "period",          "label": "Period",          "type": "int",   "default": 21,  "min": 2,   "max": 200},
        {"key": "entry_threshold", "label": "Entry threshold",  "type": "float", "default": 2.0, "min": 0.1, "max": 5.0, "step": 0.1},
        {"key": "exit_threshold",  "label": "Exit threshold",   "type": "float", "default": 0.5, "min": 0.1, "max": 5.0, "step": 0.1},
    ]},
    {"name": "ADX",  "label": "ADX (Average Directional Index)",  "params": [
        {"key": "period", "label": "Period", "type": "int", "default": 14, "min": 2, "max": 100},
    ]},
    {"name": "OBV",  "label": "OBV (On-Balance Volume)",  "params": []},
    {"name": "Stochastic",  "label": "Stochastic Oscillator",  "params": [
        {"key": "k_period", "label": "K period",  "type": "int", "default": 14, "min": 2,  "max": 100},
        {"key": "d_period", "label": "D period",  "type": "int", "default": 3,  "min": 2,  "max": 50},
        {"key": "slowing",  "label": "Slowing",   "type": "int", "default": 3,  "min": 1,  "max": 20},
    ]},
    {"name": "ParabolicSAR",  "label": "Parabolic SAR",  "params": [
        {"key": "af",     "label": "Acceleration factor", "type": "float", "default": 0.02, "min": 0.001, "max": 0.5, "step": 0.001},
        {"key": "max_af", "label": "Max AF",              "type": "float", "default": 0.2,  "min": 0.01,  "max": 1.0, "step": 0.01},
    ]},
    {"name": "SmartMoneyFlowCloud",  "label": "Smart Money Flow Cloud",  "params": [
        {"key": "trend_length",    "label": "Trend length",     "type": "int",   "default": 34,  "min": 5,   "max": 200},
        {"key": "trend_engine",    "label": "Trend engine",     "type": "select", "default": "EMA", "options": ["EMA", "ALMA"]},
        {"key": "flow_window",     "label": "Flow window",      "type": "int",   "default": 24,  "min": 5,   "max": 100},
        {"key": "flow_power",      "label": "Flow power",       "type": "float", "default": 1.2, "min": 0.1, "max": 5.0, "step": 0.1},
        {"key": "atr_length",      "label": "ATR length",       "type": "int",   "default": 14,  "min": 2,   "max": 100},
        {"key": "min_mult",        "label": "Min multiplier",   "type": "float", "default": 0.9, "min": 0.1, "max": 5.0, "step": 0.1},
        {"key": "max_mult",        "label": "Max multiplier",   "type": "float", "default": 2.2, "min": 0.1, "max": 10.0, "step": 0.1},
    ]},
]

INDICATOR_MAP: dict[str, dict] = {d["name"]: d for d in INDICATOR_DEFS}

OPERATOR_GROUPS: list[dict[str, Any]] = [
    {"group": "Comparison", "operators": [
        {"key": "gt",  "label": ">"},  {"key": "gte", "label": ">="},
        {"key": "lt",  "label": "<"},  {"key": "lte", "label": "<="},
        {"key": "eq",  "label": "=="}, {"key": "neq", "label": "!="},
    ]},
    {"group": "Crossover", "operators": [
        {"key": "crosses_above", "label": "Crosses Above"},
        {"key": "crosses_below", "label": "Crosses Below"},
    ]},
    {"group": "Overbought / Oversold", "operators": [
        {"key": "is_overbought",   "label": "Overbought (>70)"},
        {"key": "is_oversold",     "label": "Oversold (<30)"},
        {"key": "exits_overbought", "label": "Exits Overbought"},
        {"key": "exits_oversold",  "label": "Exits Oversold"},
    ]},
    {"group": "Trend Strength", "operators": [
        {"key": "trend_strong", "label": "Strong Trend (ADX>25)"},
        {"key": "trend_weak",   "label": "Weak Trend (ADX<20)"},
    ]},
    {"group": "Bollinger / Band", "operators": [
        {"key": "inside_band",       "label": "Inside Band"},
        {"key": "breaks_above_band", "label": "Breaks Above Band"},
        {"key": "breaks_below_band",  "label": "Breaks Below Band"},
    ]},
    {"group": "Ichimoku", "operators": [
        {"key": "price_above_cloud", "label": "Price Above Cloud"},
        {"key": "price_below_cloud", "label": "Price Below Cloud"},
        {"key": "price_in_cloud",    "label": "Price In Cloud"},
        {"key": "tenkan_crosses_kijun", "label": "Tenkan x Kijun"},
        {"key": "price_crosses_chikou", "label": "Price x Chikou"},
    ]},
    {"group": "Smart Money Flow", "operators": [
        {"key": "smf_above_basis",   "label": "Price Above Basis"},
        {"key": "smf_below_basis",   "label": "Price Below Basis"},
        {"key": "smf_regime_bull",   "label": "Bull Regime"},
        {"key": "smf_regime_bear",   "label": "Bear Regime"},
        {"key": "smf_retest_bull",   "label": "Bull Retest"},
        {"key": "smf_retest_bear",   "label": "Bear Retest"},
    ]},
]

# Operators that need an explicit numeric value
NEEDS_VALUE = {"gt", "gte", "lt", "lte", "eq", "neq", "crosses_above", "crosses_below"}

# ── Session state keys ──────────────────────────────────────────────────

DEFAULT_STATE: dict[str, Any] = {
    "builder_indicators": [],
    "builder_entry_conditions": [],
    "builder_exit_conditions": [],
    "builder_entry_logic": "AND",
    "builder_exit_logic": "OR",
    "builder_config": {},
    "builder_name": "",
    "builder_symbol": "SPY",
    "builder_timeframe": "1D",
    "builder_json_str": "{}",
    "builder_saved": False,
    "builder_deployed": False,
}

_INDICATOR_COUNTER = [0]


def _next_id() -> str:
    _INDICATOR_COUNTER[0] += 1
    return f"ind_{_INDICATOR_COUNTER[0]}"


# ── Public API (to be called inside Streamlit pages) ────────────────────


def init_builder_state() -> None:
    """Initialize all builder session state keys if missing."""
    import streamlit as st
    for key, default in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = default


def add_indicator(indicator_type: str, params: dict, source: str = "close") -> None:
    """Add an indicator to the builder list."""
    import streamlit as st
    entry = {
        "id": _next_id(),
        "type": indicator_type,
        "params": params,
        "source": source,
    }
    st.session_state.builder_indicators.append(entry)


def remove_indicator(indicator_id: str) -> None:
    """Remove an indicator by its ID."""
    import streamlit as st
    st.session_state.builder_indicators = [
        i for i in st.session_state.builder_indicators
        if i["id"] != indicator_id
    ]


def add_entry_condition(condition_dict: dict) -> None:
    """Add an entry condition."""
    import streamlit as st
    st.session_state.builder_entry_conditions.append(condition_dict)


def remove_entry_condition(index: int) -> None:
    """Remove entry condition by list index."""
    import streamlit as st
    if 0 <= index < len(st.session_state.builder_entry_conditions):
        st.session_state.builder_entry_conditions.pop(index)


def add_exit_condition(condition_dict: dict) -> None:
    """Add an exit condition."""
    import streamlit as st
    st.session_state.builder_exit_conditions.append(condition_dict)


def remove_exit_condition(index: int) -> None:
    """Remove exit condition by list index."""
    import streamlit as st
    if 0 <= index < len(st.session_state.builder_exit_conditions):
        st.session_state.builder_exit_conditions.pop(index)


def build_config() -> dict:
    """Build the full strategy config dict from session state.

    Returns the config dict and updates ``st.session_state.builder_config``.
    """
    import streamlit as st

    from royaltdn.strategy.schema import VALID_TIMEFRAMES

    s = st.session_state
    name = s.get("builder_name", "").strip()
    symbol = s.get("builder_symbol", "SPY")
    timeframe = s.get("builder_timeframe", "1D")
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1D"

    # Indicators list
    indicators_list: list[dict] = []
    for ind in s.get("builder_indicators", []):
        entry: dict = {"name": ind["type"], "params": dict(ind["params"]), "source": ind.get("source", "close")}
        indicators_list.append(entry)

    # Entry rules
    entry_conds = s.get("builder_entry_conditions", [])
    entry_logic = s.get("builder_entry_logic", "AND")
    entry_rules = _build_tree(entry_logic, entry_conds)

    # Exit rules
    exit_conds = s.get("builder_exit_conditions", [])
    exit_logic = s.get("builder_exit_logic", "OR")
    exit_rules = _build_tree(exit_logic, exit_conds)

    config = {
        "version": 1,
        "name": name or "unnamed_strategy",
        "description": f"{'Custom' if name else 'Unnamed'} strategy built with RoyalTDN Builder",
        "symbols": [symbol],
        "timeframe": timeframe,
        "indicators": indicators_list,
        "entry_rules": entry_rules,
        "exit_rules": exit_rules,
        "risk_management": {
            "stop_loss_pct": s.get("builder_stop_loss", 2.0),
            "take_profit_pct": s.get("builder_take_profit", 5.0),
            "max_position_size": s.get("builder_max_pos", 1.0),
            "max_daily_loss": s.get("builder_max_loss", 0.1),
        },
    }

    st.session_state.builder_config = config
    return config


def update_json_view() -> None:
    """Update builder_json_str with formatted JSON of the current config."""
    import streamlit as st
    build_config()
    st.session_state.builder_json_str = json.dumps(
        st.session_state.builder_config, indent=2, ensure_ascii=False
    )


def reset_builder() -> None:
    """Reset all builder state to defaults."""
    import streamlit as st
    for key, default in DEFAULT_STATE.items():
        st.session_state[key] = default


def load_config_into_state(config: dict) -> None:
    """Populate session state from an existing config dict (for editing)."""
    import streamlit as st
    st.session_state.builder_name = config.get("name", "")
    st.session_state.builder_symbol = (config.get("symbols") or ["SPY"])[0]
    st.session_state.builder_timeframe = config.get("timeframe", "1D")

    # Indicators
    st.session_state.builder_indicators = []
    for ind in config.get("indicators", []):
        st.session_state.builder_indicators.append({
            "id": _next_id(),
            "type": ind["name"],
            "params": dict(ind.get("params", {})),
            "source": ind.get("source", "close"),
        })

    # Rules
    entry_rules = config.get("entry_rules", {})
    st.session_state.builder_entry_logic = entry_rules.get("operator", "AND")
    st.session_state.builder_entry_conditions = _flatten_conditions(entry_rules.get("conditions", []))

    exit_rules = config.get("exit_rules", {})
    st.session_state.builder_exit_logic = exit_rules.get("operator", "OR")
    st.session_state.builder_exit_conditions = _flatten_conditions(exit_rules.get("conditions", []))

    # Risk
    rm = config.get("risk_management", {})
    st.session_state.builder_stop_loss = rm.get("stop_loss_pct", 2.0)
    st.session_state.builder_take_profit = rm.get("take_profit_pct", 5.0)
    st.session_state.builder_max_pos = rm.get("max_position_size", 1.0)
    st.session_state.builder_max_loss = rm.get("max_daily_loss", 0.1)

    # Update JSON view
    st.session_state.builder_config = config
    st.session_state.builder_json_str = json.dumps(config, indent=2, ensure_ascii=False)


# ── Internal helpers ────────────────────────────────────────────────────


def _build_tree(logic: str, conditions: list) -> dict:
    """Build a rule tree dict from a list of condition dicts."""
    leaf_conds = []
    for cond in conditions:
        leaf: dict = {
            "indicator": cond.get("indicator", "RSI"),
            "params": cond.get("params", {}),
            "operator": cond.get("operator", "gt"),
        }
        if cond.get("operator") in NEEDS_VALUE and "value" in cond:
            leaf["value"] = cond["value"]
        leaf_conds.append(leaf)

    return {
        "operator": logic,
        "conditions": leaf_conds,
    }


def _flatten_conditions(conditions: list) -> list[dict]:
    """Flatten a rule tree conditions list to flat condition dicts."""
    result = []
    for c in conditions:
        if "indicator" in c and "operator" in c:
            entry = {
                "indicator": c["indicator"],
                "params": c.get("params", {}),
                "operator": c["operator"],
            }
            if "value" in c:
                entry["value"] = c["value"]
            result.append(entry)
    return result
