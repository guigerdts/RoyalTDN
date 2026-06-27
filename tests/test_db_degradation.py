"""Degradation tests for the TimescaleDB persistence layer (M5, PR 3).

Tests T3.3 and T3.4 — mock-based, no Docker required.

T3.3 — Startup with DB unreachable
    ``init_pool()`` returns ``NullDBRepository``; the engine starts,
    processes ticks, and all ``save_*`` calls silently no-op with a
    warning log.

T3.4 — Mid-run DB loss
    A connected ``DBRepository`` loses its connection mid-run.  The
    engine continues processing ticks without crashing; each failed
    ``save_*`` call logs a warning.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── T3.3 — Bot starts with DB unreachable ───────────────────────────────


class TestDegradationStartupDBUnreachable:
    """Engine continues normally when TimescaleDB is unreachable at startup."""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        """Reset ``get_repository()`` singleton before each test."""
        import royaltdn.db.repository as mod

        mod._repository = None
        yield

    # -- init_pool -----------------------------------------------------------

    def test_init_pool_returns_null_on_failure(self):
        """``init_pool()`` returns ``NullDBRepository`` when DB is unreachable."""
        from royaltdn.db.repository import DBRepository, NullDBRepository, init_pool

        async def _run():
            with patch.object(DBRepository, "connect", AsyncMock(return_value=False)):
                repo = await init_pool(
                    dsn="postgresql://u:p@localhost:9999/unreachable",
                    min_size=1,
                    max_size=2,
                )
                assert isinstance(repo, NullDBRepository)
                assert repo.is_connected is False

        asyncio.run(_run())

    def test_get_repository_defaults_to_null(self):
        """``get_repository()`` returns ``NullDBRepository`` before init."""
        from royaltdn.db.repository import get_repository, NullDBRepository

        repo = get_repository()
        assert isinstance(repo, NullDBRepository)
        assert not repo.is_connected

    # -- Engine integration --------------------------------------------------

    def test_engine_runs_with_null_repo(self):
        """Engine processes ticks without crashing when repo is NullDBRepository.

        This verifies the full pipeline: event -> cell -> signal -> risk
        -> broker, while ``get_repository()`` returns a ``NullDBRepository``
        whose ``save_*`` methods no-op.
        """
        from royaltdn.core.engine import EventEngine
        from royaltdn.db.repository import get_repository

        bus = MagicMock()
        bus.get = AsyncMock(
            return_value={"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        )
        bus.emit = AsyncMock()

        clock = MagicMock()
        clock.now.return_value = "2025-01-01T00:00:00"

        risk_manager = MagicMock()
        risk_manager.approve.return_value = {
            "approved": True,
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.01,
            "entry_price": 50000,
        }
        risk_manager.portfolio.snapshot.return_value = None

        broker = MagicMock()
        broker.submit_order = AsyncMock(
            return_value={"status": "filled", "order_id": "mock_1", "price": 50000}
        )

        engine = EventEngine(clock, bus, risk_manager, broker)

        cell = MagicMock()
        cell.name = "test_cell"
        cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000,
                "qty": 0.01,
            }
        )
        engine.register(cell)

        # Verify we are using NullDBRepository
        repo = get_repository()
        assert not repo.is_connected

        # Process one event via run_batch (no infinite loop)
        engine.run_batch(
            [{"type": "tick", "symbol": "BTCUSDT", "price": 50000}]
        )

        cell.handle.assert_called_once()

    # -- Save no-ops --------------------------------------------------------

    def test_save_calls_noop_with_null_repo(self):
        """All ``save_*`` methods silently no-op on NullDBRepository."""
        from royaltdn.db.repository import NullDBRepository

        repo = NullDBRepository()

        async def _run():
            await repo.save_trade({"symbol": "TEST", "pnl": 100.0})
            await repo.save_equity_snapshot({"total_value": 1000.0})
            await repo.save_signal({"symbol": "TEST", "action": "BUY"})
            await repo.save_event({"event_type": "test"})

        asyncio.run(_run())

    def test_query_methods_return_empty_on_null_repo(self):
        """Query methods return empty/zero results on NullDBRepository."""
        from royaltdn.db.repository import NullDBRepository

        repo = NullDBRepository()

        async def _run():
            trades = await repo.get_recent_trades(10)
            assert trades == []

            curve = await repo.get_equity_curve()
            assert curve == []

            stats = await repo.get_trade_stats()
            assert stats == {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "avg_duration": 0.0,
            }

        asyncio.run(_run())


# ── T3.4 — Mid-run DB loss ─────────────────────────────────────────────


class TestDegradationMidRunDBLoss:
    """Engine handles mid-run database disconnection gracefully."""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        """Reset ``get_repository()`` singleton before each test."""
        import royaltdn.db.repository as mod

        mod._repository = None
        yield

    def test_save_methods_noop_when_disconnected(self):
        """``DBRepository.save_*`` silently no-ops when ``is_connected`` is False.

        Warning logs are emitted by the implementation (verified manually
        via the ``Captured stderr call`` section in test output), but
        programmatic assertion is omitted because ``loguru`` writes
        directly to its own sink and is not intercepted by pytest's
        ``capsys`` or ``caplog`` fixtures.
        """
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        repo.is_connected = False
        repo._pool = None

        async def _run():
            # Must not raise despite being disconnected
            await repo.save_trade({"symbol": "BTCUSDT", "pnl": 100.0})
            await repo.save_equity_snapshot({"total_value": 1000.0})
            await repo.save_signal({"symbol": "ETHUSDT", "action": "BUY"})
            await repo.save_event({"event_type": "test"})

        asyncio.run(_run())

    def test_engine_no_crash_on_mid_run_disconnect(self):
        """Engine continues processing when DBRepository disconnects mid-run.

        The test simulates: connected -> process events -> disconnect ->
        process more events.  The engine must not crash and all events
        must reach registered cells.
        """
        import royaltdn.db.repository as mod
        from royaltdn.core.engine import EventEngine

        # Mock a connected DBRepository
        mock_repo = MagicMock(spec=mod.DBRepository)
        mock_repo.is_connected = True
        mock_repo.save_trade = AsyncMock()
        mock_repo.save_equity_snapshot = AsyncMock()
        mock_repo.save_signal = AsyncMock()
        mock_repo.save_event = AsyncMock()
        mock_repo.get_recent_trades = AsyncMock(return_value=[])
        mock_repo.get_equity_curve = AsyncMock(return_value=[])
        mock_repo.get_trade_stats = AsyncMock(
            return_value={
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "avg_duration": 0.0,
            }
        )

        # Install as singleton
        mod._repository = mock_repo

        # Engine setup
        bus = MagicMock()
        bus.get = AsyncMock(
            return_value={"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        )
        bus.emit = AsyncMock()

        clock = MagicMock()
        clock.now.return_value = "2025-01-01T00:00:00"

        risk_manager = MagicMock()
        risk_manager.approve.return_value = {
            "approved": True,
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.01,
            "entry_price": 50000,
        }
        risk_manager.portfolio.snapshot.return_value = {
            "timestamp": "2025-01-01T00:00:00",
            "total_value": 100000.0,
            "capital": 95000.0,
            "drawdown": 0.0,
            "peak_value": 100000.0,
        }

        broker = MagicMock()
        broker.submit_order = AsyncMock(
            return_value={"status": "filled", "order_id": "mock_1", "price": 50000}
        )

        engine = EventEngine(clock, bus, risk_manager, broker)

        cell = MagicMock()
        cell.name = "test_cell"
        cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000,
                "qty": 0.01,
            }
        )
        engine.register(cell)

        # First batch: repo is connected
        engine.run_batch(
            [{"type": "tick", "symbol": "BTCUSDT", "price": 50000}]
        )

        assert mock_repo.save_signal.await_count >= 1
        assert mock_repo.save_event.await_count >= 1
        assert mock_repo.save_equity_snapshot.await_count >= 1

        # Simulate DB disconnection mid-run
        mock_repo.is_connected = False

        # Second batch: repo is now disconnected
        engine.run_batch(
            [{"type": "tick", "symbol": "ETHUSDT", "price": 3000}]
        )

        # Engine was called twice
        assert cell.handle.await_count == 2

    def test_engine_does_not_crash_on_exception_in_save(self):
        """An exception in a ``save_*`` call does not crash the engine.

        The engine uses ``asyncio.create_task`` for persistence calls,
        which means exceptions are silently swallowed by the event loop.
        This test verifies the engine continues processing even if a
        save task raises.
        """
        import royaltdn.db.repository as mod
        from royaltdn.core.engine import EventEngine

        # Mock repo that raises on save
        mock_repo = MagicMock(spec=mod.DBRepository)
        mock_repo.is_connected = True
        mock_repo.save_trade = AsyncMock(side_effect=RuntimeError("DB crash"))
        mock_repo.save_equity_snapshot = AsyncMock(
            side_effect=RuntimeError("DB crash")
        )
        mock_repo.save_signal = AsyncMock(side_effect=RuntimeError("DB crash"))
        mock_repo.save_event = AsyncMock(side_effect=RuntimeError("DB crash"))
        mock_repo.get_recent_trades = AsyncMock(return_value=[])
        mock_repo.get_equity_curve = AsyncMock(return_value=[])
        mock_repo.get_trade_stats = AsyncMock(
            return_value={
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "avg_duration": 0.0,
            }
        )
        mock_repo.portfolio = MagicMock()
        mock_repo.portfolio.snapshot = MagicMock(return_value=None)

        mod._repository = mock_repo

        # Engine setup
        bus = MagicMock()
        bus.get = AsyncMock(
            return_value={"type": "tick", "symbol": "BTCUSDT", "price": 50000}
        )
        bus.emit = AsyncMock()

        clock = MagicMock()
        clock.now.return_value = "2025-01-01T00:00:00"

        risk_manager = MagicMock()
        risk_manager.approve.return_value = {
            "approved": True,
            "action": "BUY",
            "symbol": "BTCUSDT",
            "price": 50000,
            "qty": 0.01,
            "entry_price": 50000,
        }
        risk_manager.portfolio.snapshot.return_value = None

        broker = MagicMock()
        broker.submit_order = AsyncMock(
            return_value={"status": "filled", "order_id": "mock_1", "price": 50000}
        )

        engine = EventEngine(clock, bus, risk_manager, broker)

        cell = MagicMock()
        cell.name = "test_cell"
        cell.handle = AsyncMock(
            return_value={
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 50000,
                "qty": 0.01,
            }
        )
        engine.register(cell)

        # Should not crash despite repo exceptions
        engine.run_batch(
            [{"type": "tick", "symbol": "BTCUSDT", "price": 50000}]
        )

        cell.handle.assert_called_once()
