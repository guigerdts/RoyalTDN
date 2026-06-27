"""Unit tests for the EventEngine.

Tests cover cell registration, event processing, the full signal
pipeline, risk rejection, and bus event emission.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock


class MockBus:
    """Mock EventBus with a controllable event stream."""

    def __init__(self, events: list | None = None) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.emitted: list[dict] = []
        if events:
            for e in events:
                self.queue.put_nowait(e)

    async def emit(self, event: dict) -> None:
        self.emitted.append(event)

    async def get(self) -> dict:
        return await self.queue.get()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        return q


class MockCell:
    """Mock cell with controllable signal output."""

    def __init__(self, name: str = "test_cell", symbol: str = "BTCUSDT") -> None:
        self.name = name
        self.symbol = symbol
        self.handle = AsyncMock(return_value=None)


class TestEventEngine(unittest.TestCase):
    """Test suite for EventEngine."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.bus = MockBus()
        self.clock = MagicMock()
        self.clock.now.return_value = "2025-01-01T00:00:00"
        self.risk_manager = MagicMock()
        self.risk_manager.approve.return_value = None
        self.broker = MagicMock()
        self.broker.submit_order = AsyncMock(
            return_value={"status": "filled", "order_id": "mock_1"}
        )

        from royaltdn.core.engine import EventEngine

        self.engine = EventEngine(self.clock, self.bus, self.risk_manager, self.broker)

    def tearDown(self):
        self.loop.close()

    # -- Registration -------------------------------------------------------

    def test_register_cell(self):
        """Engine should store a registered cell."""
        cell = MockCell()
        self.engine.register(cell)
        self.assertIn(cell, self.engine.cells)
        self.assertEqual(len(self.engine.cells), 1)

    def test_register_multiple_cells(self):
        """Engine should store all registered cells."""
        cell_a = MockCell(name="cell_a")
        cell_b = MockCell(name="cell_b")
        self.engine.register(cell_a)
        self.engine.register(cell_b)
        self.assertEqual(len(self.engine.cells), 2)

    # -- Event processing ---------------------------------------------------

    def test_event_processing(self):
        """Engine should feed events to registered cells."""
        cell = MockCell()
        self.engine.register(cell)

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())
        cell.handle.assert_awaited_once_with(event)

    def test_event_processing_all_cells_receive_event(self):
        """All registered cells should receive every event."""
        cell_a = MockCell(name="cell_a")
        cell_b = MockCell(name="cell_b")
        self.engine.register(cell_a)
        self.engine.register(cell_b)

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        cell_a.handle.assert_awaited_once_with(event)
        cell_b.handle.assert_awaited_once_with(event)

    # -- Signal flow --------------------------------------------------------

    def test_signal_flow(self):
        """Event -> cell -> signal -> risk -> broker pipeline."""
        cell = MockCell()
        signal = {
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.01,
        }
        cell.handle = AsyncMock(return_value=signal)
        self.engine.register(cell)

        approved_signal = {"approved": True, **signal}
        self.risk_manager.approve.return_value = approved_signal

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        self.risk_manager.approve.assert_called_once_with(signal)
        self.broker.submit_order.assert_awaited_once_with(approved_signal)

    def test_signal_rejected_by_risk(self):
        """Risk rejection should stop pipeline before broker."""
        cell = MockCell()
        signal = {
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.01,
        }
        cell.handle = AsyncMock(return_value=signal)
        self.engine.register(cell)

        self.risk_manager.approve.return_value = None  # reject

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        self.risk_manager.approve.assert_called_once_with(signal)
        self.broker.submit_order.assert_not_awaited()

    def test_engine_emits_signal_and_trade_events(self):
        """Engine should emit signal and trade events to the bus."""
        cell = MockCell()
        signal = {
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.01,
        }
        cell.handle = AsyncMock(return_value=signal)
        self.engine.register(cell)

        self.risk_manager.approve.return_value = {"approved": True, **signal}

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        emitted_types = [e["type"] for e in self.bus.emitted]
        self.assertIn("signal", emitted_types)
        self.assertIn("trade", emitted_types)

    def test_cell_exception_does_not_stop_engine(self):
        """A cell exception should be caught; engine continues."""
        good_cell = MockCell(name="good")
        bad_cell = MockCell(name="bad")
        bad_cell.handle.side_effect = ValueError("boom")
        self.engine.register(bad_cell)
        self.engine.register(good_cell)

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Both cells should have been called
        bad_cell.handle.assert_awaited_once_with(event)
        good_cell.handle.assert_awaited_once_with(event)

    # -- SHORT pipeline -------------------------------------------------------

    def test_short_pipeline(self):
        """SHORT signal → enter_position(direction='short') → broker → journal."""
        cell = MockCell()
        signal = {
            "action": "SHORT",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.01,
            "entry_price": 50000,
        }
        cell.handle = AsyncMock(return_value=signal)
        # Add enter_position so engine can call it
        cell.enter_position = MagicMock()
        cell.exit_position = MagicMock()
        cell.state = "IDLE"
        self.engine.register(cell)

        approved_signal = {"approved": True, **signal}
        self.risk_manager.approve.return_value = approved_signal

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Should call enter_position with direction="short"
        cell.enter_position.assert_called_once_with(50000, direction="short")
        self.broker.submit_order.assert_awaited_once()

    def test_short_pipeline_broker_and_portfolio(self):
        """SHORT signal should update broker portfolio and risk portfolio."""
        from royaltdn.risk.portfolio import Portfolio

        # Create real portfolio
        portfolio = Portfolio(initial_capital=100_000.0)
        self.risk_manager.portfolio = portfolio

        cell = MockCell()
        signal = {
            "action": "SHORT",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.02,
            "sizing": 0.01,
            "entry_price": 50000,
        }
        cell.handle = AsyncMock(return_value=signal)
        cell.enter_position = MagicMock()
        cell.exit_position = MagicMock()
        cell.state = "IDLE"
        self.engine.register(cell)

        approved_signal = {"approved": True, **signal}
        self.risk_manager.approve.return_value = approved_signal

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Risk portfolio should have the short
        assert "BTCUSDT" in portfolio._short_positions
        assert portfolio._short_positions["BTCUSDT"] == 0.02

    # -- BUY-to-close pipeline ------------------------------------------------

    def test_buy_to_close_pipeline(self):
        """BUY signal when IN_SHORT → close position → journal short PnL."""
        cell = MockCell()
        signal = {
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 25000,
            "qty": 0.01,
            "entry_price": 30000,
        }
        cell.handle = AsyncMock(return_value=signal)
        cell.enter_position = MagicMock()
        cell.exit_position = MagicMock()
        cell.state = "IN_SHORT"  # Cell is in SHORT, so BUY is a close
        cell.name = "test_cell"
        self.engine.register(cell)

        approved_signal = {"approved": True, **signal}
        self.risk_manager.approve.return_value = approved_signal

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 25000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Should NOT call enter_position (it's a close, not entry)
        # Instead should call exit_position
        cell.exit_position.assert_called_once()

    def test_buy_to_close_does_not_enter_position(self):
        """BUY-to-close should NOT call enter_position()."""
        cell = MockCell()
        signal = {
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 25000,
            "qty": 0.01,
            "entry_price": 30000,
        }
        cell.handle = AsyncMock(return_value=signal)
        cell.enter_position = MagicMock()
        cell.exit_position = MagicMock()
        cell.state = "IN_SHORT"
        cell.name = "test_cell"
        self.engine.register(cell)

        approved_signal = {"approved": True, **signal}
        self.risk_manager.approve.return_value = approved_signal

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 25000}
        self.bus.queue.put_nowait(event)

        async def _run():
            task = asyncio.create_task(self.engine.run())
            await asyncio.sleep(0.05)
            self.engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # enter_position should NOT be called for buy-to-close
        cell.enter_position.assert_not_called()
