"""Schema validator for Dynamic Strategy JSON configs (v1).

Validates structure, types, ranges, and enum membership.
"""

import re
from datetime import datetime

# ── Constants ──────────────────────────────────────────────────────────

VALID_INDICATORS = {
    "SMA", "EMA", "RSI", "MACD", "BollingerBands", "ATR", "Volume",
    "Ichimoku", "SuperTrend", "VWAP", "ZScore", "ADX", "OBV",
    "Stochastic", "ParabolicSAR", "SmartMoneyFlowCloud",
}

VALID_SOURCES = {"open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"}

VALID_TIMEFRAMES = {"1min", "5min", "15min", "30min", "1H", "4H", "1D"}

VALID_COMPARISON_OPERATORS = {
    "gt", "gte", "lt", "lte", "eq", "neq",
}

VALID_SPECIAL_OPERATORS = {
    "crosses_above", "crosses_below",
    "inside_band", "breaks_above_band", "breaks_below_band",
    "is_overbought", "is_oversold", "exits_overbought", "exits_oversold",
    "price_above_cloud", "price_below_cloud", "price_in_cloud",
    "trend_strong", "trend_weak",
    "tenkan_crosses_kijun", "price_crosses_chikou",
    "smf_above_basis", "smf_below_basis",
    "smf_regime_bull", "smf_regime_bear",
    "smf_retest_bull", "smf_retest_bear",
}

ALL_OPERATORS = VALID_COMPARISON_OPERATORS | VALID_SPECIAL_OPERATORS

ISO_DT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,10}$")

# ── Public API ─────────────────────────────────────────────────────────


def validate_config(config: dict) -> tuple:
    """Validate a strategy JSON config against schema v1.

    Returns:
        (is_valid: bool, error_message: str)
    """
    if not isinstance(config, dict):
        return False, "Config must be a dict"

    # version
    if config.get("version") != 1:
        return False, "version must be 1 (int)"

    # name
    name = config.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= 64):
        return False, "name must be a string of 1-64 characters"

    # description (optional)
    description = config.get("description", "")
    if description and (not isinstance(description, str) or len(description) > 256):
        return False, "description must be a string of max 256 characters"

    # timestamps (optional but must be valid ISO 8601 if present)
    for field in ("created_at", "updated_at"):
        value = config.get(field)
        if value is not None and not ISO_DT_RE.match(str(value)):
            return False, f"{field} must be a valid ISO 8601 datetime string"

    # symbols
    symbols = config.get("symbols")
    if not isinstance(symbols, list) or len(symbols) < 1:
        return False, "symbols must be a non-empty list"
    for sym in symbols:
        if not isinstance(sym, str) or not SYMBOL_RE.match(sym):
            return False, f"Invalid symbol: {sym!r}"

    # timeframe
    tf = config.get("timeframe")
    if tf not in VALID_TIMEFRAMES:
        return False, f"timeframe must be one of {sorted(VALID_TIMEFRAMES)}, got {tf!r}"

    # indicators
    indicators = config.get("indicators", [])
    if not isinstance(indicators, list) or len(indicators) < 1:
        return False, "indicators must be a non-empty list"
    for idx, ind in enumerate(indicators):
        ok, err = _validate_indicator(ind)
        if not ok:
            return False, f"indicators[{idx}]: {err}"

    # entry_rules
    entry = config.get("entry_rules")
    if not isinstance(entry, dict):
        return False, "entry_rules must be a dict (rule tree)"
    ok, err = _validate_rule_tree(entry, depth=0)
    if not ok:
        return False, f"entry_rules: {err}"

    # exit_rules
    exit_ = config.get("exit_rules")
    if not isinstance(exit_, dict):
        return False, "exit_rules must be a dict (rule tree)"
    ok, err = _validate_rule_tree(exit_, depth=0)
    if not ok:
        return False, f"exit_rules: {err}"

    # risk_management
    rm = config.get("risk_management")
    if not isinstance(rm, dict):
        return False, "risk_management must be a dict"

    for key, lo, hi in (
        ("stop_loss_pct", 0, 100),
        ("take_profit_pct", 0, 100),
        ("max_position_size", 0, None),
        ("max_daily_loss", 0, None),
    ):
        val = rm.get(key)
        if not isinstance(val, (int, float)) or val < 0:
            return False, f"risk_management.{key} must be a positive number"
        if hi is not None and val > hi:
            return False, f"risk_management.{key} must be <= {hi}"

    return True, ""


# ── Internal helpers ───────────────────────────────────────────────────


def _validate_indicator(ind: dict) -> tuple:
    if not isinstance(ind, dict):
        return False, "must be a dict"

    name = ind.get("name")
    if name not in VALID_INDICATORS:
        return False, f"unknown indicator {name!r}; valid: {sorted(VALID_INDICATORS)}"

    params = ind.get("params", {})
    if not isinstance(params, dict):
        return False, "params must be a dict"

    source = ind.get("source", "close")
    if source not in VALID_SOURCES:
        return False, f"source must be one of {sorted(VALID_SOURCES)}, got {source!r}"

    return True, ""


def _validate_rule_tree(node: dict, depth: int) -> tuple:
    if depth > 2:
        return False, f"Max depth 2 exceeded at depth {depth}"

    operator = node.get("operator")
    if operator not in ("AND", "OR"):
        return False, f"operator must be AND or OR, got {operator!r}"

    conditions = node.get("conditions")
    if not isinstance(conditions, list) or len(conditions) == 0:
        return False, "conditions must be a non-empty list"

    for idx, cond in enumerate(conditions):
        # Nested group?
        if isinstance(cond, dict) and "operator" in cond and "conditions" in cond:
            ok, err = _validate_rule_tree(cond, depth=depth + 1)
            if not ok:
                return False, f"conditions[{idx}]: {err}"
        else:
            # Leaf
            ok, err = _validate_leaf(cond)
            if not ok:
                return False, f"conditions[{idx}]: {err}"

    return True, ""


def _validate_leaf(leaf: dict) -> tuple:
    if not isinstance(leaf, dict):
        return False, "must be a dict"

    if "indicator" not in leaf:
        return False, "missing 'indicator'"
    if leaf["indicator"] not in VALID_INDICATORS:
        return False, f"unknown indicator {leaf['indicator']!r}"

    operator = leaf.get("operator")
    if operator not in ALL_OPERATORS:
        return False, f"unknown operator {operator!r}"

    # Co-validate value presence
    if operator in VALID_COMPARISON_OPERATORS | {"crosses_above", "crosses_below"}:
        if "value" not in leaf:
            return False, f"operator {operator} requires a 'value' field"
        val = leaf["value"]
        if not isinstance(val, (int, float)):
            return False, f"operator {operator} value must be a number"

    return True, ""
