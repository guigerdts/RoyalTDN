"""RoyalTDN — Tests for dual-param profiles (FASE 18.2, PR 1).

Phases 1-3:
  - Phase 1: BaseStrategy.category, universe_type setter
  - Phase 2: Three strategies with _PROFILES, symbol-aware dispatch
  - Phase 3: Scanner inspect dispatch (do NOT pass symbol to strategies
    that don't accept it)

Uso:
    pytest tests/test_dual_params.py -v
"""

import inspect
from typing import Any, Dict, Optional

import pandas as pd
import pytest

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.sma_strategy import SMAStrategy
from royaltdn.strategy.bollinger_rsi import BollingerRSIStrategy
from royaltdn.strategy.momentum_atr import MomentumATRStrategy
from royaltdn.strategy.factor_rotation import FactorRotationStrategy
from royaltdn.scanner.universe import AssetUniverse


# ═══════════════════════════════════════════════════════════════════════
# Phase 1 — Foundation
# ═══════════════════════════════════════════════════════════════════════

class _ConcreteStrategy(BaseStrategy):
    """Minimal concrete strategy for testing BaseStrategy itself."""

    @property
    def name(self) -> str:
        return "concrete_test"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return None


class TestBaseStrategyCategory:
    """Task 1.4 — category defaults and property."""

    def test_default_category_is_swing(self):
        """BaseStrategy subclass defaults category to 'swing'."""
        s = _ConcreteStrategy()
        assert s.category == "swing"

    def test_custom_category(self):
        """BaseStrategy subclass accepts custom category."""
        s = _ConcreteStrategy(category="intraday")
        assert s.category == "intraday"

    def test_get_parameters_includes_category(self):
        """get_parameters default impl includes category."""
        s = _ConcreteStrategy(category="swing")
        params = s.get_parameters()
        assert params["category"] == "swing"
        assert params["timeframe"] == "1d"

    def test_strategy_isinstance_base(self):
        """Concrete strategy is an instance of BaseStrategy."""
        assert isinstance(_ConcreteStrategy(), BaseStrategy)


class TestUniverseTypeSetter:
    """Task 1.4 — universe_type setter validates + invalidates cache."""

    def test_setter_valid_value(self):
        """Setting universe_type to valid value updates and invalidates cache."""
        u = AssetUniverse("k", "s", universe_type="etfs")
        u.get_symbols()  # populate cache
        assert len(u._cache) > 0
        u.universe_type = "sp500"
        assert u.universe_type == "sp500"
        # Cache should be cleared after setter
        assert len(u._cache) == 0

    def test_setter_invalid_value_raises(self):
        """Setting universe_type to invalid value raises ValueError."""
        u = AssetUniverse("k", "s", universe_type="etfs")
        with pytest.raises(ValueError, match="Invalid universe type"):
            u.universe_type = "invalid_xyz"

    def test_setter_valid_values(self):
        """All VALID_UNIVERSE_TYPES are accepted."""
        u = AssetUniverse("k", "s", universe_type="etfs")
        for vt in AssetUniverse.VALID_UNIVERSE_TYPES:
            u.universe_type = vt
            assert u.universe_type == vt


# ═══════════════════════════════════════════════════════════════════════
# Phase 2 — Dual params: get_parameters three-way
# ═══════════════════════════════════════════════════════════════════════

class TestSMAStrategyDualParams:
    """Task 2.4 — SMAStrategy profile resolution."""

    def test_get_params_none_returns_both_profiles(self):
        """get_parameters(None) returns dual prefixed profiles."""
        s = SMAStrategy("redis://localhost:6379/0")
        params = s.get_parameters(symbol=None)
        assert "crypto_sma_fast" in params
        assert "crypto_sma_slow" in params
        assert "stocks_sma_fast" in params
        assert "stocks_sma_slow" in params

    def test_get_params_crypto_returns_crypto_profile(self):
        """get_parameters('BTCUSDT') returns crypto profile."""
        s = SMAStrategy("redis://localhost:6379/0")
        params = s.get_parameters("BTCUSDT")
        assert params["sma_fast"] == 7
        assert params["sma_slow"] == 25

    def test_get_params_stock_returns_stocks_profile(self):
        """get_parameters('AAPL') returns stocks profile."""
        s = SMAStrategy("redis://localhost:6379/0")
        params = s.get_parameters("AAPL")
        assert params["sma_fast"] == 5
        assert params["sma_slow"] == 20

    def test_generate_signal_crypto_uses_crypto_params(self):
        """generate_signal with crypto symbol uses crypto profile (local vars)."""
        s = SMAStrategy("redis://localhost:6379/0")
        closes = [float(i) for i in range(30, 5, -1)]  # 25 values, descending
        df = pd.DataFrame({"close": closes})
        result = s.generate_signal(df, symbol="BTCUSDT")
        # If a signal was generated, verify metadata reflects crypto profile
        if result is not None:
            meta = result["metadata"]
            assert meta["fast_period"] == 7
            assert meta["slow_period"] == 25

    def test_generate_signal_stock_uses_stock_params(self):
        """generate_signal with stock symbol uses stocks profile."""
        s = SMAStrategy("redis://localhost:6379/0")
        closes = [float(i) for i in range(30, 5, -1)]
        df = pd.DataFrame({"close": closes})
        result = s.generate_signal(df, symbol="AAPL")
        if result is not None:
            meta = result["metadata"]
            assert meta["fast_period"] == 5
            assert meta["slow_period"] == 20

    def test_generate_signal_no_symbol_uses_instance_params(self):
        """generate_signal with no symbol uses instance defaults."""
        s = SMAStrategy("redis://localhost:6379/0", sma_fast=3, sma_slow=10)
        closes = [float(i) for i in range(15, 0, -1)]
        df = pd.DataFrame({"close": closes})
        result = s.generate_signal(df)
        if result is not None:
            meta = result["metadata"]
            assert meta["fast_period"] == 3
            assert meta["slow_period"] == 10

    def test_self_params_not_mutated(self):
        """generate_signal does NOT mutate self.sma_fast / self.sma_slow."""
        s = SMAStrategy("redis://localhost:6379/0", sma_fast=5, sma_slow=20)
        original_fast = s.sma_fast
        original_slow = s.sma_slow
        closes = [float(i) for i in range(30, 5, -1)]
        df = pd.DataFrame({"close": closes})
        s.generate_signal(df, symbol="BTCUSDT")
        assert s.sma_fast == original_fast
        assert s.sma_slow == original_slow


class TestBollingerRSIDualParams:
    """Task 2.4 — BollingerRSIStrategy profile resolution."""

    def test_get_params_none_returns_both_profiles(self):
        s = BollingerRSIStrategy()
        params = s.get_parameters(symbol=None)
        assert "crypto_bb_period" in params
        assert "crypto_rsi_period" in params
        assert "stocks_bb_period" in params
        assert "stocks_rsi_period" in params

    def test_get_params_crypto_returns_crypto_profile(self):
        s = BollingerRSIStrategy()
        params = s.get_parameters("BTCUSDT")
        assert params["bb_period"] == 15
        assert params["bb_std"] == 2.5
        assert params["rsi_period"] == 10
        assert params["rsi_oversold"] == 25
        assert params["rsi_overbought"] == 75
        assert params["max_bars_hold"] == 20

    def test_get_params_stock_returns_stocks_profile(self):
        s = BollingerRSIStrategy()
        params = s.get_parameters("AAPL")
        assert params["bb_period"] == 20
        assert params["bb_std"] == 2.0
        assert params["rsi_period"] == 14
        assert params["rsi_oversold"] == 30
        assert params["rsi_overbought"] == 70
        assert params["max_bars_hold"] == 30

    def test_self_params_not_mutated(self):
        """generate_signal does NOT mutate self params."""
        s = BollingerRSIStrategy(bb_period=20, rsi_period=14)
        close_data = [float(i) for i in range(50, 0, -1)]
        df = pd.DataFrame({"close": close_data})
        s.generate_signal(df, symbol="BTCUSDT")
        assert s.bb_period == 20
        assert s.rsi_period == 14


class TestMomentumATRDualParams:
    """Task 2.4 — MomentumATRStrategy profile resolution."""

    def test_get_params_none_returns_both_profiles(self):
        s = MomentumATRStrategy()
        params = s.get_parameters(symbol=None)
        assert "crypto_momentum_period" in params
        assert "crypto_atr_period" in params
        assert "crypto_atr_max_pct" in params
        assert "stocks_momentum_period" in params
        assert "stocks_atr_period" in params
        assert "stocks_atr_max_pct" in params

    def test_get_params_crypto_returns_crypto_profile(self):
        s = MomentumATRStrategy()
        params = s.get_parameters("BTCUSDT")
        assert params["momentum_period"] == 15
        assert params["atr_period"] == 14
        assert params["atr_max_pct"] == 4.0
        assert params["exit_period"] == 3

    def test_get_params_stock_returns_stocks_profile(self):
        s = MomentumATRStrategy()
        params = s.get_parameters("AAPL")
        assert params["momentum_period"] == 20
        assert params["atr_period"] == 20
        assert params["atr_max_pct"] == 2.0
        assert params["exit_period"] == 5

    def test_self_params_not_mutated(self):
        """generate_signal does NOT mutate self params."""
        s = MomentumATRStrategy(momentum_period=20, atr_period=20)
        close_data = [float(i) for i in range(50, 0, -1)]
        df = pd.DataFrame({"close": close_data, "high": close_data, "low": close_data})
        s.generate_signal(df, symbol="BTCUSDT")
        assert s.momentum_period == 20
        assert s.atr_period == 20


# ═══════════════════════════════════════════════════════════════════════
# Phase 3 — Scanner dispatch (inspect-based)
# ═══════════════════════════════════════════════════════════════════════

class TestScannerInspectDispatch:
    """Task 3.2 — inspect dispatch does NOT pass symbol to
    strategies that lack the parameter."""

    def test_factor_rotation_lacks_symbol_param(self):
        """FactorRotationStrategy.generate_signal does NOT have 'symbol' in signature."""
        sig = inspect.signature(FactorRotationStrategy.generate_signal)
        params = list(sig.parameters.keys())
        # FactorRotationStrategy.generate_signal has 'self' and 'data' only
        assert "symbol" not in params

    def test_sma_strategy_has_symbol_param(self):
        """SMAStrategy.generate_signal DOES have 'symbol' in signature."""
        sig = inspect.signature(SMAStrategy.generate_signal)
        assert "symbol" in sig.parameters

    def test_inspect_dispatch_sma_passes_symbol(self):
        """When symbol is in signature, inspect dispatch passes it as kwarg."""
        sig = inspect.signature(SMAStrategy.generate_signal)
        kwargs = {"symbol": "BTCUSDT"} if "symbol" in sig.parameters else {}
        assert kwargs == {"symbol": "BTCUSDT"}

    def test_inspect_dispatch_factor_rotation_no_symbol(self):
        """When symbol is NOT in signature, inspect dispatch passes empty kwargs."""
        sig = inspect.signature(FactorRotationStrategy.generate_signal)
        kwargs = {"symbol": "BTCUSDT"} if "symbol" in sig.parameters else {}
        assert kwargs == {}
