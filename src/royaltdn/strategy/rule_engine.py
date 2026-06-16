"""Recursive rule-tree evaluator for the Dynamic Strategy Engine.

Supports:
- Logical operators: AND, OR
- Comparison: gt, gte, lt, lte, eq, neq
- Crossover: crosses_above, crosses_below
- Band: inside_band, breaks_above_band, breaks_below_band
- Overbought/Oversold: is_overbought, is_oversold, exits_overbought, exits_oversold
- Ichimoku cloud: price_above_cloud, price_below_cloud, price_in_cloud
- Trend strength: trend_strong, trend_weak
- Ichimoku lines: tenkan_crosses_kijun, price_crosses_chikou
- SMF: smf_above_basis, smf_below_basis, smf_regime_bull, smf_regime_bear,
        smf_retest_bull, smf_retest_bear
"""

from typing import Any

MAX_DEPTH = 2


def evaluate(tree: dict, indicators: dict, data: "pd.DataFrame") -> bool:
    """Recursively evaluate a rule tree against computed indicators.

    Args:
        tree: Rule tree dict with operator and conditions.
        indicators: Dict of {indicator_name: computed_df/series}.
        data: The full OHLCV DataFrame (for price checks).

    Returns:
        True if the tree evaluates to True, False otherwise.

    Raises:
        ValueError: if tree depth exceeds MAX_DEPTH, or operator is unknown.
    """
    import pandas as pd  # noqa: F811

    return _evaluate(tree, indicators, data, depth=0)


def _evaluate(
    tree: dict, indicators: dict, data: "pd.DataFrame", depth: int,
) -> bool:
    import pandas as pd  # noqa: F811

    if depth > MAX_DEPTH:
        raise ValueError(
            f"Rule tree exceeds max depth {MAX_DEPTH}. "
            f"Got depth {depth}."
        )

    operator = tree.get("operator", "").upper()
    conditions = tree.get("conditions", [])

    if not conditions:
        return False

    if operator == "AND":
        return all(
            _evaluate_condition(c, indicators, data, depth)
            if "conditions" in c and "operator" in c
            else _eval_leaf(c, indicators, data)
            for c in conditions
        )
    elif operator == "OR":
        return any(
            _evaluate_condition(c, indicators, data, depth)
            if "conditions" in c and "operator" in c
            else _eval_leaf(c, indicators, data)
            for c in conditions
        )
    else:
        raise ValueError(f"Unknown rule operator: {operator}")


def _evaluate_condition(
    cond: dict, indicators: dict, data: "pd.DataFrame", depth: int,
) -> bool:
    return _evaluate(cond, indicators, data, depth=depth + 1)


def _eval_leaf(leaf: dict, indicators: dict, data: "pd.DataFrame") -> bool:
    import pandas as pd  # noqa: F811

    indicator_name = leaf.get("indicator", "")
    params = leaf.get("params", {})
    operator = leaf.get("operator", "")
    value = leaf.get("value")

    # Resolve indicator data
    series = _resolve_indicator(indicator_name, params, indicators, data)
    if series is None or series.empty:
        return False

    last = series.iloc[-1] if not isinstance(series, pd.DataFrame) else series.iloc[-1]
    prev = series.iloc[-2] if len(series) >= 2 else last

    # Comparison operators
    if operator == "gt":
        return bool(last > value)
    elif operator == "gte":
        return bool(last >= value)
    elif operator == "lt":
        return bool(last < value)
    elif operator == "lte":
        return bool(last <= value)
    elif operator == "eq":
        return bool(last == value)
    elif operator == "neq":
        return bool(last != value)
    elif operator == "crosses_above":
        return bool(prev <= value and last > value)
    elif operator == "crosses_below":
        return bool(prev >= value and last > value)

    # Band operators — need DataFrame columns
    if isinstance(series, pd.DataFrame):
        cols = series.columns.tolist()
        if operator == "inside_band":
            upper = series.get("BB_upper") or series.get("upper_band")
            lower = series.get("BB_lower") or series.get("lower_band")
            if upper is None or lower is None:
                return False
            return bool(lower.iloc[-1] <= last["close"] <= upper.iloc[-1])
        elif operator == "breaks_above_band":
            upper = series.get("BB_upper") or series.get("upper_band")
            if upper is None:
                return False
            return bool(data["close"].iloc[-2] <= upper.iloc[-2] and data["close"].iloc[-1] > upper.iloc[-1])
        elif operator == "breaks_below_band":
            lower = series.get("BB_lower") or series.get("lower_band")
            if lower is None:
                return False
            return bool(data["close"].iloc[-2] >= lower.iloc[-2] and data["close"].iloc[-1] < lower.iloc[-1])

    # Overbought / Oversold
    if operator == "is_overbought":
        return bool(last > 70)
    elif operator == "is_oversold":
        return bool(last < 30)
    elif operator == "exits_overbought":
        return bool(prev > 70 and last <= 70)
    elif operator == "exits_oversold":
        return bool(prev < 30 and last >= 30)

    # Trend strength
    if operator == "trend_strong":
        return bool(last > 25)
    elif operator == "trend_weak":
        return bool(last < 20)

    # Ichimoku cloud
    close = data["close"]
    if isinstance(series, pd.DataFrame):
        senkou_a = series.get("senkou_a")
        senkou_b = series.get("senkou_b")
        tenkan = series.get("tenkan")
        kijun = series.get("kijun")
        chikou = series.get("chikou")

        if operator == "price_above_cloud":
            if senkou_a is None or senkou_b is None:
                return False
            return bool(close.iloc[-1] > senkou_a.iloc[-1] and close.iloc[-1] > senkou_b.iloc[-1])
        elif operator == "price_below_cloud":
            if senkou_a is None or senkou_b is None:
                return False
            return bool(close.iloc[-1] < senkou_a.iloc[-1] and close.iloc[-1] < senkou_b.iloc[-1])
        elif operator == "price_in_cloud":
            if senkou_a is None or senkou_b is None:
                return False
            lower_cloud = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
            upper_cloud = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
            return bool(lower_cloud.iloc[-1] <= close.iloc[-1] <= upper_cloud.iloc[-1])
        elif operator == "tenkan_crosses_kijun":
            if tenkan is None or kijun is None:
                return False
            return bool(tenkan.iloc[-2] <= kijun.iloc[-2] and tenkan.iloc[-1] > kijun.iloc[-1])
        elif operator == "price_crosses_chikou":
            if chikou is None:
                return False
            return bool(close.iloc[-2] <= chikou.iloc[-2] and close.iloc[-1] > chikou.iloc[-1])

    # SMF operators
    if isinstance(series, pd.DataFrame):
        basis = series.get("basis")
        regime_s = series.get("regime")
        retest_bull = series.get("retest_bull")
        retest_bear = series.get("retest_bear")

        if operator == "smf_above_basis":
            if basis is None:
                return False
            return bool(data["close"].iloc[-1] > basis.iloc[-1])
        elif operator == "smf_below_basis":
            if basis is None:
                return False
            return bool(data["close"].iloc[-1] < basis.iloc[-1])
        elif operator == "smf_regime_bull":
            if regime_s is None:
                return False
            return bool(regime_s.iloc[-1] == 1)
        elif operator == "smf_regime_bear":
            if regime_s is None:
                return False
            return bool(regime_s.iloc[-1] == -1)
        elif operator == "smf_retest_bull":
            if retest_bull is None:
                return False
            return bool(retest_bull.iloc[-1])
        elif operator == "smf_retest_bear":
            if retest_bear is None:
                return False
            return bool(retest_bear.iloc[-1])

    # Unknown operator
    raise ValueError(f"Unknown operator: {operator} for indicator {indicator_name}")


def _resolve_indicator(
    name: str, params: dict, indicators: dict, data: "pd.DataFrame",
) -> Any:
    """Find the computed indicator by name."""
    key = _normalize_indicator_name(name)
    for k, v in indicators.items():
        if _normalize_indicator_name(k) == key:
            return v

    # If not in pre-computed indicators, try computing inline
    from royaltdn.strategy.indicators import (
        ADX, ATR, BollingerBands, EMA, Ichimoku, MACD, OBV, ParabolicSAR,
        RSI, SMA, SmartMoneyFlowCloud, Stochastic, SuperTrend, VWAP,
        Volume, ZScore,
    )

    FUNC_MAP = {
        "sma": SMA, "ema": EMA, "rsi": RSI, "macd": MACD,
        "bollingerbands": BollingerBands, "atr": ATR,
        "volume": Volume, "ichimoku": Ichimoku, "supertrend": SuperTrend,
        "vwap": VWAP, "zscore": ZScore, "adx": ADX, "obv": OBV,
        "stochastic": Stochastic, "parabolicsar": ParabolicSAR,
        "smartmoneyflowcloud": SmartMoneyFlowCloud,
    }

    func = FUNC_MAP.get(key)
    if func is None:
        raise ValueError(f"Unknown indicator: {name}")

    result = func(data, **params)
    return result


def _normalize_indicator_name(name: str) -> str:
    return name.lower().replace(" ", "").replace("_", "")


def validate_tree(tree: dict) -> bool:
    """Validate a rule tree structure.

    Checks:
    - Has operator (AND/OR)
    - Has conditions list
    - Each condition has indicator, operator
    - Nested trees respect MAX_DEPTH
    """
    try:
        _validate_node(tree, depth=0)
        return True
    except (ValueError, KeyError, TypeError):
        return False


def _validate_node(node: dict, depth: int) -> None:
    if depth > MAX_DEPTH:
        raise ValueError(f"Max depth {MAX_DEPTH} exceeded at depth {depth}")

    if "operator" not in node:
        raise ValueError("Node missing 'operator'")
    if node["operator"] not in ("AND", "OR"):
        raise ValueError(f"Invalid operator: {node['operator']}")
    if "conditions" not in node or not isinstance(node["conditions"], list):
        raise ValueError("Node missing 'conditions' list")

    for cond in node["conditions"]:
        if "operator" in cond and "conditions" in cond:
            # Nested group
            _validate_node(cond, depth=depth + 1)
        else:
            # Leaf condition
            if "indicator" not in cond:
                raise ValueError("Leaf missing 'indicator'")
            if "operator" not in cond:
                raise ValueError("Leaf missing 'operator'")
