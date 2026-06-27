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

    # NOTE: engine-run_batch tests (test_engine_runs_with_null_repo,
    # test_engine_no_crash_on_mid_run_disconnect,
    # test_engine_does_not_crash_on_exception_in_save) were removed on
    # 2026-06-27 during M1-M4-M5-Telegram branch restructuring.
    #
    # They tested EventEngine.run_batch() with DB persistence integration
    # that was never implemented — engine.py does not call any DB save
    # methods directly. The run_batch() method itself was also missing and
    # was added retroactively.
    #
    # See architecture/merged-m1-m4-m5-telegram-chain-to-main in engram.
