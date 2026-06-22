"""PR-2 Tests: 5 scalping strategies explain().

Verifies:
1. _compute_indicators() returns expected keys for all 5 strategies
2. explain() returns valid structure (indicators, conditions, signal)
3. explain()["signal"] matches generate_signal() for same data
"""

import sys
import os
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from royaltdn.strategy.scalping_momentum import ScalpingMomentumStrategy
from royaltdn.strategy.scalping_breakout import ScalpingBreakoutStrategy
from royaltdn.strategy.scalping_reversion import ScalpingReversionStrategy
from royaltdn.strategy.scalping_orderflow import ScalpingOrderFlowStrategy
from royaltdn.strategy.scalping_spread import ScalpingSpreadStrategy


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


def _uptrend_data(n: int = 60) -> pd.DataFrame:
    return _sample_ohlcv(n, start_price=100.0, trend=0.3)


# ── Shared helpers ────────────────────────────────────────────────────────

def _assert_explain_structure(result: Dict[str, Any], name: str):
    assert "indicators" in result, f"{name}: missing indicators"
    assert "conditions" in result, f"{name}: missing conditions"
    assert "signal" in result, f"{name}: missing signal"
    for c in result["conditions"]:
        for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
            assert key in c, f"{name}: condition missing '{key}'"
    print(f"  ✅ {name} explain() structure")


def _assert_signal_consistency(s, data, name: str, symbol=None):
    gen = s.generate_signal(data, symbol)
    exp = s.explain(data, symbol)
    if gen is not None:
        assert exp["signal"] is not None, f"{name}: signal None but explain has signal"
        assert exp["signal"]["action"] == gen["action"], f"{name}: action mismatch"
        assert exp["signal"]["price"] == gen["price"], f"{name}: price mismatch"
    print(f"  ✅ {name} signal consistency")


# ── 1. scalping_momentum ─────────────────────────────────────────────────

def test_momentum_compute_indicators():
    s = ScalpingMomentumStrategy(momentum_period=5, min_momentum_pct=1.0)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "momentum_return" in ind
    assert "close" in ind
    assert "momentum_period" in ind
    assert "min_momentum_pct" in ind
    assert ind["momentum_return"] is not None
    print("  ✅ scalping_momentum _compute_indicators keys")


def test_momentum_explain_structure():
    s = ScalpingMomentumStrategy(momentum_period=5, min_momentum_pct=1.0)
    data = _uptrend_data(60)
    result = s.explain(data)
    _assert_explain_structure(result, "scalping_momentum")
    assert len(result["conditions"]) > 0


def test_momentum_signal_consistency():
    s = ScalpingMomentumStrategy(momentum_period=5, min_momentum_pct=0.5)
    vals = [100.0] + [100 + i * 0.5 for i in range(1, 15)]
    data = pd.DataFrame({"close": vals})
    _assert_signal_consistency(s, data, "scalping_momentum")


# ── 2. scalping_breakout ─────────────────────────────────────────────────

def test_breakout_compute_indicators():
    s = ScalpingBreakoutStrategy(period=10)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "close" in ind
    assert "recent_high" in ind
    assert "recent_low" in ind
    assert "atr" in ind
    assert "price_range" in ind
    assert ind["close"] is not None
    print("  ✅ scalping_breakout _compute_indicators keys")


def test_breakout_explain_structure():
    s = ScalpingBreakoutStrategy(period=10)
    data = _sample_ohlcv(60, start_price=100.0, trend=0.3)
    result = s.explain(data)
    _assert_explain_structure(result, "scalping_breakout")
    assert len(result["conditions"]) > 0


def test_breakout_signal_consistency():
    s = ScalpingBreakoutStrategy(period=10, multiplier=5.0)
    closes = [100.0] * 15 + [105.0, 110.0, 115.0, 120.0, 125.0]
    highs = [101.0] * 15 + [107.0, 112.0, 117.0, 122.0, 128.0]
    lows = [99.0] * 15 + [103.0, 108.0, 113.0, 118.0, 122.0]
    data = pd.DataFrame({"close": closes, "high": highs, "low": lows, "volume": [1000000] * 20})
    _assert_signal_consistency(s, data, "scalping_breakout")


# ── 3. scalping_reversion ────────────────────────────────────────────────

def test_reversion_compute_indicators():
    s = ScalpingReversionStrategy(period=10, deviation=2.0)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "close" in ind
    assert "sma" in ind
    assert "std" in ind
    assert "lower_band" in ind
    assert "upper_band" in ind
    assert ind["close"] is not None
    print("  ✅ scalping_reversion _compute_indicators keys")


def test_reversion_explain_structure():
    s = ScalpingReversionStrategy(period=10, deviation=2.0)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    _assert_explain_structure(result, "scalping_reversion")
    assert len(result["conditions"]) > 0


def test_reversion_signal_consistency():
    s = ScalpingReversionStrategy(period=10, deviation=10.0)
    vals = [100.0] * 15 + [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 80, 70, 65]
    data = pd.DataFrame({"close": vals})
    _assert_signal_consistency(s, data, "scalping_reversion")


# ── 4. scalping_orderflow ────────────────────────────────────────────────

def test_orderflow_compute_indicators():
    s = ScalpingOrderFlowStrategy(volume_threshold=100_000, volume_period=10)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "volume_ratio" in ind
    assert "last_volume" in ind
    assert "avg_volume" in ind
    assert "close" in ind
    assert "prev_close" in ind
    assert ind["volume_ratio"] is not None
    print("  ✅ scalping_orderflow _compute_indicators keys")


def test_orderflow_explain_structure():
    s = ScalpingOrderFlowStrategy(volume_threshold=100_000, volume_period=10)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    _assert_explain_structure(result, "scalping_orderflow")
    assert len(result["conditions"]) > 0


def test_orderflow_signal_consistency():
    s = ScalpingOrderFlowStrategy(volume_threshold=100_000, imbalance_ratio=0.5, volume_period=5)
    vals = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    data = pd.DataFrame({
        "close": vals,
        "volume": [500_000, 500_000, 500_000, 500_000, 500_000, 2_000_000, 2_000_000],
    })
    _assert_signal_consistency(s, data, "scalping_orderflow")


# ── 5. scalping_spread ───────────────────────────────────────────────────

def test_spread_compute_indicators():
    s = ScalpingSpreadStrategy(spread_period=10, spread_threshold=2.0)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "range" in ind
    assert "avg_range" in ind
    assert "range_ratio" in ind
    assert "close" in ind
    assert "open" in ind
    assert ind["range"] is not None
    print("  ✅ scalping_spread _compute_indicators keys")


def test_spread_explain_structure():
    s = ScalpingSpreadStrategy(spread_period=10, spread_threshold=2.0)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    _assert_explain_structure(result, "scalping_spread")
    assert len(result["conditions"]) > 0


def test_spread_signal_consistency():
    s = ScalpingSpreadStrategy(spread_period=5, spread_threshold=0.5)
    vals = [100.0] * 10 + [105.0, 110.0, 115.0, 120.0, 125.0]
    data = pd.DataFrame({
        "close": vals,
        "open": [100.0] * 15,
        "high": [v + 5 for v in vals],
        "low": [v - 1 for v in vals],
    })
    _assert_signal_consistency(s, data, "scalping_spread")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("PR-2 — 5 Scalping Strategies explain()")
    print("=" * 50)

    # 1. scalping_momentum
    test_momentum_compute_indicators()
    test_momentum_explain_structure()
    test_momentum_signal_consistency()

    # 2. scalping_breakout
    test_breakout_compute_indicators()
    test_breakout_explain_structure()
    test_breakout_signal_consistency()

    # 3. scalping_reversion
    test_reversion_compute_indicators()
    test_reversion_explain_structure()
    test_reversion_signal_consistency()

    # 4. scalping_orderflow
    test_orderflow_compute_indicators()
    test_orderflow_explain_structure()
    test_orderflow_signal_consistency()

    # 5. scalping_spread
    test_spread_compute_indicators()
    test_spread_explain_structure()
    test_spread_signal_consistency()

    print("\n✅ PR-2 TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
