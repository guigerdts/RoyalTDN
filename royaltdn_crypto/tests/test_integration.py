"""Integration tests for the full CellMesh pipeline.

Tests cover the complete event -> cell -> risk -> broker flow using
real components with mocked cell behaviour.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock


class TestIntegration(unittest.TestCase):
    """Integration test suite for the full pipeline."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # -- Helpers ------------------------------------------------------------

    def _make_tick(self, symbol: str, price: float, **kw) -> dict:
        """Build a standard tick event dict."""
        return {
            "type": "tick",
            "symbol": symbol,
            "price": price,
            "data": {
                "close": price,
                "volume": 100.0,
                "high": price * 1.01,
                "low": price * 0.99,
            },
            **kw,
        }

    # -- Full pipeline ------------------------------------------------------

    def test_full_pipeline(self):
        """Full event -> cell -> risk -> broker flow produces a trade."""
        from core.bus import EventBus
        from core.clock import RealClock
        from core.engine import EventEngine
        from risk.portfolio import Portfolio
        from risk.manager import RiskManager
        from execution.paper_broker import PaperBroker

        bus = EventBus()
        clock = RealClock()
        portfolio = Portfolio(initial_capital=100_000.0)
        risk_manager = RiskManager(portfolio, max_positions=5, max_drawdown=0.03)
        broker = PaperBroker(initial_capital=100_000.0)
        engine = EventEngine(clock, bus, risk_manager, broker)

        # Mock cell that always returns a BUY signal
        cell = MagicMock()
        cell.name = "test_cell"
        cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "qty": 0.01,
            }
        )
        engine.register(cell)

        async def _run():
            task = asyncio.create_task(engine.run())

            # Emit a single tick — one event, one signal, one trade
            await bus.emit(self._make_tick("BTCUSDT", 50000.0))

            await asyncio.sleep(0.1)
            engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # A trade should have been executed
        self.assertEqual(len(broker.trades), 1)
        trade = broker.trades[0]
        self.assertEqual(trade["action"], "BUY")
        self.assertEqual(trade["symbol"], "BTCUSDT")
        self.assertEqual(trade["status"], "filled")

    def test_full_pipeline_trade_updates_portfolio(self):
        """After trade execution, broker portfolio should reflect it."""
        from core.bus import EventBus
        from core.clock import RealClock
        from core.engine import EventEngine
        from risk.portfolio import Portfolio
        from risk.manager import RiskManager
        from execution.paper_broker import PaperBroker

        bus = EventBus()
        clock = RealClock()
        portfolio = Portfolio(initial_capital=100_000.0)
        risk_manager = RiskManager(portfolio, max_positions=5, max_drawdown=0.03)
        broker = PaperBroker(initial_capital=100_000.0)
        engine = EventEngine(clock, bus, risk_manager, broker)

        cell = MagicMock()
        cell.name = "test_cell"
        cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "qty": 0.01,
            }
        )
        engine.register(cell)

        async def _run():
            task = asyncio.create_task(engine.run())
            await bus.emit(self._make_tick("BTCUSDT", 50000.0))
            await asyncio.sleep(0.05)
            engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Broker's portfolio updated
        self.assertEqual(broker.capital, 100_000.0 - 0.01 * 50000.0)
        self.assertIn("BTCUSDT", broker.positions)
        self.assertAlmostEqual(broker.positions["BTCUSDT"], 0.01)

    # -- Multiple cells -----------------------------------------------------

    def test_multiple_cells_different_symbols(self):
        """Multiple cells should each process their own events."""
        from core.bus import EventBus
        from core.clock import RealClock
        from core.engine import EventEngine
        from risk.portfolio import Portfolio
        from risk.manager import RiskManager
        from execution.paper_broker import PaperBroker

        bus = EventBus()
        clock = RealClock()
        portfolio = Portfolio(initial_capital=100_000.0)
        risk_manager = RiskManager(portfolio, max_positions=10, max_drawdown=0.03)
        broker = PaperBroker(initial_capital=100_000.0)
        engine = EventEngine(clock, bus, risk_manager, broker)

        # BTC cell — generates signal
        btc_cell = MagicMock()
        btc_cell.name = "btc_cell"
        btc_cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "qty": 0.01,
            }
        )
        engine.register(btc_cell)

        # ETH cell — no signal
        eth_cell = MagicMock()
        eth_cell.name = "eth_cell"
        eth_cell.handle = AsyncMock(return_value=None)
        engine.register(eth_cell)

        async def _run():
            task = asyncio.create_task(engine.run())
            await bus.emit(self._make_tick("BTCUSDT", 50000.0))
            await asyncio.sleep(0.05)
            engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Both cells called with the event
        btc_cell.handle.assert_called_once()
        eth_cell.handle.assert_called_once()

        # Only BTC trade executed
        self.assertEqual(len(broker.trades), 1)
        self.assertEqual(broker.trades[0]["symbol"], "BTCUSDT")

    def test_multiple_cells_both_generate_signals(self):
        """Two cells generating signals should both produce trades."""
        from core.bus import EventBus
        from core.clock import RealClock
        from core.engine import EventEngine
        from risk.portfolio import Portfolio
        from risk.manager import RiskManager
        from execution.paper_broker import PaperBroker

        bus = EventBus()
        clock = RealClock()
        portfolio = Portfolio(initial_capital=100_000.0)
        risk_manager = RiskManager(portfolio, max_positions=10, max_drawdown=0.03)
        broker = PaperBroker(initial_capital=100_000.0)
        engine = EventEngine(clock, bus, risk_manager, broker)

        btc_cell = MagicMock()
        btc_cell.name = "btc_cell"
        btc_cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "qty": 0.01,
            }
        )
        engine.register(btc_cell)

        eth_cell = MagicMock()
        eth_cell.name = "eth_cell"
        eth_cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "ETHUSDT",
                "price": 3000.0,
                "qty": 1.0,
            }
        )
        engine.register(eth_cell)

        async def _run():
            task = asyncio.create_task(engine.run())

            # Both cells respond to the same first tick -> 2 trades
            await bus.emit(self._make_tick("BTCUSDT", 50000.0))
            await asyncio.sleep(0.05)

            # Stop both cells from signalling on the second tick
            btc_cell.handle.return_value = None
            eth_cell.handle.return_value = None

            await bus.emit(self._make_tick("ETHUSDT", 3000.0))
            await asyncio.sleep(0.05)

            engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Only the 2 trades from the first tick
        self.assertEqual(len(broker.trades), 2)
        symbols = [t["symbol"] for t in broker.trades]
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)

    # -- Risk rejection -----------------------------------------------------

    def test_risk_rejects_signal_when_max_positions_reached(self):
        """Risk manager should reject when max positions are filled."""
        from core.bus import EventBus
        from core.clock import RealClock
        from core.engine import EventEngine
        from risk.portfolio import Portfolio
        from risk.manager import RiskManager
        from execution.paper_broker import PaperBroker

        bus = EventBus()
        clock = RealClock()
        portfolio = Portfolio(initial_capital=100_000.0)
        # Only 1 position allowed
        risk_manager = RiskManager(portfolio, max_positions=1, max_drawdown=0.03)
        broker = PaperBroker(initial_capital=100_000.0)
        engine = EventEngine(clock, bus, risk_manager, broker)

        cell = MagicMock()
        cell.name = "test_cell"

        # First signal: enters BTC
        cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "qty": 0.01,
            }
        )
        engine.register(cell)

        async def _run():
            task = asyncio.create_task(engine.run())

            # First tick — BUY BTC, should be approved
            await bus.emit(self._make_tick("BTCUSDT", 50000.0))
            await asyncio.sleep(0.05)

            # Manually mark position full so risk rejects next signal
            portfolio.positions["BTCUSDT"] = 0.01

            # Second signal — BUY ETH, should be rejected by risk
            cell.handle.return_value = {
                "action": "BUY",
                "symbol": "ETHUSDT",
                "price": 3000.0,
                "qty": 1.0,
            }
            await bus.emit(self._make_tick("ETHUSDT", 3000.0))
            await asyncio.sleep(0.05)

            engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Only BTC trade executed (ETH rejected)
        self.assertEqual(len(broker.trades), 1)
        self.assertEqual(broker.trades[0]["symbol"], "BTCUSDT")

    def test_risk_rejects_signal_when_drawdown_exceeded(self):
        """Risk manager should reject when max drawdown is breached."""
        from core.bus import EventBus
        from core.clock import RealClock
        from core.engine import EventEngine
        from risk.portfolio import Portfolio
        from risk.manager import RiskManager
        from execution.paper_broker import PaperBroker

        bus = EventBus()
        clock = RealClock()
        portfolio = Portfolio(initial_capital=100_000.0)
        portfolio.capital = 96_000.0  # 4% drawdown
        risk_manager = RiskManager(
            portfolio, max_positions=5, max_drawdown=0.03  # 3% max
        )
        broker = PaperBroker(initial_capital=100_000.0)
        engine = EventEngine(clock, bus, risk_manager, broker)

        cell = MagicMock()
        cell.name = "test_cell"
        cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "qty": 0.01,
            }
        )
        engine.register(cell)

        async def _run():
            task = asyncio.create_task(engine.run())
            await bus.emit(self._make_tick("BTCUSDT", 50000.0))
            await asyncio.sleep(0.05)
            engine.stop()
            await task

        self.loop.run_until_complete(_run())

        # Drawdown exceeded, so no trade
        self.assertEqual(len(broker.trades), 0)
