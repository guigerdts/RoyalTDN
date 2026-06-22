"""RoyalTDN — Tests for FASE 18.3: 12 nuevas estrategias (PR 3).

Covers 13 strategies total — 5 scalping + 5 intraday + 3 swing.

Each test is parametrized across all strategies to ensure:
  - name property
  - category correctness
  - get_parameters(None) returns dual crypto_*/stocks_* prefixes
  - get_parameters(symbol) returns per-profile params
  - validate() with defaults
  - generate_signal with insufficient data returns None
  - generate_signal does NOT mutate self.* params

Usage:
    pytest tests/test_fase18_3_doce_estrategias.py -v
"""

from typing import Any, Dict, Optional

import pandas as pd
import pytest

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.scalping_momentum import ScalpingMomentumStrategy
from royaltdn.strategy.scalping_breakout import ScalpingBreakoutStrategy
from royaltdn.strategy.scalping_reversion import ScalpingReversionStrategy
from royaltdn.strategy.scalping_orderflow import ScalpingOrderFlowStrategy
from royaltdn.strategy.scalping_spread import ScalpingSpreadStrategy
from royaltdn.strategy.intraday_trend import IntradayTrendStrategy
from royaltdn.strategy.intraday_vwap import IntradayVWAPStrategy
from royaltdn.strategy.intraday_volume_breakout import IntradayVolumeBreakoutStrategy
from royaltdn.strategy.intraday_support_resistance import IntradaySupportResistanceStrategy
from royaltdn.strategy.intraday_macd_divergence import IntradayMACDDivergenceStrategy
from royaltdn.strategy.swing_trend_following import SwingTrendFollowingStrategy
from royaltdn.strategy.swing_reversion import SwingReversionStrategy
from royaltdn.strategy.swing_breakout import SwingBreakoutStrategy


# ── Helpers ──────────────────────────────────────────────────────────────

StrategyFactory = Any  # a strategy class, not instance


def _identity_strategy() -> BaseStrategy:
    """Return a no-op strategy for BaseStrategy-level tests."""
    class _Identity(BaseStrategy):
        @property
        def name(self) -> str:
            return "identity"
        def generate_signal(
            self, data: pd.DataFrame, symbol: Optional[str] = None,
        ) -> Optional[Dict[str, Any]]:
            return None
    return _Identity()


# ── Strategy catalog ─────────────────────────────────────────────────────

STRATEGIES: Dict[str, StrategyFactory] = {
    # scalping (5)
    "scalping_momentum": ScalpingMomentumStrategy,
    "scalping_breakout": ScalpingBreakoutStrategy,
    "scalping_reversion": ScalpingReversionStrategy,
    "scalping_orderflow": ScalpingOrderFlowStrategy,
    "scalping_spread": ScalpingSpreadStrategy,
    # intraday (5)
    "intraday_trend": IntradayTrendStrategy,
    "intraday_vwap": IntradayVWAPStrategy,
    "intraday_volume_breakout": IntradayVolumeBreakoutStrategy,
    "intraday_support_resistance": IntradaySupportResistanceStrategy,
    "intraday_macd_divergence": IntradayMACDDivergenceStrategy,
    # swing (3)
    "swing_trend_following": SwingTrendFollowingStrategy,
    "swing_reversion": SwingReversionStrategy,
    "swing_breakout": SwingBreakoutStrategy,
}

EXPECTED_NAMES = list(STRATEGIES.keys())

# Map strategy name → expected category
EXPECTED_CATEGORIES: Dict[str, str] = {
    "scalping_momentum": "scalping",
    "scalping_breakout": "scalping",
    "scalping_reversion": "scalping",
    "scalping_orderflow": "scalping",
    "scalping_spread": "scalping",
    "intraday_trend": "intraday",
    "intraday_vwap": "intraday",
    "intraday_volume_breakout": "intraday",
    "intraday_support_resistance": "intraday",
    "intraday_macd_divergence": "intraday",
    "swing_trend_following": "swing",
    "swing_reversion": "swing",
    "swing_breakout": "swing",
}


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFase183Name:
    """Task C.1 — name property matches expected."""

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_name(self, name: str) -> None:
        factory = STRATEGIES[name]
        strategy = factory()
        assert strategy.name == name


class TestFase183Category:
    """Task C.2 — each strategy has correct category."""

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_category(self, name: str) -> None:
        factory = STRATEGIES[name]
        strategy = factory()
        assert strategy.category == EXPECTED_CATEGORIES[name]


class TestFase183DualPrefixes:
    """Task C.3 — get_parameters(None) has crypto_*/stocks_* keys."""

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_get_parameters_has_dual_prefixes(self, name: str) -> None:
        factory = STRATEGIES[name]
        strategy = factory()
        params = strategy.get_parameters(None)
        crypto_keys = [k for k in params if k.startswith("crypto_")]
        stocks_keys = [k for k in params if k.startswith("stocks_")]
        assert crypto_keys, f"No crypto_* keys in {name}"
        assert stocks_keys, f"No stocks_* keys in {name}"
        # Every key should be prefixed (no bare keys)
        bare = [k for k in params if not k.startswith(("crypto_", "stocks_"))]
        assert not bare, f"Bare keys without prefix in {name}: {bare}"


class TestFase183Parameters:
    """Task C.4 — get_parameters('BTCUSDT') returns crypto profile."""

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_get_parameters_crypto(self, name: str) -> None:
        factory = STRATEGIES[name]
        strategy = factory()
        params = strategy.get_parameters("BTCUSDT")
        assert "timeframe" in params
        # No prefixed keys when resolved
        crypto_prefixed = [k for k in params if k.startswith("crypto_")]
        assert not crypto_prefixed, (
            f"get_parameters('BTCUSDT') returned prefixed keys in {name}: {crypto_prefixed}"
        )

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_get_parameters_stock(self, name: str) -> None:
        """Task C.5 — get_parameters('AAPL') returns stocks profile."""
        factory = STRATEGIES[name]
        strategy = factory()
        params = strategy.get_parameters("AAPL")
        assert "timeframe" in params
        stocks_prefixed = [k for k in params if k.startswith("stocks_")]
        assert not stocks_prefixed, (
            f"get_parameters('AAPL') returned prefixed keys in {name}: {stocks_prefixed}"
        )


class TestFase183Validate:
    """Task C.6 — strategy with defaults validates True."""

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_validate_ok(self, name: str) -> None:
        factory = STRATEGIES[name]
        strategy = factory()
        assert strategy.validate() is True


class TestFase183InsufficientData:
    """Task C.7 — data too short returns None."""

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_generate_signal_insufficient_data(self, name: str) -> None:
        factory = STRATEGIES[name]
        strategy = factory()
        df = pd.DataFrame({"close": [1.0, 2.0]})
        result = strategy.generate_signal(df)
        assert result is None


class TestFase183SelfParamsNotMutated:
    """Task C.8 — generate_signal with symbol doesn't change self.*."""

    @pytest.mark.parametrize("name", EXPECTED_NAMES)
    def test_self_params_not_mutated(self, name: str) -> None:
        factory = STRATEGIES[name]
        strategy = factory()

        # Snapshot initial params (excluding BaseStrategy attrs)
        initial = {}
        for attr, val in strategy.__dict__.items():
            if attr.startswith("_") or attr in ("timeframe", "_category"):
                continue
            initial[attr] = val

        n = 50
        df = pd.DataFrame({
            "close": [float(i) for i in range(n, 0, -1)],
            "high": [float(i + 1) for i in range(n, 0, -1)],
            "low": [float(i - 1) for i in range(n, 0, -1)],
            "volume": [1000.0 + i for i in range(n)],
        })
        strategy.generate_signal(df, symbol="BTCUSDT")

        # Assert no self.* params changed
        for attr, val in initial.items():
            assert getattr(strategy, attr) == val, (
                f"{name}.{attr} mutated from {val} to {getattr(strategy, attr)}"
            )
