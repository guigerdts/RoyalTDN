"""Unit tests for the Cell class.

Tests cover initialisation, symbol filtering, entry/exit condition
evaluation, stop-loss, take-profit, and SHORT entry/exit behaviour.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch

# ── numpy compatibility shim ──────────────────────────────────────────
# inference.graph → inference.conditions → numpy (broken in some envs).
# Pre-seed sys.modules so that patch("inference.graph.build_graph") and
# the lazy import inside Cell.__init__ both resolve without hitting the
# numpy dependency chain.
if "royaltdn.inference.graph" not in sys.modules:
    import types  # noqa: E402 (imported after sys guard)
    _inf_graph = types.ModuleType("royaltdn.inference.graph")
    _inf_graph.build_graph = MagicMock()
    sys.modules["royaltdn.inference.graph"] = _inf_graph


def _make_bars(count: int, base_price: float = 50000.0, volatility: float = 200.0) -> list[dict]:
    """Generate realistic OHLCV bars for testing."""
    import random
    bars = []
    price = base_price
    for _ in range(count):
        hi = price + volatility * random.uniform(0, 1)
        lo = price - volatility * random.uniform(0, 1)
        close = lo + (hi - lo) * random.uniform(0.3, 0.7)
        bars.append({
            "open": price,
            "high": hi,
            "low": lo,
            "close": close,
            "volume": 100.0 + random.uniform(0, 50),
        })
        price = close
    return bars


def _make_tick_event(symbol: str, price: float) -> dict[str, object]:
    """Create a realistic tick event with proper OHLCV data."""
    return {
        "type": "tick",
        "symbol": symbol,
        "price": price,
        "data": {
            "close": price,
            "high": price * 1.001,   # 0.1% wiggle
            "low": price * 0.999,    # 0.1% wiggle
            "volume": 100.0,
        },
    }


class TestCell(unittest.TestCase):
    """Test suite for the Cell autonomous trading cell."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.config = {
            "name": "ema_cross",
            "symbol": "BTCUSDT",
            "risk": {
                "sizing": 0.01,
                "max_positions": 3,
            },
            "exit": [
                {"type": "stop_loss", "params": {"atr_multiplier": 2.0}},
                {"type": "take_profit", "params": {"atr_multiplier": 4.0}},
            ],
            "entry": {
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "rsi",
                        "params": {"period": 7},
                        "operator": "< 30",
                    }
                ],
            },
        }
        self.mock_engine = MagicMock()
        # mock build_graph to return a MagicMock that evaluates to True/False
        self.graph_mock = MagicMock()
        self.graph_mock.evaluate.return_value = False

        with patch("inference.graph.build_graph", return_value=self.graph_mock):
            from royaltdn.cells.base import Cell
            self.cell = Cell(self.config, inference_engine=self.mock_engine)

    def tearDown(self):
        self.loop.close()

    # -- Initialisation -----------------------------------------------------

    def test_init(self):
        """Cell should initialise with config values, state IDLE."""
        self.assertEqual(self.cell.name, "ema_cross")
        self.assertEqual(self.cell.symbol, "BTCUSDT")
        self.assertEqual(self.cell.state, "IDLE")
        self.assertEqual(self.cell.sizing, 0.01)
        self.assertEqual(self.cell.exit_stop_loss, 2.0)
        self.assertEqual(self.cell.exit_take_profit, 4.0)

    def test_init_defaults(self):
        """Cell should use sensible defaults for missing config keys."""
        with patch("inference.graph.build_graph", return_value=self.graph_mock):
            from royaltdn.cells.base import Cell
            minimal = Cell({"name": "minimal", "symbol": "ETHUSDT"})
        self.assertEqual(minimal.name, "minimal")
        self.assertEqual(minimal.symbol, "ETHUSDT")
        self.assertEqual(minimal.state, "IDLE")
        self.assertEqual(minimal.sizing, 0.01)
        self.assertIsNone(minimal.exit_stop_loss)
        self.assertIsNone(minimal.exit_take_profit)

    # -- Symbol filtering ---------------------------------------------------

    def test_handle_wrong_symbol_returns_none(self):
        """Event with different symbol should be ignored."""
        event = {"type": "tick", "symbol": "ETHUSDT", "price": 3000}
        result = self.loop.run_until_complete(self.cell.handle(event))
        self.assertIsNone(result)

    def test_handle_correct_symbol_processes(self):
        """Event with matching symbol should be processed."""
        self.graph_mock.evaluate.return_value = False
        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 50000,
            "data": {"close": 50000, "volume": 100},
        }
        result = self.loop.run_until_complete(self.cell.handle(event))
        # Entry conditions not met, so no signal
        self.assertIsNone(result)
        # But bar should be accumulated
        self.assertEqual(len(self.cell.bars), 1)

    # -- Entry conditions ---------------------------------------------------

    def test_entry_conditions_met(self):
        """When entry conditions are met, handle should return BUY signal."""
        self.graph_mock.evaluate.return_value = True

        # Need 20+ bars for _build_data to return data
        self.cell.bars = _make_bars(25, base_price=50000.0)

        result = None
        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "data": {"close": 50000.0, "volume": 100.0},
        }
        result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "BUY")
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertEqual(result["sizing"], 0.01)

        # Simulate what the engine does after risk approval
        self.cell.enter_position(result["price"])
        self.assertEqual(self.cell.state, "IN_POSITION")
        self.assertGreater(self.cell.entry_price, 0)

    def test_entry_conditions_not_met(self):
        """When entry conditions are not met, handle should return None."""
        self.graph_mock.evaluate.return_value = False
        self.cell.bars = _make_bars(25)

        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "data": {"close": 50000.0, "volume": 100.0},
        }
        result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNone(result)
        self.assertEqual(self.cell.state, "IDLE")

    def test_entry_no_inference_engine(self):
        """Cell without inference engine should never generate signals."""
        with patch("inference.graph.build_graph"):
            from royaltdn.cells.base import Cell
            no_engine_cell = Cell(self.config, inference_engine=None)

        no_engine_cell.bars = _make_bars(25)
        for _ in range(10):
            event = {
                "type": "tick",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "data": {"close": 50000.0, "volume": 100.0},
            }
            result = self.loop.run_until_complete(no_engine_cell.handle(event))
            self.assertIsNone(result)

        self.assertEqual(no_engine_cell.state, "IDLE")

    # -- Stop-loss exit (ATR-based) -----------------------------------------

    def test_exit_stop_loss(self):
        """Price dropping far enough should trigger ATR-based stop-loss SELL."""
        self.graph_mock.evaluate.return_value = True

        # Need 15+ bars with realistic OHLCV for ATR calculation
        bars = _make_bars(20, base_price=50000.0, volatility=200.0)
        self.cell.bars = bars.copy()

        # Enter position (simulating engine flow: handle -> risk -> enter_position)
        entry_result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", 50000.0)
        ))
        self.assertIsNotNone(entry_result)
        self.cell.enter_position(entry_result["price"])
        self.assertEqual(self.cell.state, "IN_POSITION")

        self.graph_mock.evaluate.return_value = False

        # Use an extreme drop that will definitely trigger any stop-loss
        # ATR of ~200 with 2.0 multiplier → stop at ~49600
        crash_price = self.cell.entry_price * 0.70  # 30% drop
        result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", crash_price)
        ))

        self.assertIsNotNone(result, f"Stop-loss should trigger at {crash_price:.2f}")
        self.assertEqual(result["action"], "SELL")
        self.assertEqual(result["symbol"], "BTCUSDT")
        # State stays IN_POSITION until engine calls exit_position()
        self.assertEqual(self.cell.state, "IN_POSITION")
        # Simulate engine flow: after SELL execution, engine calls exit_position()
        self.cell.exit_position()
        self.assertEqual(self.cell.state, "IDLE")

    def test_stop_loss_not_triggered_above_threshold(self):
        """Price above ATR-based stop-loss should NOT trigger exit."""
        self.graph_mock.evaluate.return_value = True
        self.cell.bars = _make_bars(20, base_price=50000.0, volatility=200.0)

        entry_result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", 50000.0)
        ))
        self.assertIsNotNone(entry_result)
        self.cell.enter_position(entry_result["price"])
        self.assertEqual(self.cell.state, "IN_POSITION")

        # Price drops a little but should stay above ATR-based stop-loss
        # ATR ~225 with 2.0 multiplier → stop at ~49550
        self.graph_mock.evaluate.return_value = False
        result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", 49800.0)
        ))

        self.assertIsNone(result)
        self.assertEqual(self.cell.state, "IN_POSITION")

    # -- Take-profit exit (ATR-based) ---------------------------------------

    def test_exit_take_profit(self):
        """Price rising far enough should trigger ATR-based take-profit SELL."""
        self.graph_mock.evaluate.return_value = True
        self.cell.bars = _make_bars(20, base_price=50000.0, volatility=200.0)

        entry_result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", 50000.0)
        ))
        self.assertIsNotNone(entry_result)
        self.cell.enter_position(entry_result["price"])
        self.assertEqual(self.cell.state, "IN_POSITION")

        self.graph_mock.evaluate.return_value = False

        # Use an extreme surge that will definitely trigger take-profit
        # ATR of ~200 with 4.0 multiplier → take-profit at ~50800
        surge_price = self.cell.entry_price * 1.30  # 30% surge
        result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", surge_price)
        ))

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "SELL")
        # State stays IN_POSITION until engine confirms execution
        self.assertEqual(self.cell.state, "IN_POSITION")
        self.cell.exit_position()
        self.assertEqual(self.cell.state, "IDLE")

    # -- Re-entry after exit ------------------------------------------------

    def test_re_entry_after_exit(self):
        """Cell should re-enter after stop-loss when conditions improve."""
        self.graph_mock.evaluate.return_value = True
        self.cell.bars = _make_bars(20, base_price=50000.0, volatility=200.0)

        # Enter (simulating engine flow)
        entry_1 = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", 50000.0)
        ))
        self.assertIsNotNone(entry_1)
        self.cell.enter_position(entry_1["price"])
        self.assertEqual(self.cell.state, "IN_POSITION")

        # Stop-loss exit (aggressive drop)
        self.graph_mock.evaluate.return_value = False
        crash_price = self.cell.entry_price * 0.70  # 30% drop
        exit_result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", crash_price)
        ))
        self.assertIsNotNone(exit_result, "Stop-loss should trigger on 30% drop")
        self.assertEqual(exit_result["action"], "SELL")
        # Simulate engine: after SELL execution, cell resets
        self.cell.exit_position()
        self.assertEqual(self.cell.state, "IDLE")

        # Re-enter
        self.graph_mock.evaluate.return_value = True
        entry_result = self.loop.run_until_complete(self.cell.handle(
            _make_tick_event("BTCUSDT", 49000.0)
        ))

        self.assertIsNotNone(entry_result)
        self.assertEqual(entry_result["action"], "BUY")
        # Simulate engine calling enter_position after risk approval
        self.cell.enter_position(entry_result["price"])
        self.assertEqual(self.cell.state, "IN_POSITION")

    # -- SHORT entry ---------------------------------------------------------

    def test_short_entry_with_config(self):
        """Cell with short_entry config → SHORT signal."""
        self.cell.short_entry_config = {
            "logic": "AND",
            "conditions": [{"indicator": "rsi", "params": {"period": 7}, "operator": "> 70"}],
        }
        short_graph = MagicMock()
        short_graph.evaluate.return_value = True
        self.cell._short_entry_graph = short_graph
        self.cell.bars = _make_bars(25)
        self.graph_mock.evaluate.return_value = False  # ensure _check_entry fails

        event = _make_tick_event("BTCUSDT", 50000.0)
        result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "SHORT")
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertEqual(result["cell_name"], "ema_cross")

    def test_short_entry_without_config(self):
        """Cell without short_entry → _check_short_entry returns None."""
        self.cell.short_entry_config = {}
        self.cell._short_entry_graph = None
        self.cell.bars = _make_bars(25)
        self.graph_mock.evaluate.return_value = False

        event = _make_tick_event("BTCUSDT", 50000.0)
        result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNone(result)
        self.assertEqual(self.cell.state, "IDLE")

    # -- SHORT exit (IN_SHORT state) -----------------------------------------

    def test_short_exit_take_profit(self):
        """IN_SHORT: price drops below inverted TP threshold → BUY."""
        self.cell.state = "IN_SHORT"
        self.cell.entry_price = 30000.0
        self.cell.exit_take_profit = 4.0
        self.cell.bars = _make_bars(25, base_price=30000.0, volatility=200.0)

        # With ATR~200, entry=30000 → atr_pct≈0.0067
        # TP threshold = 30000 * (1 - 4.0 * 0.0067) ≈ 30000 * 0.973 ≈ 29196
        drop_price = 25000.0
        result = self.cell._check_exit(drop_price)

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "BUY")
        self.assertEqual(result["entry_price"], 30000.0)

    def test_short_exit_stop_loss(self):
        """IN_SHORT: price rises above inverted SL threshold → BUY."""
        self.cell.state = "IN_SHORT"
        self.cell.entry_price = 30000.0
        self.cell.exit_stop_loss = 2.0
        self.cell.bars = _make_bars(25, base_price=30000.0, volatility=200.0)

        # With ATR~200, entry=30000 → atr_pct≈0.0067
        # SL threshold = 30000 * (1 + 2.0 * 0.0067) ≈ 30000 * 1.013 ≈ 30402
        surge_price = 33000.0
        result = self.cell._check_exit(surge_price)

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "BUY")

    def test_short_exit_trailing_stop(self):
        """IN_SHORT: trailing_low tracks, exit when price rises above."""
        self.cell.state = "IN_SHORT"
        self.cell.entry_price = 30000.0
        # Isolate trailing test: clear SL/TP so they don't pre-empt
        self.cell.exit_stop_loss = None
        self.cell.exit_take_profit = None
        self.cell.exit_trailing_stop = 2.0
        self.cell._trailing_low = 0.0
        self.cell._trailing_high = 0.0
        self.cell.bars = _make_bars(25, base_price=30000.0, volatility=200.0)

        # First call sets _trailing_low (no exit)
        result = self.cell._check_exit(29000.0)
        self.assertIsNone(result)
        self.assertEqual(self.cell._trailing_low, 29000.0)

        # Price goes lower → _trailing_low updates (still no exit)
        result = self.cell._check_exit(28500.0)
        self.assertIsNone(result)
        self.assertEqual(self.cell._trailing_low, 28500.0)

        # Price rises above _trailing_low + trail_distance → exit
        # trail_distance = 2.0 * atr (~400) → exit at 28500 + 400 = 28900
        result = self.cell._check_exit(29200.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "BUY")
