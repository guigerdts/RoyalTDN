"""PR-3a Tests: explain() for 5 intraday strategies.

Tests per strategy:
1. _compute_indicators — expected keys present
2. explain_structure — valid return dict with indicators/conditions/signal
3. signal_consistency — explain()["signal"] matches generate_signal()
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from royaltdn.strategy.intraday_vwap import IntradayVWAPStrategy
from royaltdn.strategy.intraday_volume_breakout import IntradayVolumeBreakoutStrategy
from royaltdn.strategy.intraday_trend import IntradayTrendStrategy
from royaltdn.strategy.intraday_support_resistance import IntradaySupportResistanceStrategy
from royaltdn.strategy.intraday_macd_divergence import IntradayMACDDivergenceStrategy


# ── Fixtures ──────────────────────────────────────────────────────────────

def _sample_ohlcv(n: int = 60, start_price: float = 100.0, trend: float = 0.0) -> pd.DataFrame:
    np.random.seed(42)
    prices = [start_price]
    for i in range(1, n):
        change = np.random.normal(trend, 1.0)
        prices.append(prices[-1] * (1 + change / 100))
    close = pd.Series(prices)
    high = close * (1 + abs(np.random.normal(0, 0.5, n)) / 100)
    low = close * (1 - abs(np.random.normal(0, 0.5, n)) / 100)
    volume = pd.Series(np.random.randint(500000, 2000000, n))
    return pd.DataFrame({
        "open": close * (1 + np.random.normal(0, 0.1, n) / 100),
        "high": high, "low": low, "close": close, "volume": volume,
    })


def _uptrend_data(n: int = 60) -> pd.DataFrame:
    return _sample_ohlcv(n, start_price=100.0, trend=0.3)


# ── Strategy 1: IntradayVWAP ──────────────────────────────────────────────

def test_vwap_compute_indicators():
    s = IntradayVWAPStrategy(vwap_period=10)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    for key in ("vwap", "std", "lower_band", "upper_band", "close"):
        assert key in ind, f"Missing key: {key}"
        assert ind[key] is not None, f"None value: {key}"
    print("  ✅ vwap _compute_indicators keys")


def test_vwap_explain_structure():
    s = IntradayVWAPStrategy(vwap_period=10)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    for c in result["conditions"]:
        for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
            assert key in c, f"Missing condition key: {key}"
    print("  ✅ vwap explain() structure")


def test_vwap_signal_consistency():
    s = IntradayVWAPStrategy(vwap_period=10)
    data = _sample_ohlcv(60)
    gen = s.generate_signal(data)
    exp = s.explain(data)
    assert exp["signal"] == gen
    print("  ✅ vwap signal consistency")


# ── Strategy 2: IntradayVolumeBreakout ────────────────────────────────────

def test_volume_breakout_compute_indicators():
    s = IntradayVolumeBreakoutStrategy(breakout_period=10)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    for key in ("volume_ratio", "avg_volume", "close", "range_high", "range_low"):
        assert key in ind, f"Missing key: {key}"
        assert ind[key] is not None, f"None value: {key}"
    print("  ✅ volume_breakout _compute_indicators keys")


def test_volume_breakout_explain_structure():
    s = IntradayVolumeBreakoutStrategy(breakout_period=10)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    for c in result["conditions"]:
        for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
            assert key in c
    print("  ✅ volume_breakout explain() structure")


def test_volume_breakout_signal_consistency():
    s = IntradayVolumeBreakoutStrategy(breakout_period=10)
    data = _sample_ohlcv(60)
    gen = s.generate_signal(data)
    exp = s.explain(data)
    assert exp["signal"] == gen
    print("  ✅ volume_breakout signal consistency")


# ── Strategy 3: IntradayTrend ─────────────────────────────────────────────

def test_trend_compute_indicators():
    s = IntradayTrendStrategy(ema_fast=5, ema_slow=10, trend_period=10)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    for key in ("ema_fast_val", "ema_slow_val", "atr_pct", "close"):
        assert key in ind, f"Missing key: {key}"
        assert ind[key] is not None, f"None value: {key}"
    print("  ✅ trend _compute_indicators keys")


def test_trend_explain_structure():
    s = IntradayTrendStrategy(ema_fast=5, ema_slow=10, trend_period=10)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    for c in result["conditions"]:
        for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
            assert key in c
    print("  ✅ trend explain() structure")


def test_trend_signal_consistency():
    s = IntradayTrendStrategy(ema_fast=5, ema_slow=10, trend_period=10)
    data = _sample_ohlcv(60)
    gen = s.generate_signal(data)
    exp = s.explain(data)
    assert exp["signal"] == gen
    print("  ✅ trend signal consistency")


# ── Strategy 4: IntradaySupportResistance ─────────────────────────────────

def test_support_resistance_compute_indicators():
    s = IntradaySupportResistanceStrategy(sr_period=10)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    for key in ("support", "resistance", "close", "prev_close", "zone_width"):
        assert key in ind, f"Missing key: {key}"
        assert ind[key] is not None, f"None value: {key}"
    print("  ✅ support_resistance _compute_indicators keys")


def test_support_resistance_explain_structure():
    s = IntradaySupportResistanceStrategy(sr_period=10)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    for c in result["conditions"]:
        for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
            assert key in c
    print("  ✅ support_resistance explain() structure")


def test_support_resistance_signal_consistency():
    s = IntradaySupportResistanceStrategy(sr_period=10)
    data = _sample_ohlcv(60)
    gen = s.generate_signal(data)
    exp = s.explain(data)
    assert exp["signal"] == gen
    print("  ✅ support_resistance signal consistency")


# ── Strategy 5: IntradayMACDDivergence ────────────────────────────────────

def test_macd_divergence_compute_indicators():
    s = IntradayMACDDivergenceStrategy(fast_period=5, slow_period=10, signal_period=5)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    for key in ("price_low1", "price_low2", "price_high1", "price_high2",
                "macd_low1", "macd_low2", "macd_high1", "macd_high2", "close"):
        assert key in ind, f"Missing key: {key}"
        assert ind[key] is not None, f"None value: {key}"
    print("  ✅ macd_divergence _compute_indicators keys")


def test_macd_divergence_explain_structure():
    s = IntradayMACDDivergenceStrategy(fast_period=5, slow_period=10, signal_period=5)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    for c in result["conditions"]:
        for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
            assert key in c
    print("  ✅ macd_divergence explain() structure")


def test_macd_divergence_signal_consistency():
    s = IntradayMACDDivergenceStrategy(fast_period=5, slow_period=10, signal_period=5)
    data = _sample_ohlcv(60)
    gen = s.generate_signal(data)
    exp = s.explain(data)
    assert exp["signal"] == gen
    print("  ✅ macd_divergence signal consistency")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("PR-3a — 5 Intraday Strategies explain()")
    print("=" * 50)

    # VWAP
    test_vwap_compute_indicators()
    test_vwap_explain_structure()
    test_vwap_signal_consistency()

    # Volume Breakout
    test_volume_breakout_compute_indicators()
    test_volume_breakout_explain_structure()
    test_volume_breakout_signal_consistency()

    # Trend
    test_trend_compute_indicators()
    test_trend_explain_structure()
    test_trend_signal_consistency()

    # Support/Resistance
    test_support_resistance_compute_indicators()
    test_support_resistance_explain_structure()
    test_support_resistance_signal_consistency()

    # MACD Divergence
    test_macd_divergence_compute_indicators()
    test_macd_divergence_explain_structure()
    test_macd_divergence_signal_consistency()

    print("\n✅ PR-3a TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
