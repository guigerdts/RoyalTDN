"""16 indicator functions for the Dynamic Strategy Engine.

15 use pandas-ta; SmartMoneyFlowCloud is manual.
Every function accepts data: pd.DataFrame as the first argument
and returns a pd.Series or pd.DataFrame.
"""

import numpy as np
import pandas as pd
import pandas_ta as ta


def SMA(data: pd.DataFrame, period: int = 20, source: str = "close") -> pd.Series:
    """Simple Moving Average."""
    if period < 1:
        raise ValueError(f"SMA period must be >= 1, got {period}")
    result = ta.sma(data[source], length=period)
    result.name = f"SMA_{period}"
    return result


def EMA(data: pd.DataFrame, period: int = 20, source: str = "close") -> pd.Series:
    """Exponential Moving Average."""
    if period < 1:
        raise ValueError(f"EMA period must be >= 1, got {period}")
    result = ta.ema(data[source], length=period)
    result.name = f"EMA_{period}"
    return result


def RSI(data: pd.DataFrame, period: int = 14, source: str = "close") -> pd.Series:
    """Relative Strength Index."""
    if period < 1:
        raise ValueError(f"RSI period must be >= 1, got {period}")
    result = ta.rsi(data[source], length=period)
    result.name = f"RSI_{period}"
    return result


def MACD(
    data: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    source: str = "close",
) -> pd.DataFrame:
    """MACD indicator. Returns DataFrame with MACD, MACD_signal, MACD_hist."""
    if fast >= slow:
        raise ValueError(f"MACD fast ({fast}) must be < slow ({slow})")
    result = ta.macd(data[source], fast=fast, slow=slow, signal=signal)
    result.columns = ["MACD", "MACD_signal", "MACD_hist"]
    return result


def BollingerBands(
    data: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
    source: str = "close",
) -> pd.DataFrame:
    """Bollinger Bands. Returns DataFrame with BB_upper, BB_middle, BB_lower."""
    if period < 2:
        raise ValueError(f"BB period must be >= 2, got {period}")
    result = ta.bbands(data[source], length=period, std=std)
    result.columns = ["BB_lower", "BB_middle", "BB_upper", "BB_bandwidth", "BB_percent"]
    return result[["BB_upper", "BB_middle", "BB_lower"]]


def ATR(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    if period < 1:
        raise ValueError(f"ATR period must be >= 1, got {period}")
    result = ta.atr(data["high"], data["low"], data["close"], length=period)
    result.name = f"ATR_{period}"
    return result


def Volume(data: pd.DataFrame) -> pd.Series:
    """Raw volume."""
    return data["volume"]


def Ichimoku(
    data: pd.DataFrame,
    tenkan: int = 9,
    kijun: int = 26,
    senkou: int = 52,
) -> pd.DataFrame:
    """Ichimoku Cloud. Returns DataFrame with tenkan, kijun, senkou_a, senkou_b, chikou."""
    result = ta.ichimoku(
        data["high"], data["low"], data["close"],
        tenkan=tenkan, kijun=kijun, senkou=senkou,
    )
    # Returns (historical_df, forward_df)
    # historical columns: ITS_{tenkan}, IKS_{kijun}, ISA_{tenkan}, ISB_{kijun}, ICS_{kijun}
    isa, _ = result
    out = pd.DataFrame(index=data.index)
    out["tenkan"] = isa[f"ITS_{tenkan}"]
    out["kijun"] = isa[f"IKS_{kijun}"]
    out["senkou_a"] = isa[f"ISA_{tenkan}"]
    out["senkou_b"] = isa[f"ISB_{kijun}"]
    out["chikou"] = isa[f"ICS_{kijun}"]
    return out


def SuperTrend(
    data: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """SuperTrend. Returns DataFrame with supertrend and supertrend_direction."""
    result = ta.supertrend(
        data["high"], data["low"], data["close"],
        length=period, multiplier=multiplier,
    )
    # pandas-ta returns 4 columns: SUPERT, SUPERTd, SUPERTl, SUPERTs
    out = pd.DataFrame(index=data.index)
    out["supertrend"] = result.iloc[:, 0]
    out["supertrend_direction"] = result.iloc[:, 1]
    return out


def VWAP(data: pd.DataFrame, anchor: str = "D") -> pd.Series:
    """Volume-Weighted Average Price by anchor period (D/W/M)."""
    # pandas-ta vwap requires a DatetimeIndex; if not present, compute manually
    if not isinstance(data.index, pd.DatetimeIndex):
        # Manual VWAP: cumulative typical price * volume / cumulative volume
        tp = (data["high"] + data["low"] + data["close"]) / 3
        result = (tp * data["volume"]).cumsum() / data["volume"].cumsum()
        result.name = "VWAP"
        return result
    result = ta.vwap(data["high"], data["low"], data["close"], data["volume"])
    if result is None:
        tp = (data["high"] + data["low"] + data["close"]) / 3
        result = (tp * data["volume"]).cumsum() / data["volume"].cumsum()
    result.name = "VWAP"
    return result


def ZScore(
    data: pd.DataFrame,
    period: int = 21,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.5,
) -> pd.Series:
    """Z-score of close price. Returns the z-score series."""
    if period < 2:
        raise ValueError(f"ZScore period must be >= 2, got {period}")
    close = data["close"]
    rolling_mean = close.rolling(window=period).mean()
    rolling_std = close.rolling(window=period).std(ddof=0)
    z = (close - rolling_mean) / rolling_std.replace(0, np.nan)
    z.name = f"ZScore_{period}"
    return z


def ADX(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index."""
    if period < 1:
        raise ValueError(f"ADX period must be >= 1, got {period}")
    result = ta.adx(data["high"], data["low"], data["close"], length=period)
    return result[f"ADX_{period}"]


def OBV(data: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    result = ta.obv(data["close"], data["volume"])
    result.name = "OBV"
    return result


def Stochastic(
    data: pd.DataFrame,
    k_period: int = 14,
    d_period: int = 3,
    slowing: int = 3,
) -> pd.DataFrame:
    """Stochastic Oscillator. Returns DataFrame with Stoch_k, Stoch_d."""
    result = ta.stoch(
        data["high"], data["low"], data["close"],
        k=k_period, d=d_period, smooth_k=slowing,
    )
    out = pd.DataFrame(index=data.index)
    out["Stoch_k"] = result.iloc[:, 0]
    out["Stoch_d"] = result.iloc[:, 1]
    return out


def ParabolicSAR(data: pd.DataFrame, af: float = 0.02, max_af: float = 0.2) -> pd.Series:
    """Parabolic SAR."""
    result = ta.psar(data["high"], data["low"], data["close"], af=af, max_af=max_af)
    # psar returns a DataFrame with PSARl_<af>, PSARs_<af>, PSARaf_<af>
    # We take whichever PSAR column exists
    psar_cols = [c for c in result.columns if c.startswith("PSAR")]
    if not psar_cols:
        raise ValueError("Parabolic SAR returned no PSAR columns")
    return result[psar_cols[0]]


def SmartMoneyFlowCloud(
    data: pd.DataFrame,
    trend_length: int = 34,
    trend_engine: str = "EMA",
    alma_offset: float = 0.85,
    alma_sigma: float = 6.0,
    trend_smoothing: int = 3,
    flow_window: int = 24,
    flow_smoothing: int = 5,
    flow_power: float = 1.2,
    atr_length: int = 14,
    min_mult: float = 0.9,
    max_mult: float = 2.2,
) -> pd.DataFrame:
    """Smart Money Flow Cloud — manual indicator.

    Combines CLV-based money flow with adaptive ATR bands
    and a regime-tracking signal system.
    """
    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"]

    # 1. Trend basis (ALMA or EMA)
    if trend_engine == "ALMA":
        basis = ta.alma(close, length=trend_length, offset=alma_offset, sigma=alma_sigma)
    else:
        basis = ta.ema(close, length=trend_length)

    if trend_smoothing > 1 and basis is not None:
        basis = ta.ema(basis, length=trend_smoothing)

    if basis is None:
        basis = pd.Series(np.nan, index=data.index)

    # 2. Smart Money Flow
    hl_range = (high - low).replace(0, np.nan)
    clv = ((close - low) - (high - close)) / hl_range
    mf = clv * volume

    mf_smooth = ta.ema(mf, length=flow_window)
    if mf_smooth is not None:
        mf_smooth = ta.ema(mf_smooth, length=flow_smoothing)

    if mf_smooth is None:
        mf_smooth = pd.Series(np.nan, index=data.index)

    # Normalize with tanh
    flow_strength = np.tanh(np.abs(mf_smooth) ** flow_power)

    # 3. Adaptive bands
    atr = ta.atr(high, low, close, length=atr_length)
    if atr is None:
        atr = pd.Series(np.nan, index=data.index)

    dynamic_mult = min_mult + (max_mult - min_mult) * flow_strength
    upper_band = basis + atr * dynamic_mult
    lower_band = basis - atr * dynamic_mult

    # 4. Switch signals
    switch_up = (close.shift(1) <= upper_band.shift(1)) & (close > upper_band)
    switch_down = (close.shift(1) >= lower_band.shift(1)) & (close < lower_band)

    # 5. Regime (1 = bullish, -1 = bearish, 0 = neutral)
    regime = pd.Series(0, index=data.index, dtype=int)
    last_signal = 0
    for i in range(len(data)):
        if switch_up.iloc[i]:
            last_signal = 1
        elif switch_down.iloc[i]:
            last_signal = -1
        regime.iloc[i] = last_signal

    # 6. Retest signals
    retest_bull = (close < basis) & (close.shift(1) >= basis.shift(1)) & (regime.shift(1) == -1)
    retest_bear = (close > basis) & (close.shift(1) <= basis.shift(1)) & (regime.shift(1) == 1)

    return pd.DataFrame(
        {
            "basis": basis,
            "upper_band": upper_band,
            "lower_band": lower_band,
            "regime": regime,
            "flow_strength": flow_strength,
            "switch_up": switch_up,
            "switch_down": switch_down,
            "retest_bull": retest_bull,
            "retest_bear": retest_bear,
        },
        index=data.index,
    )
