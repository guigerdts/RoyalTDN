"""Builder state management — pure data definitions for the Strategy Builder.

This module contains ONLY pure data/logic: indicator definitions, operator
groups, tree builders, and flatten helpers. No Streamlit dependencies.

Extracted from the original ``frontend/components/builder_state.py`` during
the Fase 8 Streamlit removal. All Streamlit-dependent functions were removed.
"""

import json
from typing import Any


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
