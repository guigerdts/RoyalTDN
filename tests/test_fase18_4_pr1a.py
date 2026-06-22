"""PR-1a Tests: explain() BaseStrategy + sma_crossover + bollinger_rsi + scanner base.

Verifies:
1. BaseStrategy.explain() default return contract
2. _compute_indicators() returns expected keys for sma + bollinger
3. explain() returns valid structure (indicators, conditions, signal)
4. explain()["signal"] matches generate_signal() for same data
5. gap_pct calculation is correct
6. Scanner scan(verbose=True) collects explanations
7. Backward compat: strategy without explain() doesn't crash scanner
"""

import sys
import os
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

from royaltdn.strategy.base import BaseStrategy, _calc_gap
from royaltdn.strategy.sma_strategy import SMAStrategy
from royaltdn.strategy.bollinger_rsi import BollingerRSIStrategy
from royaltdn.scanner.scanner import Scanner


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


# ── Mock strategy without explain() ──────────────────────────────────────

class MockStrategyNoExplain(BaseStrategy):
    @property
    def name(self) -> str:
        return "no_explain"

    def generate_signal(self, data: pd.DataFrame, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return None

    def get_parameters(self) -> Dict[str, Any]:
        return {}


class MockStrategyWithExplain(BaseStrategy):
    @property
    def name(self) -> str:
        return "with_explain"

    def generate_signal(self, data: pd.DataFrame, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return {"action": "BUY", "price": 100.0}

    def get_parameters(self) -> Dict[str, Any]:
        return {}

    def explain(self, data: pd.DataFrame, symbol: Optional[str] = None) -> Dict[str, Any]:
        return {"indicators": {"rsi": 30.0}, "conditions": [], "signal": self.generate_signal(data, symbol)}


# ── Test 1: BaseStrategy explain() default ───────────────────────────────

def test_base_strategy_explain_default():
    """BaseStrategy.explain() returns empty template."""
    s = MockStrategyWithExplain()
    result = BaseStrategy.explain(s, None)
    assert result == {"indicators": {}, "conditions": [], "signal": None}
    print("  ✅ BaseStrategy.explain() default return")


# ── Test 2: _calc_gap ────────────────────────────────────────────────────

def test_calc_gap_above_met():
    assert _calc_gap(110.0, 100.0, "above") == 0.0
    assert _calc_gap(100.0, 100.0, "above") == 0.0
    print("  ✅ _calc_gap above met")


def test_calc_gap_above_not_met():
    gap = _calc_gap(100.0, 110.0, "above")
    expected = abs((100.0 - 110.0) / 110.0) * 100
    assert abs(gap - expected) < 0.01
    print("  ✅ _calc_gap above not met")


def test_calc_gap_below_met():
    assert _calc_gap(90.0, 100.0, "below") == 0.0
    assert _calc_gap(100.0, 100.0, "below") == 0.0
    print("  ✅ _calc_gap below met")


def test_calc_gap_below_not_met():
    gap = _calc_gap(110.0, 100.0, "below")
    expected = abs((110.0 - 100.0) / 100.0) * 100
    assert abs(gap - expected) < 0.01
    print("  ✅ _calc_gap below not met")


# ── Test 3: sma_crossover explain() ──────────────────────────────────────

def test_sma_crossover_compute_indicators():
    s = SMAStrategy(sma_fast=5, sma_slow=20)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "sma_short" in ind
    assert "sma_long" in ind
    assert "sma_diff" in ind
    assert "signal_generated" in ind
    assert ind["sma_short"] is not None
    assert ind["sma_long"] is not None
    print("  ✅ sma_crossover _compute_indicators keys")


def test_sma_crossover_explain_structure():
    s = SMAStrategy(sma_fast=5, sma_slow=20)
    data = _uptrend_data(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert "sma_short" in result["indicators"]
    assert "sma_long" in result["indicators"]
    assert len(result["conditions"]) > 0
    for c in result["conditions"]:
        assert "name" in c
        assert "met" in c
        assert "value" in c
        assert "threshold" in c
        assert "gap_pct" in c
        assert "direction" in c
    print("  ✅ sma_crossover explain() structure")


def test_sma_crossover_signal_consistency():
    s = SMAStrategy(sma_fast=5, sma_slow=20)
    closes = [100.0] * 25 + [100 + i * 0.5 for i in range(35)]
    data = pd.DataFrame({"close": closes})
    gen_signal = s.generate_signal(data)
    exp_result = s.explain(data)
    if gen_signal is not None:
        assert exp_result["signal"] is not None
        assert exp_result["signal"]["action"] == gen_signal["action"]
        assert exp_result["signal"]["price"] == gen_signal["price"]
    print("  ✅ sma_crossover signal consistency")


def test_sma_crossover_gap_pct():
    s = SMAStrategy(sma_fast=5, sma_slow=10)
    closes = [100.0] * 10 + [100 + i * 2.0 for i in range(30)]
    data = pd.DataFrame({"close": closes})
    result = s.explain(data)
    assert len(result["conditions"]) > 0
    c = result["conditions"][0]
    assert c["met"] is True, f"Expected met=True, got {c}"
    assert c["gap_pct"] == 0.0, f"gap_pct should be 0.0 when met, got {c['gap_pct']}"

    closes2 = [100.0] * 10 + [100 - i * 2.0 for i in range(30)]
    data2 = pd.DataFrame({"close": closes2})
    result2 = s.explain(data2)
    assert len(result2["conditions"]) > 0
    c2 = result2["conditions"][0]
    assert c2["met"] is False, f"Expected met=False for downtrend, got {c2}"
    assert c2["gap_pct"] > 0.0, f"gap_pct should be > 0 when not met, got {c2['gap_pct']}"
    print("  ✅ sma_crossover gap_pct")


# ── Test 4: bollinger_rsi explain() ─────────────────────────────────────

def test_bollinger_rsi_compute_indicators():
    s = BollingerRSIStrategy(bb_period=10, rsi_period=10)
    data = _sample_ohlcv(60)
    ind = s._compute_indicators(data)
    assert "rsi" in ind
    assert "bb_upper" in ind
    assert "bb_middle" in ind
    assert "bb_lower" in ind
    assert "bb_position" in ind
    assert "bb_width" in ind
    print("  ✅ bollinger_rsi _compute_indicators keys")


def test_bollinger_rsi_explain_structure():
    s = BollingerRSIStrategy(bb_period=10, rsi_period=10)
    data = _sample_ohlcv(60)
    result = s.explain(data)
    assert "indicators" in result
    assert "conditions" in result
    assert "signal" in result
    assert len(result["conditions"]) > 0
    print("  ✅ bollinger_rsi explain() structure")


def test_bollinger_rsi_signal_consistency():
    s = BollingerRSIStrategy(bb_period=10, rsi_period=10, rsi_oversold=40)
    vals = [100.0] * 15 + [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 80, 70, 65]
    data = pd.DataFrame({"close": vals})
    gen_signal = s.generate_signal(data)
    exp_result = s.explain(data)
    if gen_signal is not None:
        assert exp_result["signal"] is not None
        assert exp_result["signal"]["action"] == gen_signal["action"]
    print("  ✅ bollinger_rsi signal consistency")


# ── Test 5: Scanner scan(verbose=True) ───────────────────────────────────

def test_scanner_verbose_true():
    scanner = _make_scanner_with_mocks()
    results = scanner.scan(verbose=True)
    assert len(scanner._last_explanations) > 0
    for strategy_name, symbol_dict in scanner._last_explanations.items():
        for symbol, explanation in symbol_dict.items():
            assert "indicators" in explanation
            assert "conditions" in explanation
            assert "signal" in explanation
    print("  ✅ scan(verbose=True) collects explanations")


def test_scanner_verbose_false():
    scanner = _make_scanner_with_mocks()
    results = scanner.scan(verbose=False)
    assert len(scanner._last_explanations) == 0
    print("  ✅ scan(verbose=False) no explanations")


def test_scanner_no_explain_guard():
    scanner = _make_scanner_with_mocks(include_no_explain=True)
    results = scanner.scan(verbose=True)
    assert len(scanner._last_explanations) == 3
    print("  ✅ scanner doesn't crash with no_explain strategy")


def _make_scanner_with_mocks(include_no_explain=False):
    from royaltdn.scanner.universe import AssetUniverse
    from royaltdn.scanner.filters import LiquidityFilter
    from alpaca.data.historical import StockHistoricalDataClient

    mock_universe = MagicMock(spec=AssetUniverse)
    mock_universe.get_symbols.return_value = ["SPY", "QQQ"]

    mock_filter = MagicMock(spec=LiquidityFilter)
    mock_filter.filter.return_value = ["SPY", "QQQ"]
    mock_filter.token_bucket = MagicMock()
    mock_filter.token_bucket.consume = MagicMock()

    mock_client = MagicMock(spec=StockHistoricalDataClient)
    mock_client.get_stock_bars = MagicMock()

    strategies = {
        "sma_crossover": SMAStrategy(sma_fast=5, sma_slow=20),
        "bollinger_rsi": BollingerRSIStrategy(bb_period=10, rsi_period=10),
    }
    if include_no_explain:
        strategies["no_explain"] = MockStrategyNoExplain()

    scanner = Scanner(
        universe=mock_universe,
        liquidity_filter=mock_filter,
        strategies=strategies,
        data_client=mock_client,
    )

    test_data = _sample_ohlcv(60)
    scanner._batch_get_symbol_data = MagicMock(
        return_value={"SPY": test_data, "QQQ": test_data}
    )

    return scanner


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("PR-1a — BaseStrategy + sma + bollinger + scanner verbose")
    print("=" * 50)

    test_base_strategy_explain_default()

    test_calc_gap_above_met()
    test_calc_gap_above_not_met()
    test_calc_gap_below_met()
    test_calc_gap_below_not_met()

    test_sma_crossover_compute_indicators()
    test_sma_crossover_explain_structure()
    test_sma_crossover_signal_consistency()
    test_sma_crossover_gap_pct()

    test_bollinger_rsi_compute_indicators()
    test_bollinger_rsi_explain_structure()
    test_bollinger_rsi_signal_consistency()

    test_scanner_verbose_true()
    test_scanner_verbose_false()
    test_scanner_no_explain_guard()

    print("\n✅ PR-1a TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
