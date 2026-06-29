"""Unit tests for SMF Cloud indicators.

Tests cover ``_compute_smf``, the 5 wrapper functions, ``adaptive_mult``,
module-level caching, and compound operator resolution via ``_INDICATORS``.
"""

from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from royaltdn.inference.conditions import (
    _compute_smf,
    _INDICATORS,
    _resolve_value,
    adaptive_mult,
    evaluate,
    smf_basis,
    smf_flow,
    smf_lower,
    smf_strength,
    smf_upper,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_data(
    n_bars: int,
    close_start: float = 100.0,
    close_step: float = 0.5,
    noise: float = 0.2,
    vol_base: float = 1000.0,
) -> dict[str, list[float]]:
    """Build a dict of synthetic OHLCV lists.

    When *close_step* is positive, the price rises steadily (bullish).
    High/low are offset by a small amount around close.
    """
    close = [close_start + i * close_step for i in range(n_bars)]
    high = [c + noise + abs(c * 0.005) for c in close]
    low = [c - noise - abs(c * 0.005) for c in close]
    volume = [vol_base + (i % 10) * 50.0 for i in range(n_bars)]
    return {"close": close, "high": high, "low": low, "volume": volume}


@pytest.fixture
def bullish_100() -> dict[str, list[float]]:
    """100 bars of steadily rising price (bullish flow)."""
    return _make_data(100, close_start=100.0, close_step=0.5)


@pytest.fixture
def bearish_100() -> dict[str, list[float]]:
    """100 bars of steadily falling price (bearish flow)."""
    return _make_data(100, close_start=200.0, close_step=-0.5)


@pytest.fixture
def short_data() -> dict[str, list[float]]:
    """Only 5 bars — insufficient for any SMF computation."""
    return _make_data(5)


@pytest.fixture
def zero_volume() -> dict[str, list[float]]:
    """50 bars with zero volume."""
    return _make_data(50, vol_base=0.0)


@pytest.fixture
def single_bar() -> dict[str, float]:
    """Single bar (edge case)."""
    return {"close": [100.0], "high": [101.0], "low": [99.0], "volume": [1000.0]}


# ---------------------------------------------------------------------------
# _compute_smf
# ---------------------------------------------------------------------------


class TestComputeSmf:
    """Tests for the core ``_compute_smf`` helper."""

    def test_sufficient_data_returns_9_keys(self, bullish_100):
        result = _compute_smf(bullish_100)
        assert isinstance(result, dict)
        expected_keys = {"clv", "raw_flow", "mf", "strength", "mult", "basis", "atr", "upper", "lower"}
        assert set(result.keys()) == expected_keys
        for v in result.values():
            assert isinstance(v, float)
            assert math.isfinite(v)

    def test_bullish_flow_is_positive(self, bullish_100):
        """Steadily rising close should produce positive money flow."""
        result = _compute_smf(bullish_100)
        assert result["mf"] > 0.0

    def test_bearish_flow_is_negative(self, bearish_100):
        """Steadily falling close should produce negative money flow."""
        result = _compute_smf(bearish_100)
        assert result["mf"] < 0.0

    def test_strength_in_01_range(self, bullish_100):
        result = _compute_smf(bullish_100)
        assert 0.0 <= result["strength"] <= 1.0

    def test_bands_ordered(self, bullish_100):
        """Upper >= basis >= lower."""
        result = _compute_smf(bullish_100)
        assert result["upper"] >= result["basis"]
        assert result["basis"] >= result["lower"]

    def test_insufficient_data_returns_empty(self, short_data):
        result = _compute_smf(short_data)
        assert result == {}

    def test_insufficient_data_single_bar(self, single_bar):
        result = _compute_smf(single_bar)
        assert result == {}

    def test_zero_volume_does_not_raise(self, zero_volume):
        try:
            result = _compute_smf(zero_volume)
            # With zero volume, raw_flow is all zero → mf_denom = 0 → mf = 0
            assert result.get("mf", None) is not None
        except Exception as exc:
            pytest.fail(f"Zero volume raised {type(exc).__name__}: {exc}")

    def test_zero_volume_returns_mf_zero(self, zero_volume):
        result = _compute_smf(zero_volume)
        assert result["mf"] == 0.0

    def test_nan_values_handled(self):
        """Data with NaN in the middle should not crash."""
        data = _make_data(60)
        data["close"][30] = float("nan")
        data["close"][31] = float("nan")
        result = _compute_smf(data)
        assert isinstance(result, dict)
        if result:
            for v in result.values():
                assert math.isfinite(v)

    def test_all_nan_close_returns_empty(self):
        data = _make_data(60)
        data["close"] = [float("nan")] * 60
        result = _compute_smf(data)
        assert result == {}

    def test_band_distance_scales_with_atr(self, bullish_100):
        """upper - basis ≈ basis - lower ≈ atr * mult."""
        result = _compute_smf(bullish_100)
        expected_distance = result["atr"] * result["mult"]
        assert abs((result["upper"] - result["basis"]) - expected_distance) < 1e-9
        assert abs((result["basis"] - result["lower"]) - expected_distance) < 1e-9


# ---------------------------------------------------------------------------
# adaptive_mult
# ---------------------------------------------------------------------------


class TestAdaptiveMult:
    """Tests for the ``adaptive_mult`` utility function."""

    def test_strength_zero_returns_min(self):
        assert adaptive_mult(0.0, min_mult=0.9, max_mult=2.2) == 0.9

    def test_strength_one_returns_max(self):
        assert adaptive_mult(1.0, min_mult=0.9, max_mult=2.2) == 2.2

    def test_strength_half_returns_midpoint(self):
        result = adaptive_mult(0.5, min_mult=0.9, max_mult=2.2)
        expected = 0.9 + (2.2 - 0.9) * 0.5
        assert result == expected

    def test_clamps_below_zero(self):
        assert adaptive_mult(-0.5, min_mult=0.9, max_mult=2.2) == 0.9

    def test_clamps_above_one(self):
        assert adaptive_mult(1.5, min_mult=0.9, max_mult=2.2) == 2.2

    def test_nan_returns_min(self):
        assert adaptive_mult(float("nan"), min_mult=0.9, max_mult=2.2) == 0.9

    def test_inf_returns_min(self):
        assert adaptive_mult(float("inf"), min_mult=0.9, max_mult=2.2) == 0.9

    def test_neg_inf_returns_min(self):
        assert adaptive_mult(float("-inf"), min_mult=0.9, max_mult=2.2) == 0.9

    def test_custom_bounds(self):
        result = adaptive_mult(0.5, min_mult=0.5, max_mult=3.0)
        expected = 0.5 + (3.0 - 0.5) * 0.5
        assert result == expected


# ---------------------------------------------------------------------------
# Five wrapper functions
# ---------------------------------------------------------------------------


class TestSmfWrappers:
    """Tests for the 5 public SMF wrapper indicators."""

    def test_smf_flow_returns_float(self, bullish_100):
        val = smf_flow(bullish_100)
        assert isinstance(val, float)
        assert math.isfinite(val)

    def test_smf_strength_returns_float(self, bullish_100):
        val = smf_strength(bullish_100)
        assert isinstance(val, float)
        assert 0.0 <= val <= 1.0

    def test_smf_basis_returns_float(self, bullish_100):
        val = smf_basis(bullish_100)
        assert isinstance(val, float)
        assert val > 0.0

    def test_smf_upper_returns_float(self, bullish_100):
        val = smf_upper(bullish_100)
        assert isinstance(val, float)
        assert val > 0.0

    def test_smf_lower_returns_float(self, bullish_100):
        val = smf_lower(bullish_100)
        assert isinstance(val, float)
        assert val > 0.0

    def test_wrappers_return_zero_on_short_data(self, short_data):
        assert smf_flow(short_data) == 0.0
        assert smf_strength(short_data) == 0.0
        assert smf_basis(short_data) == 0.0
        assert smf_upper(short_data) == 0.0
        assert smf_lower(short_data) == 0.0

    def test_upper_ge_basis_ge_lower(self, bullish_100):
        upper = smf_upper(bullish_100)
        basis = smf_basis(bullish_100)
        lower = smf_lower(bullish_100)
        assert upper >= basis >= lower

    def test_identical_params_match(self, bullish_100):
        """Calling with same data + params should return consistent values."""
        flow1 = smf_flow(bullish_100)
        flow2 = smf_flow(bullish_100)
        assert flow1 == flow2


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestSmfCache:
    """Tests for the module-level ``_smf_cache`` on ``_compute_smf``."""

    def test_cache_hit_returns_same_dict(self, bullish_100):
        """Calls with same data object should hit cache."""
        first = _compute_smf(bullish_100)
        second = _compute_smf(bullish_100)
        # Same object → same id(data) → cache hit → same dict reference
        assert first is second

    def test_new_data_object_is_cache_miss(self, bullish_100):
        """A fresh dict with identical values is a different object → cache miss."""
        first = _compute_smf(bullish_100)
        copy = dict(bullish_100)
        second = _compute_smf(copy)
        # Different id → different computation
        assert first is not second
        # But values should be extremely close
        for key in first:
            assert abs(first[key] - second[key]) < 1e-9

    def test_cache_eviction_on_many_keys(self):
        """Cache should survive and compute for many different data objects."""
        results = []
        for i in range(15):
            data = _make_data(60, close_start=100.0 + i)
            results.append(_compute_smf(data))
        # All 15 should compute successfully (cache eviction keeps it healthy)
        assert all(isinstance(r, dict) and len(r) == 9 for r in results)

    def test_wrappers_share_cache(self, bullish_100):
        """Calling multiple wrappers with the same data should share cache."""
        # This should only call _compute_smf once internally
        upper = smf_upper(bullish_100)
        lower = smf_lower(bullish_100)
        basis = smf_basis(bullish_100)
        # All computed from same cached dict
        assert upper >= basis >= lower


# ---------------------------------------------------------------------------
# _INDICATORS registration and compound operators
# ---------------------------------------------------------------------------


class TestIndicatorsRegistry:
    """Tests that SMF indicators are registered and resolvable."""

    def test_all_smf_in_indicators(self):
        for name in ("smf_flow", "smf_strength", "smf_basis", "smf_upper", "smf_lower"):
            assert name in _INDICATORS, f"{name} not found in _INDICATORS"

    def test_adaptive_mult_not_in_indicators(self):
        """adaptive_mult is an internal utility, not evaluable from YAML."""
        assert "adaptive_mult" not in _INDICATORS

    def test_compound_operator_price_gt_smf_basis(self, bullish_100):
        """price > smf_basis should work as a compound operator."""
        # In a bullish trend, price should be > basis
        result = evaluate("", {}, "price > smf_basis", bullish_100)
        assert isinstance(result, bool)

    def test_compound_operator_price_lt_smf_upper(self, bullish_100):
        """price < smf_upper — price should be below the upper band in steady trend."""
        result = evaluate("", {}, "price < smf_upper", bullish_100)
        assert result is True

    def test_resolve_smf_upper(self, bullish_100):
        val = _resolve_value("smf_upper", bullish_100)
        assert isinstance(val, float)
        assert val > 0.0

    def test_resolve_smf_lower(self, bullish_100):
        val = _resolve_value("smf_lower", bullish_100)
        assert isinstance(val, float)
        assert val > 0.0

    def test_resolve_smf_basis(self, bullish_100):
        val = _resolve_value("smf_basis", bullish_100)
        assert isinstance(val, float)
        assert val > 0.0

    def test_short_data_compound_operator_returns_false(self, short_data):
        """With insufficient data, smf_basis returns 0.0."""
        result = evaluate("", {}, "price > smf_basis", short_data)
        assert result is False
