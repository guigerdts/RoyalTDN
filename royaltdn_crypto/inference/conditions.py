"""Indicator condition catalog for the inference engine.

Each function receives market data (Series or dict) and evaluation
parameters, returning either a float value or a boolean verdict.

All functions handle edge cases: insufficient periods return False,
division by zero returns False, and errors are logged via loguru.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_series(data: Any, key: str = "close") -> pd.Series:
    """Normalise *data* into a pandas Series.

    If *data* is a dict, extract the *key* column and convert to Series.
    If it is already a Series, return it as-is.

    Args:
        data: Raw market data (dict, Series, or list-like).
        key: Dict key to extract when *data* is a dict.

    Returns:
        A pandas Series of values.
    """
    if isinstance(data, pd.Series):
        return data
    if isinstance(data, dict):
        vals = data.get(key)
        if vals is None:
            logger.warning("Key '{}' not found in data dict", key)
            return pd.Series(dtype="float64")
        return pd.Series(vals) if not isinstance(vals, pd.Series) else vals
    # Assume list-like
    return pd.Series(data)


# ---------------------------------------------------------------------------
# Indicator functions
# ---------------------------------------------------------------------------


def momentum(data: Any, period: int = 3) -> float:
    """Calculate price momentum over *period* bars.

    ``(price_t - price_{t-period}) / price_{t-period}``

    Args:
        data: Price series.
        period: Lookback window.

    Returns:
        Momentum ratio, or 0.0 if insufficient data.
    """
    series = _to_series(data, "close")
    if len(series) < period + 1:
        logger.debug("Momentum: insufficient data (need {})", period + 1)
        return 0.0
    prev = series.iloc[-period - 1]
    if prev == 0.0:
        logger.debug("Momentum: division by zero")
        return 0.0
    return float((series.iloc[-1] - prev) / prev)


def volume_surge(data: Any, period: int = 20, factor: float = 2.0) -> bool:
    """Detect a volume surge relative to the rolling average.

    ``volume_t / avg_volume(period) > factor``

    Args:
        data: Volume series.
        period: Rolling window for average.
        factor: Multiplier threshold.

    Returns:
        True if current volume exceeds the average by *factor*.
    """
    series = _to_series(data, "volume")
    if len(series) < period + 1:
        logger.debug("Volume surge: insufficient data (need {})", period + 1)
        return False
    avg_vol = float(series.iloc[-period - 1 : -1].mean())
    if avg_vol == 0.0:
        logger.debug("Volume surge: average volume is zero")
        return False
    return float(series.iloc[-1]) / avg_vol > factor


def rsi(data: Any, period: int = 7) -> float:
    """Calculate the Relative Strength Index (RSI).

    Standard Welles Wilder RSI over the lookback window.

    Args:
        data: Price series.
        period: RSI lookback period.

    Returns:
        RSI value (0-100), or 50.0 if insufficient data.
    """
    series = _to_series(data, "close")
    if len(series) < period + 1:
        logger.debug("RSI: insufficient data (need {})", period + 1)
        return 50.0

    deltas = series.diff().iloc[1:]
    gains = deltas.where(deltas > 0, 0.0)
    losses = (-deltas).where(deltas < 0, 0.0)

    avg_gain = gains.rolling(window=period, min_periods=period).mean().iloc[-1]
    avg_loss = losses.rolling(window=period, min_periods=period).mean().iloc[-1]

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def ema(data: Any, period: int = 15) -> float:
    """Calculate the Exponential Moving Average (EMA).

    Args:
        data: Price series.
        period: EMA lookback period.

    Returns:
        Current EMA value, or the last price (as fallback).
    """
    series = _to_series(data, "close")
    if len(series) < 1:
        logger.debug("EMA: no data")
        return 0.0
    if len(series) < period:
        logger.debug("EMA: insufficient data, returning last price")
        return float(series.iloc[-1])

    ema_series = series.ewm(span=period, adjust=False).mean()
    return float(ema_series.iloc[-1])


def adx(data: Any, period: int = 10) -> float:
    """Calculate the Average Directional Index (ADX).

    Simplified ADX calculation using price high/low/close.

    Args:
        data: Dict or DataFrame with ``high``, ``low``, ``close`` keys.
        period: ADX lookback period.

    Returns:
        ADX value (0-100), or 0.0 if insufficient data.
    """
    high = _to_series(data, "high") if isinstance(data, dict) else _to_series(data)
    low = _to_series(data, "low") if isinstance(data, dict) else _to_series(data)
    close = _to_series(data, "close") if isinstance(data, dict) else _to_series(data)

    if len(close) < period + 1:
        logger.debug("ADX: insufficient data (need {})", period + 1)
        return 0.0

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()

    # Directional Movement
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(0.0, index=up_move.index)
    minus_dm = pd.Series(0.0, index=down_move.index)

    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    plus_di = 100.0 * (plus_dm.rolling(window=period, min_periods=period).mean() / atr)
    minus_di = 100.0 * (
        minus_dm.rolling(window=period, min_periods=period).mean() / atr
    )

    # ADX
    dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA))
    adx_series = dx.rolling(window=period, min_periods=period).mean()

    if pd.isna(adx_series.iloc[-1]):
        return 0.0
    return float(adx_series.iloc[-1])


def zscore(data: Any, period: int = 20) -> float:
    """Calculate the Z-score of the current price.

    ``(price - mean) / std``

    Args:
        data: Price series.
        period: Rolling window for mean and std.

    Returns:
        Z-score value, or 0.0 if insufficient data or zero std.
    """
    series = _to_series(data, "close")
    if len(series) < period + 1:
        logger.debug("Z-score: insufficient data (need {})", period + 1)
        return 0.0

    window = series.iloc[-period - 1 : -1]
    mean = window.mean()
    std = window.std()

    if std == 0.0:
        logger.debug("Z-score: standard deviation is zero")
        return 0.0

    return float((series.iloc[-1] - mean) / std)


# ---------------------------------------------------------------------------
# Indicator registry
# ---------------------------------------------------------------------------

_INDICATORS: dict[str, Any] = {
    "momentum": momentum,
    "volume_surge": volume_surge,
    "rsi": rsi,
    "ema": ema,
    "adx": adx,
    "zscore": zscore,
}

# ---------------------------------------------------------------------------
# Operator parsing and evaluation
# ---------------------------------------------------------------------------

_OPERATOR_RE = re.compile(
    r"^\s*"
    r"(?P<left_word>[a-zA-Z_]\w*|\d+\.?\d*)\s+"
    r"(?P<op>>=|<=|!=|==|>|<)"
    r"\s+(?P<right_word>[a-zA-Z_]\w*|-?\d+\.?\d*)"
    r"\s*$"
)

_SIMPLE_OP_RE = re.compile(
    r"^\s*(?P<op>>=|<=|!=|==|>|<)\s*(?P<value>-?\d+\.?\d*)\s*$"
)


def _resolve_value(word: str, data: Any) -> float:
    """Resolve a word to a numeric value.

    ``price`` maps to the last close price.
    Any other word is treated as an indicator name and calculated.

    Args:
        word: The word to resolve ('price', indicator name, or number).
        data: Market data to pass to indicator functions.

    Returns:
        The resolved numeric value.
    """
    word_lower = word.lower().strip()

    # Numbers
    try:
        return float(word_lower)
    except ValueError:
        pass

    # Special alias
    if word_lower == "price":
        series = _to_series(data, "close")
        return float(series.iloc[-1]) if len(series) > 0 else 0.0

    # Indicator
    if word_lower in _INDICATORS:
        return _INDICATORS[word_lower](data)

    logger.warning("Unknown identifier '{}' in operator, returning 0.0", word)
    return 0.0


_COMP_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate(
    indicator: str,
    params: dict[str, Any],
    operator: str,
    data: Any,
) -> bool:
    """Evaluate a single condition against market data.

    Flow:
    1. Calculate the primary indicator value (unless the operator
       is compound, in which case both sides are resolved from the
       operator string itself).
    2. Parse the operator string.
    3. Return the boolean result.

    Simple operator examples: ``> 30``, ``<= -2.5``
    Compound operator example: ``price > ema``

    Args:
        indicator: Name of the primary indicator (e.g. ``rsi``).
        params: Dict of parameters for the indicator function.
        operator: Operator string (simple or compound).
        data: Market data dict or Series.

    Returns:
        True if the condition is satisfied, False otherwise.

    Raises:
        ValueError: If the operator format is unrecognised.
    """
    # Try compound operator first: "word op word"
    compound_match = _OPERATOR_RE.match(operator)
    if compound_match:
        left_val = _resolve_value(compound_match.group("left_word"), data)
        op_fn = _COMP_OPS[compound_match.group("op")]
        right_val = _resolve_value(compound_match.group("right_word"), data)
        return op_fn(left_val, right_val)

    # Simple operator: "op value"
    simple_match = _SIMPLE_OP_RE.match(operator)
    if simple_match:
        # Calculate the primary indicator
        if indicator not in _INDICATORS:
            logger.warning("Unknown indicator '{}', returning False", indicator)
            return False
        indicator_val = _INDICATORS[indicator](data, **params)
        op_fn = _COMP_OPS[simple_match.group("op")]
        threshold = float(simple_match.group("value"))
        return op_fn(indicator_val, threshold)

    raise ValueError(f"Unrecognised operator format: '{operator}'")
