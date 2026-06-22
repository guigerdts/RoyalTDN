"""PR-3b Tests: swing_reversion explain() + all-16 iteration test.

Tests:
1. swing_reversion: _compute_indicators, explain_structure, signal_consistency
2. all-16: every strategy has working _compute_indicators, explain(), generate_signal()
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from royaltdn.strategy.bollinger_rsi import BollingerRSIStrategy
from royaltdn.strategy.intraday_macd_divergence import IntradayMACDDivergenceStrategy
from royaltdn.strategy.intraday_support_resistance import IntradaySupportResistanceStrategy
from royaltdn.strategy.intraday_trend import IntradayTrendStrategy
from royaltdn.strategy.intraday_volume_breakout import IntradayVolumeBreakoutStrategy
from royaltdn.strategy.intraday_vwap import IntradayVWAPStrategy
from royaltdn.strategy.momentum_atr import MomentumATRStrategy
from royaltdn.strategy.scalping_breakout import ScalpingBreakoutStrategy
from royaltdn.strategy.scalping_momentum import ScalpingMomentumStrategy
from royaltdn.strategy.scalping_orderflow import ScalpingOrderFlowStrategy
from royaltdn.strategy.scalping_reversion import ScalpingReversionStrategy
from royaltdn.strategy.scalping_spread import ScalpingSpreadStrategy
from royaltdn.strategy.sma_strategy import SMAStrategy
from royaltdn.strategy.swing_breakout import SwingBreakoutStrategy
from royaltdn.strategy.swing_reversion import SwingReversionStrategy
from royaltdn.strategy.swing_trend_following import SwingTrendFollowingStrategy


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


# ── Task 1: SwingReversion explain() ─────────────────────────────────────

def test_reversion_compute_indicators():
    s = SwingReversionStrategy(lookback_period=20, z_score_threshold=2.0)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    for key in ("z_score", "sma", "std", "close", "z_score_threshold", "lookback_period"):
        assert key in ind, f"Missing key: {key}"
        assert ind[key] is not None, f"None value: {key}"
    print("  ✅ swing_reversion _compute_indicators keys")


def test_reversion_explain_structure():
    s = SwingReversionStrategy(lookback_period=20, z_score_threshold=2.0)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    for c in result["conditions"]:
        for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
            assert key in c, f"Missing condition key: {key}"
    print("  ✅ swing_reversion explain() structure")


def test_reversion_signal_consistency():
    s = SwingReversionStrategy(lookback_period=20, z_score_threshold=2.0)
    data = _sample_ohlcv(60)
    gen = s.generate_signal(data)
    exp = s.explain(data)
    assert exp["signal"] == gen
    print("  ✅ swing_reversion signal consistency")


# ── Task 2: All-16 iteration test ────────────────────────────────────────

ALL_STRATEGIES = [
    ("bollinger_rsi", BollingerRSIStrategy, {"bb_period": 20, "rsi_period": 14}),
    ("sma_crossover", SMAStrategy, {"sma_fast": 5, "sma_slow": 20}),
    ("momentum_atr", MomentumATRStrategy, {"momentum_period": 20, "atr_period": 20}),
    ("swing_trend_following", SwingTrendFollowingStrategy, {"fast_ema": 10, "slow_ema": 30}),
    ("swing_breakout", SwingBreakoutStrategy, {"breakout_period": 30}),
    ("swing_reversion", SwingReversionStrategy, {"lookback_period": 20, "z_score_threshold": 2.0}),
    ("intraday_vwap", IntradayVWAPStrategy, {"vwap_period": 10}),
    ("intraday_volume_breakout", IntradayVolumeBreakoutStrategy, {"breakout_period": 10}),
    ("intraday_trend", IntradayTrendStrategy, {"ema_fast": 5, "ema_slow": 10}),
    ("intraday_support_resistance", IntradaySupportResistanceStrategy, {"sr_period": 10}),
    ("intraday_macd_divergence", IntradayMACDDivergenceStrategy,
     {"fast_period": 5, "slow_period": 10, "signal_period": 5}),
    ("scalping_breakout", ScalpingBreakoutStrategy, {"period": 20, "multiplier": 1.5}),
    ("scalping_momentum", ScalpingMomentumStrategy,
     {"momentum_period": 5, "min_momentum_pct": 1.0}),
    ("scalping_orderflow", ScalpingOrderFlowStrategy,
     {"volume_threshold": 500_000, "imbalance_ratio": 1.5}),
    ("scalping_reversion", ScalpingReversionStrategy, {"period": 14, "deviation": 1.5}),
    ("scalping_spread", ScalpingSpreadStrategy, {"spread_period": 20, "spread_threshold": 1.5}),
]


def test_all_16_strategies_have_explain():
    """Proves every strategy has working explain() with valid structure."""
    data = _sample_ohlcv(60)
    passed = 0
    failed = []

    for name, cls, params in ALL_STRATEGIES:
        try:
            strat = cls(**params)
            ind = strat._compute_indicators(data)
            assert isinstance(ind, dict), f"{name}: _compute_indicators not dict"
            assert len(ind) > 0, f"{name}: _compute_indicators empty"

            result = strat.explain(data)
            assert "indicators" in result, f"{name}: missing indicators"
            assert "conditions" in result, f"{name}: missing conditions"
            assert "signal" in result, f"{name}: missing signal"
            assert isinstance(result["indicators"], dict)
            assert isinstance(result["conditions"], list)
            for c in result["conditions"]:
                for key in ("name", "met", "value", "threshold", "gap_pct", "direction"):
                    assert key in c, f"{name}: condition missing {key}"

            gen = strat.generate_signal(data)
            assert result["signal"] == gen, f"{name}: signal mismatch"

            passed += 1
        except Exception as e:
            failed.append(f"{name}: {e}")

    total = len(ALL_STRATEGIES)
    print(f"\n  All-16: {passed}/{total} passed, {len(failed)} failed")
    for f in failed:
        print(f"    FAIL: {f}")
    assert len(failed) == 0, f"Failed strategies: {failed}"


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("PR-3b — swing_reversion explain() + All-16")
    print("=" * 50)

    # Task 1
    test_reversion_compute_indicators()
    test_reversion_explain_structure()
    test_reversion_signal_consistency()

    # Task 2
    test_all_16_strategies_have_explain()

    print("\n✅ PR-3b TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
