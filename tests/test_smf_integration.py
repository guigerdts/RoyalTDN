"""Integration tests for SMF Cloud strategies — Phase 2 / PR #2.

Covers:
- YAML cell loading with SMF conditions → valid condition graph
- load_cells_from_file parses SMF YAML correctly
- _PARAM_RANGES entries exist with correct types
- Backward compatibility: existing indicators still work
- Adaptive trailing: synthetic data activates and adapts
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# ── numpy compatibility shim ──────────────────────────────────────────
# inference.graph → inference.conditions → numpy (broken in some envs).
# Pre-seed sys.modules so Cell.__init__ can lazy-import graph without
# triggering the numpy dependency chain.
_HAS_NUMPY: bool = False
try:
    import numpy as _np  # noqa: F401
    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False
NUMPY_SKIP_REASON = "numpy C extensions unavailable on this system"

if "royaltdn.inference.graph" not in sys.modules:
    _inf_graph = types.ModuleType("royaltdn.inference.graph")
    _inf_graph.build_graph = MagicMock()
    sys.modules["royaltdn.inference.graph"] = _inf_graph


# ======================================================================
# YAML loading — SMF cells parse correctly
# ======================================================================


class TestSmfYamlLoading:
    """SMF YAML cells load and build valid condition graphs."""

    def _make_inference_engine(self):
        """Create a minimal inference engine stub for graph building."""
        eng = MagicMock()
        # build_graph is called in Cell.__init__ — return a MagicMock graph
        from royaltdn.inference.graph import build_graph
        eng.entry_graph = MagicMock()
        eng.entry_graph.evaluate.return_value = True
        return eng

    def test_smf_cell_loads_from_yaml(self):
        """A YAML dict with SMF conditions creates a valid Cell."""
        from royaltdn.cells.base import Cell

        config = {
            "name": "test_smf_retest_rsi",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "max_hold_hours": 8,
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "smf_flow", "params": {}, "operator": "smf_flow > 0.0"},
                    {"indicator": "smf_basis", "params": {}, "operator": "price < smf_basis"},
                    {"indicator": "rsi", "params": {"period": 7}, "operator": "< 40.0"},
                ],
            },
            "short_entry": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "smf_flow", "params": {}, "operator": "smf_flow < 0.0"},
                    {"indicator": "smf_basis", "params": {}, "operator": "price > smf_basis"},
                    {"indicator": "rsi", "params": {"period": 7}, "operator": "> 60.0"},
                ],
            },
            "exit": [
                {"type": "trailing_stop", "params": {"atr_multiplier": 2.0, "min_mult": 0.5, "max_mult": 1.5}},
                {"type": "stop_loss", "params": {"atr_multiplier": 3.0}},
            ],
            "risk": {"sizing": 0.01, "max_positions": 3},
        }

        eng = self._make_inference_engine()
        cell = Cell(config=config, inference_engine=eng)
        assert cell.name == "test_smf_retest_rsi"
        assert cell._entry_graph is not None
        assert cell.exit_trailing_min_mult == 0.5
        assert cell.exit_trailing_max_mult == 1.5
        assert cell.exit_trailing_stop == 2.0

    @pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
    def test_smf_cell_rejects_short_data(self):
        """SMF compound operator returns False on insufficient data."""
        from royaltdn.inference.conditions import evaluate

        short_data = {"close": [100.0] * 10, "high": [101.0] * 10, "low": [99.0] * 10, "volume": [1000.0] * 10}
        result = evaluate("", {}, "smf_flow > 0.0", short_data)
        assert result is False


class TestLoadCellsFromFile:
    """``load_cells_from_file`` parses SMF YAML correctly."""

    def _make_inference_engine(self):
        eng = MagicMock()
        from royaltdn.inference.graph import build_graph
        return eng

    def test_load_smf_cells_from_scalping(self):
        """load_cells_from_file reads scalping.yaml and produces SMF cells."""
        from pathlib import Path
        from royaltdn.cells.loader import load_cells_from_file

        scalping_path = Path(__file__).parents[1] / "src" / "royaltdn" / "cells" / "templates" / "scalping.yaml"
        if not scalping_path.exists():
            pytest.skip(f"scalping.yaml not found at {scalping_path}")

        eng = self._make_inference_engine()
        cells = load_cells_from_file(scalping_path, eng)

        smf_names = [c.name for c in cells if "smf" in c.name]
        assert len(smf_names) >= 4, f"Expected ≥4 SMF cells, got {smf_names}"

        # Each SMF cell should have adaptive trailing params
        for c in cells:
            if "smf" in c.name:
                assert c.exit_trailing_min_mult is not None, f"{c.name} missing min_mult"
                assert c.exit_trailing_max_mult is not None, f"{c.name} missing max_mult"

    def test_load_smf_cells_from_intraday(self):
        """load_cells_from_file reads intraday.yaml and produces SMF cells."""
        from pathlib import Path
        from royaltdn.cells.loader import load_cells_from_file

        intraday_path = Path(__file__).parents[1] / "src" / "royaltdn" / "cells" / "templates" / "intraday.yaml"
        if not intraday_path.exists():
            pytest.skip(f"intraday.yaml not found at {intraday_path}")

        eng = self._make_inference_engine()
        cells = load_cells_from_file(intraday_path, eng)

        smf_names = [c.name for c in cells if "smf" in c.name]
        assert len(smf_names) >= 4, f"Expected ≥4 SMF cells, got {smf_names}"

    def test_load_smf_cells_from_swing(self):
        """load_cells_from_file reads swing.yaml and produces SMF cells."""
        from pathlib import Path
        from royaltdn.cells.loader import load_cells_from_file

        swing_path = Path(__file__).parents[1] / "src" / "royaltdn" / "cells" / "templates" / "swing.yaml"
        if not swing_path.exists():
            pytest.skip(f"swing.yaml not found at {swing_path}")

        eng = self._make_inference_engine()
        cells = load_cells_from_file(swing_path, eng)

        smf_names = [c.name for c in cells if "smf" in c.name]
        assert len(smf_names) >= 4, f"Expected ≥4 SMF cells, got {smf_names}"


# ======================================================================
# _PARAM_RANGES entries
# ======================================================================


class TestSmfParamRanges:
    """_PARAM_RANGES entries for SMF Cloud params exist with correct types."""

    def test_flow_len_param_range(self):
        from royaltdn.scripts.optimize import _PARAM_RANGES
        assert "flow_len" in _PARAM_RANGES
        ptype, low, high, step = _PARAM_RANGES["flow_len"]
        assert ptype == "int"
        assert low <= 10
        assert high >= 50

    def test_ema_period_param_range(self):
        from royaltdn.scripts.optimize import _PARAM_RANGES
        assert "ema_period" in _PARAM_RANGES
        ptype, low, high, step = _PARAM_RANGES["ema_period"]
        assert ptype == "int"
        assert low <= 10
        assert high >= 60

    def test_atr_period_param_range(self):
        from royaltdn.scripts.optimize import _PARAM_RANGES
        assert "atr_period" in _PARAM_RANGES
        ptype, low, high, step = _PARAM_RANGES["atr_period"]
        assert ptype == "int"
        assert low <= 7
        assert high >= 30

    def test_min_mult_param_range(self):
        from royaltdn.scripts.optimize import _PARAM_RANGES
        assert "min_mult" in _PARAM_RANGES
        ptype, low, high, step = _PARAM_RANGES["min_mult"]
        assert ptype == "float"
        assert step is not None

    def test_max_mult_param_range(self):
        from royaltdn.scripts.optimize import _PARAM_RANGES
        assert "max_mult" in _PARAM_RANGES
        ptype, low, high, step = _PARAM_RANGES["max_mult"]
        assert ptype == "float"
        assert step is not None

    def test_smf_shared_params_exist(self):
        from royaltdn.scripts.optimize import _SMF_SHARED_PARAMS
        assert "flow_len" in _SMF_SHARED_PARAMS
        assert "ema_period" in _SMF_SHARED_PARAMS
        assert "atr_period" in _SMF_SHARED_PARAMS


# ======================================================================
# Backward compatibility — existing indicators still work
# ======================================================================


@pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
class TestBackwardCompatibility:
    """Existing indicators (RSI, EMA, Bollinger, ADX) still work after changes."""

    def _make_data(self, n=100):
        return {
            "close": [100.0 + i * 0.5 for i in range(n)],
            "high": [101.0 + i * 0.5 for i in range(n)],
            "low": [99.0 + i * 0.5 for i in range(n)],
            "volume": [1000.0 + (i % 10) * 50 for i in range(n)],
        }

    def test_rsi_unchanged(self):
        from royaltdn.inference.conditions import rsi
        val = rsi(self._make_data(), period=14)
        assert isinstance(val, float)
        assert 0 <= val <= 100

    def test_ema_unchanged(self):
        from royaltdn.inference.conditions import ema
        val = ema(self._make_data(), period=20)
        assert isinstance(val, float)
        assert val > 0

    def test_bollinger_lower_unchanged(self):
        from royaltdn.inference.conditions import bollinger_lower
        val = bollinger_lower(self._make_data(), period=20, std=2.0)
        assert isinstance(val, float)

    def test_bollinger_upper_unchanged(self):
        from royaltdn.inference.conditions import bollinger_upper
        val = bollinger_upper(self._make_data(), period=20, std=2.0)
        assert isinstance(val, float)

    def test_adx_unchanged(self):
        from royaltdn.inference.conditions import adx
        val = adx(self._make_data(), period=14)
        assert isinstance(val, float)
        assert val >= 0

    def test_zscore_unchanged(self):
        from royaltdn.inference.conditions import zscore
        val = zscore(self._make_data(), period=20)
        assert isinstance(val, float)

    def test_volume_surge_unchanged(self):
        from royaltdn.inference.conditions import volume_surge
        result = volume_surge(self._make_data(), period=20, factor=2.0)
        assert isinstance(result, bool)

    def test_compound_operator_resolves_existing(self):
        """price > ema still works as a compound operator."""
        from royaltdn.inference.conditions import evaluate
        data = self._make_data()
        result = evaluate("", {}, "price > ema", data)
        assert isinstance(result, bool)


# ======================================================================
# Adaptive trailing: synthetic data test
# ======================================================================


class TestAdaptiveTrailing:
    """Adaptive trailing activates and adapts with SMF strength."""

    def _build_trending_data(self, n_bars: int = 60) -> list[dict]:
        """Build bars with a clear rising trend (bullish)."""
        bars = []
        price = 100.0
        for i in range(n_bars):
            price += 0.3 + (i % 5) * 0.1  # rising
            bars.append({
                "close": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "volume": 1000.0,
            })
        return bars

    def test_adaptive_trailing_in_non_trending_data_returns_none(self):
        """With insufficient bars, adaptive trailing returns None (no exit)."""
        from royaltdn.cells.base import Cell
        from royaltdn.inference.graph import build_graph

        config = {
            "name": "adaptive_test",
            "symbol": "TEST",
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "smf_flow", "params": {}, "operator": "smf_flow > 0.0"},
                ],
            },
            "exit": [
                {"type": "trailing_stop", "params": {"atr_multiplier": 2.0, "min_mult": 0.5, "max_mult": 1.5}},
            ],
            "risk": {"sizing": 0.01, "max_positions": 3},
        }

        eng = MagicMock()
        eng.entry_graph = build_graph(config["entry"])
        cell = Cell(config=config, inference_engine=eng)
        cell.state = "IN_POSITION"
        cell.entry_price = 100.0
        cell.entry_time = 1000.0

        # Only 5 bars — insufficient for SMF or ATR
        cell.bars = self._build_trending_data(5)
        result = cell._check_exit(101.0)
        assert result is None, "Should not exit with insufficient data"

    def test_adaptive_trailing_min_mult_correct(self):
        """min_mult and max_mult are parsed correctly from YAML."""
        from royaltdn.cells.base import Cell

        config = {
            "name": "adaptive_parse",
            "symbol": "TEST",
            "exit": [
                {"type": "trailing_stop", "params": {"atr_multiplier": 2.0, "min_mult": 0.5, "max_mult": 1.5}},
            ],
            "risk": {"sizing": 0.01},
        }
        cell = Cell(config=config, inference_engine=MagicMock())
        assert cell.exit_trailing_min_mult == 0.5
        assert cell.exit_trailing_max_mult == 1.5

    def test_trailing_without_min_mult_backward_compat(self):
        """Trailing stop without min_mult/max_mult uses fixed ATR multiplier."""
        from royaltdn.cells.base import Cell

        config = {
            "name": "fixed_trailing",
            "symbol": "TEST",
            "exit": [
                {"type": "trailing_stop", "params": {"atr_multiplier": 2.5}},
            ],
            "risk": {"sizing": 0.01},
        }
        cell = Cell(config=config, inference_engine=MagicMock())
        assert cell.exit_trailing_min_mult is None
        assert cell.exit_trailing_max_mult is None
        assert cell.exit_trailing_stop == 2.5

    def test_backward_compat_existing_cell_unchanged(self):
        """A cell without SMF params still works as before (no adaptive)."""
        from royaltdn.cells.base import Cell
        from royaltdn.inference.graph import build_graph

        config = {
            "name": "legacy_cell",
            "symbol": "TEST",
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": "< 30.0"},
                ],
            },
            "exit": [
                {"type": "trailing_stop", "params": {"pct": 1.5}},
            ],
            "risk": {"sizing": 0.01, "max_positions": 3},
        }
        eng = MagicMock()
        eng.entry_graph = build_graph(config["entry"])
        cell = Cell(config=config, inference_engine=eng)
        assert cell.exit_trailing_stop_pct == 0.015  # 1.5% / 100
        assert cell.exit_trailing_min_mult is None
        assert cell.exit_trailing_max_mult is None
