"""Unit tests for the Cell class.

Tests cover initialisation, symbol filtering, entry/exit condition
evaluation, stop-loss, and take-profit behaviour.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock


class TestCell(unittest.TestCase):
    """Test suite for the Cell autonomous trading cell."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.config = {
            "name": "ema_cross",
            "symbol": "BTCUSDT",
            "qty": 0.01,
            "stop_loss": 0.02,
            "take_profit": 0.05,
            "entry": {
                "conditions": [
                    {
                        "indicator": "rsi",
                        "params": {"period": 7},
                        "operator": "< 30",
                    }
                ]
            },
        }
        self.mock_engine = MagicMock()

        from cells.base import Cell

        self.cell = Cell(self.config, inference_engine=self.mock_engine)

    def tearDown(self):
        self.loop.close()

    # -- Initialisation -----------------------------------------------------

    def test_init(self):
        """Cell should initialise with config values, state IDLE."""
        self.assertEqual(self.cell.name, "ema_cross")
        self.assertEqual(self.cell.symbol, "BTCUSDT")
        self.assertEqual(self.cell.state, "IDLE")
        self.assertEqual(self.cell.qty, 0.01)
        self.assertEqual(self.cell.stop_loss_pct, 0.02)
        self.assertEqual(self.cell.take_profit_pct, 0.05)

    def test_init_defaults(self):
        """Cell should use sensible defaults for missing config keys."""
        from cells.base import Cell

        minimal = Cell({"name": "minimal", "symbol": "ETHUSDT"})
        self.assertEqual(minimal.name, "minimal")
        self.assertEqual(minimal.symbol, "ETHUSDT")
        self.assertEqual(minimal.state, "IDLE")
        self.assertEqual(minimal.qty, 0.01)
        self.assertEqual(minimal.stop_loss_pct, 0.0)
        self.assertEqual(minimal.take_profit_pct, 0.0)

    # -- Symbol filtering ---------------------------------------------------

    def test_handle_wrong_symbol_returns_none(self):
        """Event with different symbol should be ignored."""
        event = {"type": "tick", "symbol": "ETHUSDT", "price": 3000}
        result = self.loop.run_until_complete(self.cell.handle(event))
        self.assertIsNone(result)

    def test_handle_correct_symbol_processes(self):
        """Event with matching symbol should be processed."""
        self.mock_engine.evaluate.return_value = False
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
        self.mock_engine.evaluate.return_value = True

        result = None
        for i in range(10):
            event = {
                "type": "tick",
                "symbol": "BTCUSDT",
                "price": 50000.0 + i,
                "data": {
                    "close": 50000.0 + i,
                    "volume": 100.0,
                    "high": 50100.0,
                    "low": 49900.0,
                },
            }
            r = self.loop.run_until_complete(self.cell.handle(event))
            if r is not None:
                result = r

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "BUY")
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertEqual(result["qty"], 0.01)
        self.assertEqual(self.cell.state, "IN_POSITION")
        self.assertGreater(self.cell.entry_price, 0)

    def test_entry_conditions_not_met(self):
        """When entry conditions are not met, handle should return None."""
        self.mock_engine.evaluate.return_value = False

        for i in range(15):
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
        from cells.base import Cell

        no_engine_cell = Cell(self.config, inference_engine=None)

        for i in range(10):
            event = {
                "type": "tick",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "data": {"close": 50000.0, "volume": 100.0},
            }
            result = self.loop.run_until_complete(no_engine_cell.handle(event))
            self.assertIsNone(result)

        self.assertEqual(no_engine_cell.state, "IDLE")

    # -- Stop-loss exit -----------------------------------------------------

    def test_exit_stop_loss(self):
        """Price dropping below stop-loss should trigger SELL signal."""
        # Enter position
        self.mock_engine.evaluate.return_value = True

        for i in range(5):
            event = {
                "type": "tick",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "data": {"close": 50000.0, "volume": 100.0},
            }
            self.loop.run_until_complete(self.cell.handle(event))

        self.assertEqual(self.cell.state, "IN_POSITION")
        self.assertEqual(self.cell.entry_price, 50000.0)

        # Price drops below 2% stop-loss (49000)
        self.mock_engine.evaluate.return_value = False  # dont re-enter
        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 48000.0,
            "data": {"close": 48000.0, "volume": 100.0},
        }
        result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "SELL")
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertEqual(self.cell.state, "IDLE")

    def test_stop_loss_not_triggered_above_threshold(self):
        """Price above stop-loss should NOT trigger exit."""
        self.mock_engine.evaluate.return_value = True

        for i in range(5):
            event = {
                "type": "tick",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "data": {"close": 50000.0, "volume": 100.0},
            }
            self.loop.run_until_complete(self.cell.handle(event))

        # Price drops but stays above stop-loss (49000)
        self.mock_engine.evaluate.return_value = False
        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 49500.0,
            "data": {"close": 49500.0, "volume": 100.0},
        }
        result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNone(result)
        self.assertEqual(self.cell.state, "IN_POSITION")

    # -- Take-profit exit ---------------------------------------------------

    def test_exit_take_profit(self):
        """Price rising above take-profit should trigger SELL signal."""
        self.mock_engine.evaluate.return_value = True

        for i in range(5):
            event = {
                "type": "tick",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "data": {"close": 50000.0, "volume": 100.0},
            }
            self.loop.run_until_complete(self.cell.handle(event))

        self.assertEqual(self.cell.state, "IN_POSITION")

        # Price rises above 5% take-profit (52500)
        self.mock_engine.evaluate.return_value = False
        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 53000.0,
            "data": {"close": 53000.0, "volume": 100.0},
        }
        result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "SELL")
        self.assertEqual(self.cell.state, "IDLE")

    # -- Re-entry after exit ------------------------------------------------

    def test_re_entry_after_exit(self):
        """Cell should re-enter after stop-loss when conditions improve."""
        self.mock_engine.evaluate.return_value = True

        # Enter
        for i in range(3):
            event = {
                "type": "tick",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "data": {"close": 50000.0, "volume": 100.0},
            }
            self.loop.run_until_complete(self.cell.handle(event))

        self.assertEqual(self.cell.state, "IN_POSITION")

        # Stop-loss exit
        self.mock_engine.evaluate.return_value = False
        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 48000.0,
            "data": {"close": 48000.0, "volume": 100.0},
        }
        exit_result = self.loop.run_until_complete(self.cell.handle(event))
        self.assertEqual(exit_result["action"], "SELL")
        self.assertEqual(self.cell.state, "IDLE")

        # Re-enter
        self.mock_engine.evaluate.return_value = True
        event = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "price": 49000.0,
            "data": {"close": 49000.0, "volume": 100.0},
        }
        entry_result = self.loop.run_until_complete(self.cell.handle(event))

        self.assertIsNotNone(entry_result)
        self.assertEqual(entry_result["action"], "BUY")
        self.assertEqual(self.cell.state, "IN_POSITION")
