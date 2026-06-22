"""PR-1b Tests: momentum_atr + swing_trend_following + swing_breakout explain().

Verifies:
1. _compute_indicators() returns expected keys for all 3 strategies
2. explain() returns valid structure (indicators, conditions, signal)
3. explain()["signal"] matches generate_signal() for same data
"""

import sys
import os
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from royaltdn.strategy.momentum_atr import MomentumATRStrategy
from royaltdn.strategy.swing_trend_following import SwingTrendFollowingStrategy
from royaltdn.strategy.swing_breakout import SwingBreakoutStrategy


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
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ── Test 1: momentum_atr explain() ───────────────────────────────────────

def test_momentum_atr_compute_indicators():
    s = MomentumATRStrategy(momentum_period=10, atr_period=5)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "momentum_return" in ind
    assert "last_atr" in ind
    assert "atr_pct" in ind
    assert "close" in ind
    print("  ✅ momentum_atr _compute_indicators keys")


def test_momentum_atr_explain_structure():
    s = MomentumATRStrategy(momentum_period=10, atr_period=5)
    data = _sample_ohlcv(60, start_price=100.0, trend=0.3)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    print("  ✅ momentum_atr explain() structure")


def test_momentum_atr_signal_consistency():
    s = MomentumATRStrategy(momentum_period=10, atr_period=5, atr_max_pct=10.0)
    vals = [100.0] + [100 + i * 0.5 for i in range(1, 15)]
    data = pd.DataFrame({
        "close": vals,
        "high": [v + 1 for v in vals],
        "low": [v - 1 for v in vals],
    })
    gen_signal = s.generate_signal(data)
    exp_result = s.explain(data)
    if gen_signal is not None:
        assert exp_result["signal"] is not None
        assert exp_result["signal"]["action"] == gen_signal["action"]
    print("  ✅ momentum_atr signal consistency")


# ── Test 2: swing_trend_following explain() ─────────────────────────────

def test_swing_trend_following_compute_indicators():
    s = SwingTrendFollowingStrategy(fast_ema=10, slow_ema=30)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "ema_fast" in ind
    assert "ema_slow" in ind
    assert "atr_pct" in ind
    assert "close" in ind
    print("  ✅ swing_trend_following _compute_indicators keys")


def test_swing_trend_following_explain_structure():
    s = SwingTrendFollowingStrategy(fast_ema=10, slow_ema=30)
    data = _sample_ohlcv(60, start_price=100.0, trend=0.3)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    print("  ✅ swing_trend_following explain() structure")


def test_swing_trend_following_signal_consistency():
    s = SwingTrendFollowingStrategy(fast_ema=10, slow_ema=30, trend_strength=5.0)
    vals = [100.0] + [100 + i * 0.3 for i in range(1, 40)]
    data = pd.DataFrame({
        "close": vals,
        "high": [v + 1 for v in vals],
        "low": [v - 1 for v in vals],
    })
    gen_signal = s.generate_signal(data)
    exp_result = s.explain(data)
    if gen_signal is not None:
        assert exp_result["signal"] is not None
        assert exp_result["signal"]["action"] == gen_signal["action"]
    print("  ✅ swing_trend_following signal consistency")


# ── Test 3: swing_breakout explain() ────────────────────────────────────

def test_swing_breakout_compute_indicators():
    s = SwingBreakoutStrategy(breakout_period=20)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "close" in ind
    assert "recent_high" in ind
    assert "recent_low" in ind
    assert "volume_ratio" in ind
    print("  ✅ swing_breakout _compute_indicators keys")


def test_swing_breakout_explain_structure():
    s = SwingBreakoutStrategy(breakout_period=20)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    print("  ✅ swing_breakout explain() structure")


def test_swing_breakout_signal_consistency():
    s = SwingBreakoutStrategy(breakout_period=20, volume_confirm=False)
    closes = [100.0] * 25 + [105.0, 110.0, 115.0, 120.0]
    highs = [101.0] * 25 + [106.0, 111.0, 116.0, 122.0]
    lows = [99.0] * 25 + [104.0, 109.0, 114.0, 118.0]
    volumes = [1000000] * 29
    data = pd.DataFrame({
        "close": closes + [125.0],
        "high": highs + [125.0],
        "low": lows + [120.0],
        "volume": volumes + [2000000],
    })
    gen_signal = s.generate_signal(data)
    exp_result = s.explain(data)
    if gen_signal is not None:
        assert exp_result["signal"] is not None
        assert exp_result["signal"]["action"] == gen_signal["action"]
    print("  ✅ swing_breakout signal consistency")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("PR-1b — momentum_atr + swing_trend_following + swing_breakout")
    print("=" * 50)

    test_momentum_atr_compute_indicators()
    test_momentum_atr_explain_structure()
    test_momentum_atr_signal_consistency()

    test_swing_trend_following_compute_indicators()
    test_swing_trend_following_explain_structure()
    test_swing_trend_following_signal_consistency()

    test_swing_breakout_compute_indicators()
    test_swing_breakout_explain_structure()
    test_swing_breakout_signal_consistency()

    print("\n✅ PR-1b TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
