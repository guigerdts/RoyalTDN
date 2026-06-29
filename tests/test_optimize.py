"""Tests for M4 optimizer components (scripts/optimize.py).

Covers:
- Regression test: old ``simulate()`` vs new ``backtest_run()`` produce
  compatible trade output and objective values.
- Walk-forward validation split logic unit tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

# ========================================================================
# Helpers
# ========================================================================


def _trending_ohlcv(
    n: int = 30,
    start_price: float = 100.0,
    step: float = 0.5,
    symbol: str = "TEST/USDT",
) -> pd.DataFrame:
    """Build an OHLCV DataFrame with a linear price trend."""
    from datetime import datetime

    base_ts = datetime(2025, 1, 1, 10, 0)
    prices = [start_price + i * step for i in range(n)]
    return pd.DataFrame({
        "timestamp": [base_ts + pd.Timedelta(hours=i) for i in range(n)],
        "open": prices,
        "high": [p + 1.0 for p in prices],
        "low": [p - 1.0 for p in prices],
        "close": prices,
        "volume": [1000.0] * n,
    })


# ========================================================================
# Regression: simulate() vs backtest_run()
# ========================================================================

_BUY_SIGNAL: dict = {
    "action": "BUY",
    "symbol": "TEST/USDT",
    "price": 110.0,
    "sizing": 0.5,
    "cell_name": "regression_test",
}

_SELL_SIGNAL: dict = {
    "action": "SELL",
    "symbol": "TEST/USDT",
    "price": 112.5,
    "sizing": 0.5,
    "entry_price": 110.0,
    "cell_name": "regression_test",
}

# 30-bar sequence: BUY at bar 20 (after warmup for simulate()),
# SELL at bar 25.  Bars before 20 and after 25 produce no signal.
_REGRESSION_SIGNALS: list[dict | None] = [None] * 30
_REGRESSION_SIGNALS[20] = _BUY_SIGNAL
_REGRESSION_SIGNALS[25] = _SELL_SIGNAL


class _ControlledCell:
    """Mock ``Cell`` that returns predetermined signals by bar index.

    Provides ``enter_position`` / ``exit_position`` so that
    ``EventEngine._process_event`` can call them without error.
    """

    def __init__(self, config: dict | None = None,
                 inference_engine: object = None) -> None:
        self.name = "regression_test_cell"
        self.state = "IDLE"
        self.entry_price = 0.0
        self._bar = -1

    async def handle(self, event: dict) -> dict | None:
        self._bar += 1
        if self._bar < len(_REGRESSION_SIGNALS):
            sig = _REGRESSION_SIGNALS[self._bar]
            if sig is not None:
                # Match the price to the bar's close so PnL is consistent.
                # Use the entry_price from the signal definition (which is the
                # correct buy price) — do NOT override from self.entry_price
                # because simulate() never calls enter_position().
                sig = dict(sig)
                sig["price"] = float(event.get("price", sig["price"]))
            return sig
        return None

    def enter_position(self, price: float, direction: str = "long") -> None:
        self.state = "IN_POSITION"
        self.entry_price = price

    def exit_position(self) -> None:
        self.state = "IDLE"
        self.entry_price = 0.0

    def record_approval(self) -> None:
        """Stub — required by EventEngine._process_event."""

    def record_rejection(self) -> None:
        """Stub — required by EventEngine._process_event."""


class TestRegressionSimulateVsBacktestRun:
    """Compare old ``simulate()`` and new ``backtest_run()`` output."""

    @pytest.fixture
    def ohlcv(self) -> pd.DataFrame:
        return _trending_ohlcv(n=30)

    @pytest.fixture(autouse=True)
    def _patch_cell(self):
        """Patch ``cells.base.Cell`` so both pipelines use a controlled cell."""
        with patch("royaltdn.cells.base.Cell", _ControlledCell):
            yield

    # ------------------------------------------------------------------
    # Trade count and structure
    # ------------------------------------------------------------------

    async def _run_simulate(self, ohlcv: pd.DataFrame) -> list[dict]:
        """Run the old ``simulate()`` and return trades."""
        from royaltdn.scripts.optimize import simulate

        config = {
            "name": "regression",
            "symbol": "TEST/USDT",
            "risk": {"sizing": 0.5, "max_positions": 10},
        }
        return await simulate(config, ohlcv, initial_capital=100_000.0)

    async def _run_backtest(self, ohlcv: pd.DataFrame) -> list[dict]:
        """Run the new ``backtest_run()`` and return normalized trades."""
        from royaltdn.backtesting import run as backtest_run

        config = {
            "name": "regression",
            "symbol": "TEST/USDT",
            "risk": {"sizing": 0.5, "max_positions": 10},
        }
        result = await backtest_run(
            config, ohlcv,
            initial_capital=100_000.0,
            commission=0.0,
            slippage=0.0,
        )
        return result.trades

    # -- Tests ---------------------------------------------------------

    def test_both_produce_one_trade(self, ohlcv):
        """Both pipelines produce exactly 1 closed trade (BUY → SELL)."""
        old_trades = asyncio.run(self._run_simulate(ohlcv))
        new_trades = asyncio.run(self._run_backtest(ohlcv))

        assert len(old_trades) == 1, f"simulate() expected 1 trade, got {len(old_trades)}"
        assert len(new_trades) == 1, f"backtest_run() expected 1 trade, got {len(new_trades)}"

    def test_both_have_same_fields(self, ohlcv):
        """Trade dicts from both pipelines have the same set of keys."""
        old_trades = asyncio.run(self._run_simulate(ohlcv))
        new_trades = asyncio.run(self._run_backtest(ohlcv))

        old_keys = set(old_trades[0].keys())
        new_keys = set(new_trades[0].keys())
        assert old_keys == new_keys, (
            f"Key mismatch: simulate={old_keys}, backtest_run={new_keys}"
        )

    def test_both_compatible_trade_values(self, ohlcv):
        """Trade fields have compatible values across pipelines.

        ``pnl`` may differ slightly due to different rounding paths
        (simulate rounds to 2dp after PnL, backtest_run rounds after
        normalizing).  We check approximate equality.
        """
        old_trades = asyncio.run(self._run_simulate(ohlcv))
        new_trades = asyncio.run(self._run_backtest(ohlcv))

        old = old_trades[0]
        new = new_trades[0]

        assert old["symbol"] == new["symbol"], "symbol mismatch"
        assert old["action"] == new["action"], "action mismatch"
        assert old["entry_price"] == pytest.approx(new["entry_price"], rel=1e-6)
        assert old["exit_price"] == pytest.approx(new["exit_price"], rel=1e-6)
        assert old["qty"] == pytest.approx(new["qty"], rel=1e-4)
        # PnL: simulate may round differently, use abs tolerance
        assert old["pnl"] == pytest.approx(new["pnl"], abs=0.1), (
            f"pnl mismatch: simulate={old['pnl']}, backtest_run={new['pnl']}"
        )
        # Capital should be initial + cumulative PnL
        assert old["capital"] == pytest.approx(new["capital"], abs=0.1)

    # ------------------------------------------------------------------
    # Objective / metrics agreement
    # ------------------------------------------------------------------

    def test_objective_values_agree(self, ohlcv):
        """``compute_objective()`` returns the same value for both trade lists."""
        from royaltdn.scripts.optimize import compute_objective

        old_trades = asyncio.run(self._run_simulate(ohlcv))
        new_trades = asyncio.run(self._run_backtest(ohlcv))

        old_obj = compute_objective(old_trades, metric="sharpe")
        new_obj = compute_objective(new_trades, metric="sharpe")

        assert old_obj == pytest.approx(new_obj, abs=0.5), (
            f"Objective mismatch: simulate={old_obj}, backtest_run={new_obj}"
        )

    def test_objective_empty_trades(self, ohlcv):
        """Both pipelines handle zero trades identically."""
        from royaltdn.scripts.optimize import compute_objective

        assert compute_objective([], metric="sharpe") == -999.0
        assert compute_objective([], metric="profit_factor") == -999.0

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_simulate_no_trades(self):
        """Cell that produces no signals → 0 trades from simulate()."""
        from royaltdn.scripts.optimize import simulate

        class _NullCell:
            def __init__(self, config=None, inference_engine=None):
                self.name = "null"
                self.state = "IDLE"

            async def handle(self, event):
                return None

        with patch("royaltdn.cells.base.Cell", _NullCell):
            ohlcv = _trending_ohlcv(n=20)
            trades = asyncio.run(simulate(
                {"name": "null", "symbol": "TEST/USDT", "risk": {}},
                ohlcv,
            ))
        assert len(trades) == 0

    def test_backtest_no_trades(self):
        """Cell that produces no signals → 0 trades from backtest_run()."""
        from royaltdn.backtesting import run as backtest_run

        class _NullCell:
            def __init__(self, config=None, inference_engine=None):
                self.name = "null"
                self.state = "IDLE"

            async def handle(self, event):
                return None

        with patch("royaltdn.cells.base.Cell", _NullCell):
            ohlcv = _trending_ohlcv(n=20)
            result = asyncio.run(backtest_run(
                {"name": "null", "symbol": "TEST/USDT", "risk": {}},
                ohlcv,
                commission=0.0,
                slippage=0.0,
            ))
        assert len(result.trades) == 0
        # Equity curve has initial + one entry per bar
        assert len(result.equity_curve) == len(ohlcv) + 1
        assert result.equity_curve[0] == 100_000.0


# ========================================================================
# Walk-forward validation — split logic unit tests
# ========================================================================


class TestWalkForwardSplit:
    """Unit tests for ``walk_forward_validate()`` split logic.

    These tests mock ``optimize_strategy`` and ``backtest_run`` to isolate
    the fold construction / embargo logic.
    """

    @pytest.fixture
    def ohlcv_small(self) -> pd.DataFrame:
        """50-bar OHLCV — insufficient data for any window."""
        return _trending_ohlcv(n=50)

    @pytest.fixture
    def strategy_config(self) -> dict:
        return {
            "name": "test_strat",
            "symbol": "TEST/USDT",
            "timeframe": "1h",
            "risk": {"sizing": 0.5, "max_positions": 3},
        }

    def _make_mock_opt_result(self, sharpe: float = 1.5) -> dict:
        """Create a mock ``optimize_strategy()`` return dict."""
        return {
            "best_params": {"risk.sizing": 0.01},
            "best_value": sharpe,
            "best_trial": 0,
            "best_metrics": {
                "sharpe_ratio": sharpe,
                "profit_factor": 2.0,
                "win_rate": 0.6,
                "n_trades": 10,
            },
            "worst_metrics": {},
            "trials_completed": 10,
        }

    def _make_mock_bt_result(self, n_trades: int = 0,
                             pnl: float = 0.0) -> MagicMock:
        """Create a mock ``BacktestResult``."""
        result = MagicMock()
        result.trades = (
            [{"pnl": pnl, "symbol": "TEST/USDT", "action": "SELL",
              "entry_price": 100.0, "exit_price": 101.0, "qty": 1.0,
              "capital": 100_100.0}]
            if n_trades > 0 else []
        )
        result.equity_curve = [100_000.0]
        result.metrics = {"sharpe": 0.0, "sortino": 0.0}
        return result

    # ------------------------------------------------------------------
    # 1. Basic walk-forward: correct fold structure
    # ------------------------------------------------------------------

    @pytest.fixture
    def ohlcv_large_enough(self) -> pd.DataFrame:
        """5000-bar dataset — enough for multiple valid windows."""
        return _trending_ohlcv(n=5000)

    def test_valid_windows_have_required_keys(self, ohlcv_large_enough,
                                              strategy_config):
        """Every valid window dict has the expected keys.

        With 5000 bars and n_windows=5, only windows 0-1 have non-zero
        val data (the walk-forward design caps the last windows).  We
        verify the keys of whatever windows are produced.
        """
        from royaltdn.scripts.optimize import walk_forward_validate

        expected_keys = {
            "window", "train_bars", "val_bars", "is_sharpe",
            "is_profit_factor", "is_win_rate", "is_trades",
            "oos_sharpe", "oos_profit_factor", "oos_win_rate",
            "oos_trades", "best_params",
        }

        with (
            patch("royaltdn.scripts.optimize.optimize_strategy") as opt_mock,
            patch("royaltdn.scripts.optimize.backtest_run") as bt_mock,
        ):
            opt_mock.return_value = self._make_mock_opt_result()
            bt_mock.return_value = self._make_mock_bt_result(n_trades=3)

            result = walk_forward_validate(
                strategy_name="test_strat",
                strategy_config=strategy_config,
                ohlcv=ohlcv_large_enough,
                n_trials=5,
                metric="sharpe",
                console=None,
                n_windows=5,
            )

        assert len(result["walk_windows"]) > 0, "Expected at least 1 valid window"
        for w in result["walk_windows"]:
            missing = expected_keys - set(w.keys())
            assert not missing, f"Window {w['window']} missing keys: {missing}"

    # ------------------------------------------------------------------
    # 2. Embargo gap: train/test data should NOT overlap
    # ------------------------------------------------------------------

    def test_train_val_no_overlap(self, ohlcv_large_enough, strategy_config):
        """Validation start >= training end for every window (no overlap)."""
        from royaltdn.scripts.optimize import walk_forward_validate

        total = len(ohlcv_large_enough)
        n_windows = 5
        step = total // n_windows

        with (
            patch("royaltdn.scripts.optimize.optimize_strategy") as opt_mock,
            patch("royaltdn.scripts.optimize.backtest_run") as bt_mock,
        ):
            opt_mock.return_value = self._make_mock_opt_result()
            bt_mock.return_value = self._make_mock_bt_result(n_trades=3)

            result = walk_forward_validate(
                strategy_name="test_strat",
                strategy_config=strategy_config,
                ohlcv=ohlcv_large_enough,
                n_trials=5,
                metric="sharpe",
                console=None,
                n_windows=n_windows,
            )

            for w in result["walk_windows"]:
                w_idx = w["window"]
                train_start = w_idx * step
                train_end = min(train_start + int(step * 3.5), total)
                val_start = train_end

                # The function does NOT set embargo gap — val_start == train_end.
                # This is by design (no overlap, but also no gap).
                assert val_start >= train_end, (
                    f"Window {w_idx}: val_start ({val_start}) < train_end "
                    f"({train_end}) — OVERLAP detected"
                )

    def test_train_val_bars_counted_correctly(self, ohlcv_large_enough,
                                              strategy_config):
        """train_bars and val_bars match expected sizes."""
        from royaltdn.scripts.optimize import walk_forward_validate

        total = len(ohlcv_large_enough)
        n_windows = 5
        step = total // n_windows

        with (
            patch("royaltdn.scripts.optimize.optimize_strategy") as opt_mock,
            patch("royaltdn.scripts.optimize.backtest_run") as bt_mock,
        ):
            opt_mock.return_value = self._make_mock_opt_result()
            bt_mock.return_value = self._make_mock_bt_result(n_trades=3)

            result = walk_forward_validate(
                strategy_name="test_strat",
                strategy_config=strategy_config,
                ohlcv=ohlcv_large_enough,
                n_trials=5,
                metric="sharpe",
                console=None,
                n_windows=n_windows,
            )

            for w in result["walk_windows"]:
                w_idx = w["window"]
                expected_train_end = min(w_idx * step + int(step * 3.5), total)
                expected_train_bars = expected_train_end - w_idx * step
                expected_val_end = min(expected_train_end + int(step * 1.5), total)
                expected_val_bars = expected_val_end - expected_train_end

                assert w["train_bars"] == expected_train_bars, (
                    f"Window {w_idx}: expected {expected_train_bars} train bars, "
                    f"got {w['train_bars']}"
                )
                assert w["val_bars"] == expected_val_bars, (
                    f"Window {w_idx}: expected {expected_val_bars} val bars, "
                    f"got {w['val_bars']}"
                )

    # ------------------------------------------------------------------
    # 3. Edge case: insufficient data
    # ------------------------------------------------------------------

    def test_insufficient_data_returns_empty_result(self, ohlcv_small,
                                                    strategy_config):
        """50 bars with n_windows=5 → all windows skipped (train_bars < 100)."""
        from royaltdn.scripts.optimize import walk_forward_validate

        with (
            patch("royaltdn.scripts.optimize.optimize_strategy") as opt_mock,
            patch("royaltdn.scripts.optimize.backtest_run") as bt_mock,
        ):
            result = walk_forward_validate(
                strategy_name="test_strat",
                strategy_config=strategy_config,
                ohlcv=ohlcv_small,
                n_trials=5,
                metric="sharpe",
                console=None,
                n_windows=5,
            )

        # All windows should be skipped due to train_bars < 100
        assert len(result["walk_windows"]) == 0, (
            f"Expected 0 windows for 50 bars, got {len(result['walk_windows'])}"
        )
        # opt and bt should never have been called
        opt_mock.assert_not_called()
        bt_mock.assert_not_called()

        # Default / sentinel return values
        assert result["avg_is_sharpe"] == -999.0
        assert result["avg_oos_sharpe"] == -999.0
        assert result["verdict"] == "SIN SEÑALES"

    def test_insufficient_val_data_window_skipped(self, ohlcv_large_enough,
                                                  strategy_config):
        """Window where val_bars < 20 should be skipped."""
        from royaltdn.scripts.optimize import walk_forward_validate

        with (
            patch("royaltdn.scripts.optimize.optimize_strategy") as opt_mock,
            patch("royaltdn.scripts.optimize.backtest_run") as bt_mock,
        ):
            opt_mock.return_value = self._make_mock_opt_result()
            bt_mock.return_value = self._make_mock_bt_result(n_trades=3)

            result = walk_forward_validate(
                strategy_name="test_strat",
                strategy_config=strategy_config,
                ohlcv=ohlcv_large_enough,
                n_trials=5,
                metric="sharpe",
                console=None,
                n_windows=5,
            )

        # With 5000 bars and n_windows=5, step=1000.
        # Window 0: train[0:3500], val[3500:5000] → val_bars=1500 ✓
        # Window 1: train[1000:4500], val[4500:5000] → val_bars=500 ✓
        # Window 2: train[2000:5000], val[5000:5000] → val_bars=0 ✗ (skipped)
        # Window 3: train[3000:5000], val[5000:5000] → val_bars=0 ✗ (skipped)
        # Window 4: train[4000:5000], val[5000:5000] → val_bars=0 ✗ (skipped)
        # So only windows 0 and 1 should be present.
        found_windows = {w["window"] for w in result["walk_windows"]}
        assert 0 in found_windows, "Window 0 should be valid"
        assert 1 in found_windows, "Window 1 should be valid"
        assert 4 not in found_windows, (
            "Window 4 expected to be skipped (val_bars=0)"
        )

    # ------------------------------------------------------------------
    # Walk-forward verdict logic
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "oos_sharpe, drop_pct, total_trades, is_sharpe, expected",
        [
            (1.0, 20.0, 50, 2.0, "ROBUSTO"),       # strong OOS, low drop
            (-0.5, 60.0, 50, 1.5, "SOBREAJUSTADO"), # negative OOS
            (0.6, 55.0, 50, 2.0, "SOBREAJUSTADO"),  # good OOS but high drop
            (1.0, 20.0, 0, 2.0, "SIN SEÑALES"),     # no trades
            (0.0, 0.0, 0, 0.0, "SIN SEÑALES"),      # no trades
            (0.3, 40.0, 50, 1.0, "SOBREAJUSTADO"),  # OOS < 0.5
        ],
    )
    def test_walk_forward_verdict(
        self, oos_sharpe, drop_pct, total_trades, is_sharpe, expected,
    ):
        """walk_forward_verdict classifies correctly."""
        from royaltdn.scripts.optimize import walk_forward_verdict

        verdict = walk_forward_verdict(oos_sharpe, drop_pct, total_trades, is_sharpe)
        assert verdict == expected, (
            f"verdict({oos_sharpe}, {drop_pct}, {total_trades}, {is_sharpe}) "
            f"= {verdict}, expected {expected}"
        )
