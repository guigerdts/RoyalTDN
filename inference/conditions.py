"""Indicator condition catalog for the inference engine.

Each function receives market data (Series or dict) and evaluation
parameters, returning either a float value or a boolean verdict.

All functions handle edge cases: insufficient periods return False,
division by zero returns False, and errors are logged via loguru.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_numeric(
    series: Any,
    min_length: int = 1,
) -> pd.Series:
    """Retorna la serie convertida a numérico, o una serie vacía si falla.

    Coerce inputs to numeric dtype and drop NaN/None values.  Returns an
    empty ``float64`` Series when the input is unusable or shorter than
    *min_length* — safe to chain with ``.mean()``, ``.std()``, etc.
    """
    if not isinstance(series, (pd.Series, np.ndarray)):
        return pd.Series(dtype=float)
    try:
        numeric = pd.to_numeric(series, errors="coerce")
        numeric = numeric.dropna()
        if len(numeric) < min_length:
            return pd.Series(dtype=float)
        return numeric
    except Exception:
        return pd.Series(dtype=float)


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
        logger.trace("Momentum: insufficient data (need {})", period + 1)
        return 0.0
    prev = series.iloc[-period - 1]
    if prev == 0.0:
        logger.trace("Momentum: division by zero")
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
        logger.trace("Volume surge: insufficient data (need {})", period + 1)
        return False
    avg_vol = float(_safe_numeric(series.iloc[-period - 1 : -1]).mean())
    if pd.isna(avg_vol) or avg_vol == 0.0:
        logger.trace("Volume surge: average volume is zero")
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
        logger.trace("RSI: insufficient data (need {})", period + 1)
        return 50.0

    deltas = series.diff().iloc[1:]
    gains = deltas.where(deltas > 0, 0.0)
    losses = (-deltas).where(deltas < 0, 0.0)

    gains_safe = _safe_numeric(gains, min_length=period)
    losses_safe = _safe_numeric(losses, min_length=period)

    if len(gains_safe) < 1 or len(losses_safe) < 1:
        return 50.0

    avg_gain = gains_safe.rolling(window=period, min_periods=period).mean().iloc[-1]
    avg_loss = losses_safe.rolling(window=period, min_periods=period).mean().iloc[-1]

    if pd.isna(avg_gain) or pd.isna(avg_loss):
        return 50.0
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
    series = _safe_numeric(_to_series(data, "close"), min_length=1)
    if len(series) < 1:
        logger.trace("EMA: no data")
        return 0.0
    if len(series) < period:
        logger.trace("EMA: insufficient data, returning last price")
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
    high = _safe_numeric(
        _to_series(data, "high") if isinstance(data, dict) else _to_series(data),
        min_length=1,
    )
    low = _safe_numeric(
        _to_series(data, "low") if isinstance(data, dict) else _to_series(data),
        min_length=1,
    )
    close = _safe_numeric(
        _to_series(data, "close") if isinstance(data, dict) else _to_series(data),
        min_length=1,
    )

    if len(close) < period + 1:
        logger.trace("ADX: insufficient data (need {})", period + 1)
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
    tr_safe = _safe_numeric(tr, min_length=period)
    if len(tr_safe) < 1:
        return 0.0
    atr = tr_safe.rolling(window=period, min_periods=period).mean()
    if pd.isna(atr.iloc[-1]):
        return 0.0

    # Directional Movement
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(0.0, index=up_move.index)
    minus_dm = pd.Series(0.0, index=down_move.index)

    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    plus_dm_safe = _safe_numeric(plus_dm, min_length=period)
    minus_dm_safe = _safe_numeric(minus_dm, min_length=period)
    if len(plus_dm_safe) < 1 or len(minus_dm_safe) < 1:
        return 0.0

    plus_di = 100.0 * (plus_dm_safe.rolling(window=period, min_periods=period).mean() / atr)
    minus_di = 100.0 * (
        minus_dm_safe.rolling(window=period, min_periods=period).mean() / atr
    )

    # ADX
    dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA))
    dx_safe = _safe_numeric(dx, min_length=period)
    if len(dx_safe) < 1:
        return 0.0
    adx_series = dx_safe.rolling(window=period, min_periods=period).mean()

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
        logger.trace("Z-score: insufficient data (need {})", period + 1)
        return 0.0

    window = _safe_numeric(series.iloc[-period - 1 : -1], min_length=2)
    if len(window) < 2:
        logger.trace("Z-score: insufficient data (need {})", period + 1)
        return 0.0

    mean = window.mean()
    std = window.std()

    if pd.isna(mean) or pd.isna(std) or std == 0.0:
        logger.trace("Z-score: standard deviation is zero")
        return 0.0

    return float((series.iloc[-1] - mean) / std)


# ---------------------------------------------------------------------------
# New indicators (7)
# ---------------------------------------------------------------------------


def range_breakout(data: Any, period: int = 10, factor: float = 0.5) -> bool:
    """Detect if price breaks out of a recent range by *factor* of range width.

    Range is defined as ``highest_high - lowest_low`` over *period* bars.
    Breakout is confirmed when current close exceeds the range boundary
    by at least ``range_width * factor``.

    Args:
        data: Dict with ``high``, ``low``, ``close`` lists.
        period: Lookback window.
        factor: Multiplier on range width to confirm breakout.

    Returns:
        True if an upside or downside breakout is detected.
    """
    close = _safe_numeric(_to_series(data, "close"), min_length=period)
    high = _safe_numeric(_to_series(data, "high"), min_length=period)
    low = _safe_numeric(_to_series(data, "low"), min_length=period)

    if len(close) < period + 1 or len(high) < period + 1 or len(low) < period + 1:
        return False

    range_high = float(high.iloc[-period - 1 : -1].max())
    range_low = float(low.iloc[-period - 1 : -1].min())
    range_width = range_high - range_low

    if range_width == 0.0:
        return False

    current_close = float(close.iloc[-1])
    threshold = range_width * factor

    # Upside breakout: close breaks above range high + threshold
    if current_close > range_high + threshold:
        return True
    # Downside breakout: close breaks below range low - threshold
    if current_close < range_low - threshold:
        return True

    return False


def vwap_deviation(data: Any, factor: float = 1.5) -> bool:
    """Check if current price deviates significantly from VWAP.

    VWAP = sum(price * volume) / sum(volume) over all available bars.
    Deviation = abs(close - vwap) / vwap * 100.

    Args:
        data: Dict with ``close`` and ``volume`` lists.
        factor: Deviation threshold in percent.

    Returns:
        True if deviation > factor.
    """
    close = _safe_numeric(_to_series(data, "close"), min_length=5)
    volume = _safe_numeric(_to_series(data, "volume"), min_length=5)

    if len(close) < 5 or len(volume) < 5:
        return False

    # VWAP = Σ(typical_price * volume) / Σ(volume)
    # Using close as typical price for simplicity
    vwap = float((close * volume).sum() / volume.sum())

    if vwap == 0.0:
        return False

    deviation_pct = abs(float(close.iloc[-1]) - vwap) / vwap * 100.0
    return deviation_pct > factor


def ichimoku(data: Any, tenkan: int = 7, kijun: int = 22, senkou_b: int = 44) -> bool:
    """Evaluate Ichimoku Cloud trend.

    Calculates Tenkan-sen, Kijun-sen, Senkou Span A, and Senkou Span B.
    Returns True for a confirmed trend direction:
      - Bullish: price above cloud AND Tenkan > Kijun
      - Bearish: price below cloud AND Tenkan < Kijun

    Args:
        data: Dict with ``high``, ``low``, ``close`` lists.
        tenkan: Tenkan-sen period.
        kijun: Kijun-sen period.
        senkou_b: Senkou Span B period.

    Returns:
        True if a clear trend is confirmed.
    """
    # Need enough data for the longest period
    lookback = max(tenkan, kijun, senkou_b)
    close = _safe_numeric(_to_series(data, "close"), min_length=lookback)
    high = _safe_numeric(_to_series(data, "high"), min_length=lookback)
    low = _safe_numeric(_to_series(data, "low"), min_length=lookback)

    if len(close) < lookback + 1:
        return False

    # Tenkan-sen: (highest high + lowest low) / 2 over tenkan period
    tenkan_high = float(high.iloc[-tenkan:].max())
    tenkan_low = float(low.iloc[-tenkan:].min())
    tenkan_val = (tenkan_high + tenkan_low) / 2.0

    # Kijun-sen: (highest high + lowest low) / 2 over kijun period
    kijun_high = float(high.iloc[-kijun:].max())
    kijun_low = float(low.iloc[-kijun:].min())
    kijun_val = (kijun_high + kijun_low) / 2.0

    # Senkou Span A: (tenkan + kijun) / 2
    senkou_a = (tenkan_val + kijun_val) / 2.0

    # Senkou Span B: (highest high + lowest low) / 2 over senkou_b period
    senkou_b_high = float(high.iloc[-senkou_b:].max())
    senkou_b_low = float(low.iloc[-senkou_b:].min())
    senkou_b_val = (senkou_b_high + senkou_b_low) / 2.0

    current_close = float(close.iloc[-1])

    # Bullish: price above cloud AND Tenkan > Kijun
    cloud_top = max(senkou_a, senkou_b_val)
    if current_close > cloud_top and tenkan_val > kijun_val:
        return True

    # Bearish: price below cloud AND Tenkan < Kijun
    cloud_bottom = min(senkou_a, senkou_b_val)
    if current_close < cloud_bottom and tenkan_val < kijun_val:
        return True

    return False


def support_resistance(
    data: Any,
    lookback: int = 100,
    touch_count: int = 2,
) -> bool:
    """Check if price is near a significant support or resistance level.

    Identifies levels by clustering local minima (support) and maxima
    (resistance) in the lookback window.  A level is valid if price
    has touched it *touch_count* times.  Returns True when current
    price is within 0.5 % of a valid level.

    Args:
        data: Dict with ``high``, ``low``, ``close`` lists.
        lookback: Number of bars to scan.
        touch_count: Minimum touches for a level to be significant.

    Returns:
        True if price is near a valid support or resistance level.
    """
    close = _safe_numeric(_to_series(data, "close"), min_length=lookback)
    high = _safe_numeric(_to_series(data, "high"), min_length=lookback)
    low = _safe_numeric(_to_series(data, "low"), min_length=lookback)

    if len(close) < lookback + 1:
        return False

    # Find local minima (support candidates) and maxima (resistance)
    window = 5  # look 2 bars each side for local extrema
    supports: list[float] = []
    resistances: list[float] = []

    for i in range(window, lookback - window):
        if low.iloc[i] == low.iloc[i - window : i + window + 1].min():
            supports.append(float(low.iloc[i]))
        if high.iloc[i] == high.iloc[i - window : i + window + 1].max():
            resistances.append(float(high.iloc[i]))

    # Cluster nearby levels (within 0.5 %)
    def _cluster(levels: list[float], tolerance: float = 0.005) -> list[float]:
        if not levels:
            return []
        levels.sort()
        clustered: list[float] = []
        group: list[float] = [levels[0]]
        for lvl in levels[1:]:
            if abs(lvl - group[-1]) / max(abs(group[-1]), 1.0) <= tolerance:
                group.append(lvl)
            else:
                clustered.append(sum(group) / len(group))
                group = [lvl]
        if group:
            clustered.append(sum(group) / len(group))
        return clustered

    clustered_support = _cluster(supports)
    clustered_resistance = _cluster(resistances)

    current_close = float(close.iloc[-1])
    proximity = 0.005  # 0.5 %

    for level in clustered_support:
        if abs(current_close - level) / max(level, 1.0) <= proximity:
            return True

    for level in clustered_resistance:
        if abs(current_close - level) / max(level, 1.0) <= proximity:
            return True

    return False


def spread(data: Any, max_spread_pct: float = 0.1) -> bool:
    """Check if market is liquid enough.

    Since bid/ask data is not available from Binance ticker streams,
    uses the current bar's high-low range as a spread proxy.

    ``spread_pct = (high - low) / close * 100``

    Args:
        data: Dict with ``high``, ``low``, ``close`` lists.
        max_spread_pct: Maximum acceptable spread in percent.

    Returns:
        True if the market is sufficiently liquid (spread < max).
    """
    close = _safe_numeric(_to_series(data, "close"), min_length=1)
    high = _safe_numeric(_to_series(data, "high"), min_length=1)
    low = _safe_numeric(_to_series(data, "low"), min_length=1)

    if len(close) < 1:
        return True  # cannot measure → assume liquid

    current_close = float(close.iloc[-1])
    if current_close == 0.0:
        return True

    current_high = float(high.iloc[-1]) if len(high) > 0 else current_close
    current_low = float(low.iloc[-1]) if len(low) > 0 else current_close

    spread_pct = (current_high - current_low) / current_close * 100.0
    return spread_pct < max_spread_pct


def macd_divergence(
    data: Any,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    lookback: int = 20,
) -> bool:
    """Detect MACD divergence (bullish or bearish).

    Calculates MACD line = EMA(fast) - EMA(slow) and its signal line.
    Scans the last *lookback* bars for:
      - Bullish divergence: price makes lower low, MACD makes higher low.
      - Bearish divergence: price makes higher high, MACD makes lower high.

    Args:
        data: Dict with ``close`` list.
        fast: Fast EMA period.
        slow: Slow EMA period.
        signal: Signal EMA period.
        lookback: Window to scan for divergences.

    Returns:
        True if a divergence pattern is detected.
    """
    close = _safe_numeric(_to_series(data, "close"), min_length=slow + lookback)
    if len(close) < slow + lookback:
        return False

    # MACD line
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow

    # Use the last `lookback` bars
    macd_window = _safe_numeric(macd_line.iloc[-lookback:], min_length=5)
    close_window = _safe_numeric(close.iloc[-lookback:], min_length=5)

    if len(macd_window) < 5 or len(close_window) < 5:
        return False

    # Find local minima and maxima
    def _find_turns(series: pd.Series) -> tuple[list[int], list[int]]:
        minima: list[int] = []
        maxima: list[int] = []
        for i in range(2, len(series) - 2):
            if series.iloc[i] == series.iloc[i - 2 : i + 3].min():
                minima.append(i)
            if series.iloc[i] == series.iloc[i - 2 : i + 3].max():
                maxima.append(i)
        return minima, maxima

    close_minima, close_maxima = _find_turns(close_window)
    macd_minima, macd_maxima = _find_turns(macd_window)

    # Bullish divergence: price lower low, MACD higher low
    for ci in close_minima:
        if ci <= 0 or ci >= len(close_window):
            continue
        prev_close_low = float(close_window.iloc[:ci].min())
        if prev_close_low < float(close_window.iloc[ci]):
            continue  # no lower low

        # Find matching MACD low around same index
        for mi in macd_minima:
            if abs(mi - ci) <= 2:  # allow small offset
                prev_macd_low = float(macd_window.iloc[:mi].min())
                if float(macd_window.iloc[mi]) > prev_macd_low:
                    # price lower low, MACD higher low → bullish divergence
                    return True

    # Bearish divergence: price higher high, MACD lower high
    for ci in close_maxima:
        if ci <= 0 or ci >= len(close_window):
            continue
        prev_close_high = float(close_window.iloc[:ci].max())
        if prev_close_high > float(close_window.iloc[ci]):
            continue  # no higher high

        for mi in macd_maxima:
            if abs(mi - ci) <= 2:
                prev_macd_high = float(macd_window.iloc[:mi].max())
                if float(macd_window.iloc[mi]) < prev_macd_high:
                    # price higher high, MACD lower high → bearish divergence
                    return True

    return False


def atr(data: Any, period: int = 20, max_pct: float = 4.0) -> bool:
    """Check if volatility (ATR%) is within acceptable range.

    ATR% = ATR / close * 100.  Returns True when ATR% < max_pct,
    meaning the market is in a controlled-volatility regime.

    Args:
        data: Dict with ``high``, ``low``, ``close`` lists.
        period: ATR lookback window.
        max_pct: Maximum acceptable ATR as percent of price.

    Returns:
        True if volatility is below the threshold.
    """
    close = _safe_numeric(_to_series(data, "close"), min_length=period + 1)
    high = _safe_numeric(_to_series(data, "high"), min_length=period + 1)
    low = _safe_numeric(_to_series(data, "low"), min_length=period + 1)

    if len(close) < period + 1:
        return False

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr_safe = _safe_numeric(tr, min_length=period)
    if len(tr_safe) < 1:
        return False

    atr_val = float(tr_safe.rolling(window=period, min_periods=period).mean().iloc[-1])
    if pd.isna(atr_val) or atr_val == 0.0:
        return False

    current_close = float(close.iloc[-1])
    if current_close == 0.0:
        return False

    atr_pct = atr_val / current_close * 100.0
    return atr_pct < max_pct


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
    "range_breakout": range_breakout,
    "vwap_deviation": vwap_deviation,
    "ichimoku": ichimoku,
    "support_resistance": support_resistance,
    "spread": spread,
    "macd_divergence": macd_divergence,
    "atr": atr,
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
