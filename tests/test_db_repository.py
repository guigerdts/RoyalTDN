"""Unit tests for the TimescaleDB repository layer (M5).

Covers:
- ``NullDBRepository`` — all methods are no-ops
- ``DBRepository`` — mocked ``asyncpg.Pool``, verify SQL + params for saves
- ``DBRepository`` — mocked queries (get_recent_trades, get_equity_curve,
  get_trade_stats)
- ``get_repository()`` — singleton factory, default NullDBRepository
- ``init_pool()`` — failure path returns NullDBRepository
- ``_build_dsn()`` — DSN construction from env vars
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


def _make_fake_pool(return_value: object = None) -> AsyncMock:
    """Build a fake asyncpg pool that returns *return_value* on execute."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=return_value)
    conn.fetch = AsyncMock(return_value=return_value or [])
    conn.fetchrow = AsyncMock(return_value=return_value or {})

    pool = AsyncMock()
    pool.acquire = AsyncMock(return_value=conn)
    pool.__aenter__ = AsyncMock(return_value=pool)
    pool.__aexit__ = AsyncMock(return_value=None)
    # Make pool.acquire() work as an async context manager
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)

    return pool


# ── NullDBRepository ───────────────────────────────────────────────────


class TestNullDBRepository:
    """All NullDBRepository methods must be silent no-ops."""

    @pytest.fixture
    def repo(self):
        from royaltdn.db.repository import NullDBRepository

        return NullDBRepository()

    def test_connect_returns_false(self, repo) -> None:
        """connect() should always return False."""
        import asyncio

        assert asyncio.run(repo.connect()) is False

    def test_is_connected_false(self, repo) -> None:
        """is_connected should always be False."""
        assert repo.is_connected is False

    def test_close_noop(self, repo) -> None:
        """close() should not raise."""
        import asyncio

        asyncio.run(repo.close())  # must not raise

    def test_save_trade_noop(self, repo) -> None:
        """save_trade should not raise."""
        import asyncio

        asyncio.run(repo.save_trade({"symbol": "TEST"}))  # must not raise

    def test_save_equity_snapshot_noop(self, repo) -> None:
        """save_equity_snapshot should not raise."""
        import asyncio

        asyncio.run(repo.save_equity_snapshot({"total_value": 1000.0}))

    def test_save_signal_noop(self, repo) -> None:
        """save_signal should not raise."""
        import asyncio

        asyncio.run(repo.save_signal({"symbol": "TEST", "action": "BUY"}))

    def test_save_event_noop(self, repo) -> None:
        """save_event should not raise."""
        import asyncio

        asyncio.run(repo.save_event({"event_type": "test"}))

    def test_get_recent_trades_empty(self, repo) -> None:
        """get_recent_trades should return empty list."""
        import asyncio

        result = asyncio.run(repo.get_recent_trades(10))
        assert result == []

    def test_get_equity_curve_empty(self, repo) -> None:
        """get_equity_curve should return empty list."""
        import asyncio

        result = asyncio.run(repo.get_equity_curve("2025-01-01", "2025-12-31"))
        assert result == []

    def test_get_trade_stats_zeroes(self, repo) -> None:
        """get_trade_stats should return zero-valued dict."""
        import asyncio

        result = asyncio.run(repo.get_trade_stats())
        assert result == {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "avg_duration": 0.0,
        }


# ── DBRepository — save methods ────────────────────────────────────────


class TestDBRepositorySave:
    """DBRepository save methods must construct correct SQL and parameters."""

    def _prepare_connected(self) -> tuple[Any, AsyncMock]:
        """Create a repo with a fake pool, mark connected.  Returns (repo, pool)."""
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        pool = _make_fake_pool()
        repo._pool = pool
        repo.is_connected = True
        return repo, pool

    # -- save_trade ----------------------------------------------------------

    def test_save_trade_inserts_all_fields(self) -> None:
        """save_trade should execute INSERT with mapped columns."""
        import asyncio

        repo, pool = self._prepare_connected()

        trade = {
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry_price": 30000.0,
            "exit_price": 32000.0,
            "qty": 0.1,
            "pnl": 200.0,
            "pnl_pct": 6.6667,
            "strategy_name": "swing_1",
            "entry_time": "2025-01-01T10:00:00Z",
            "exit_time": "2025-01-01T12:00:00Z",
            "duration_seconds": 7200.0,
            "exit_reason": "signal",
            "fees": 1.50,
        }

        asyncio.run(repo.save_trade(trade))

        # Verify the pool and SQL were called correctly
        cm = pool.acquire.return_value
        conn = asyncio.run(cm.__aenter__())
        conn.execute.assert_called_once()
        args = conn.execute.call_args
        sql, *params = args[0]
        assert "INSERT INTO trades" in sql
        assert params[0] == "BTCUSDT"  # symbol
        assert params[1] == "long"     # direction → side
        assert params[2] == 30000.0    # entry_price
        assert params[12] == "swing_1"  # strategy_name → strategy

    def test_save_trade_noop_when_disconnected(self) -> None:
        """save_trade must silently no-op when is_connected is False."""
        import asyncio
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        repo.is_connected = False
        repo._pool = None

        # Should not raise even though pool is None
        asyncio.run(repo.save_trade({"symbol": "TEST", "pnl": 100.0}))

    # -- save_equity_snapshot -----------------------------------------------

    def test_save_equity_snapshot_inserts_fields(self) -> None:
        """save_equity_snapshot should insert into equity_snapshots."""
        import asyncio

        repo, pool = self._prepare_connected()

        state = {
            "timestamp": "2025-01-01T10:00:00Z",
            "total_value": 105000.0,
            "capital": 95000.0,
            "drawdown": 0.05,
            "peak_value": 110000.0,
        }

        asyncio.run(repo.save_equity_snapshot(state))

        cm = pool.acquire.return_value
        conn = asyncio.run(cm.__aenter__())
        conn.execute.assert_called_once()
        args = conn.execute.call_args
        sql = args[0][0]
        assert "INSERT INTO equity_snapshots" in sql

    # -- save_signal --------------------------------------------------------

    def test_save_signal_inserts_with_mapped_action(self) -> None:
        """save_signal should map BUY->1, SELL->-1, SHORT->-1."""
        import asyncio

        repo, pool = self._prepare_connected()

        signal = {
            "timestamp": "2025-01-01T10:00:00Z",
            "cell_name": "swing_1",
            "symbol": "BTCUSDT",
            "action": "BUY",
            "approved": True,
            "price": 30000.0,
            "qty": 0.1,
            "metadata": '{"cell_name": "swing_1", "approved": true}',
        }

        asyncio.run(repo.save_signal(signal))

        cm = pool.acquire.return_value
        conn = asyncio.run(cm.__aenter__())
        conn.execute.assert_called_once()
        args = conn.execute.call_args
        sql, *params = args[0]
        assert "INSERT INTO signals" in sql
        assert params[2] == 1  # BUY -> 1

    def test_save_signal_sell_maps_to_minus_one(self) -> None:
        """SELL should map to signal int -1."""
        import asyncio

        repo, pool = self._prepare_connected()

        asyncio.run(repo.save_signal({
            "timestamp": "2025-01-01T10:00:00Z",
            "symbol": "AAPL",
            "action": "SELL",
            "price": 150.0,
        }))

        cm = pool.acquire.return_value
        conn = asyncio.run(cm.__aenter__())
        conn.execute.assert_called_once()
        args = conn.execute.call_args
        # Positional args: (sql, timestamp, symbol, signal_int, price, metadata)
        assert args[0][3] == -1  # SELL -> -1

    def test_save_signal_unknown_action_maps_to_zero(self) -> None:
        """Unknown action should map to 0."""
        import asyncio

        repo, pool = self._prepare_connected()

        asyncio.run(repo.save_signal({
            "timestamp": "2025-01-01T10:00:00Z",
            "symbol": "AAPL",
            "action": "HOLD",
            "price": 150.0,
        }))

        cm = pool.acquire.return_value
        conn = asyncio.run(cm.__aenter__())
        conn.execute.assert_called_once()
        args = conn.execute.call_args
        # Positional args: (sql, timestamp, symbol, signal_int, price, metadata)
        assert args[0][3] == 0  # HOLD -> 0

    # -- save_event ---------------------------------------------------------

    def test_save_event_inserts_into_system_events(self) -> None:
        """save_event should insert into system_events with JSONB data."""
        import asyncio

        repo, pool = self._prepare_connected()

        event = {
            "timestamp": "2025-01-01T10:00:00Z",
            "event_type": "risk_rejection",
            "symbol": "BTCUSDT",
            "data": {"reason": "max_drawdown_exceeded", "drawdown": 0.12},
        }

        asyncio.run(repo.save_event(event))

        cm = pool.acquire.return_value
        conn = asyncio.run(cm.__aenter__())
        conn.execute.assert_called_once()
        args = conn.execute.call_args
        sql = args[0][0]
        assert "INSERT INTO system_events" in sql

    # -- save no-ops when disconnected --------------------------------------

    def test_all_saves_noop_when_disconnected(self) -> None:
        """Every save method no-ops when is_connected is False."""
        import asyncio
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        repo.is_connected = False
        repo._pool = None

        asyncio.run(repo.save_trade({"symbol": "T"}))
        asyncio.run(repo.save_equity_snapshot({"total_value": 1.0}))
        asyncio.run(repo.save_signal({"symbol": "T", "action": "BUY"}))
        asyncio.run(repo.save_event({"event_type": "t"}))
        # All must complete without error and without calling any pool method


# ── DBRepository — query methods ───────────────────────────────────────


class TestDBRepositoryQueries:
    """Query methods must return data from the pool or empty on failure."""

    def test_get_recent_trades_disconnected(self) -> None:
        """get_recent_trades must return [] when not connected."""
        import asyncio
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        repo.is_connected = False
        result = asyncio.run(repo.get_recent_trades(10))
        assert result == []

    def test_get_equity_curve_disconnected(self) -> None:
        """get_equity_curve must return [] when not connected."""
        import asyncio
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        repo.is_connected = False
        result = asyncio.run(repo.get_equity_curve("2025-01-01", "2025-12-31"))
        assert result == []

    def test_get_trade_stats_disconnected(self) -> None:
        """get_trade_stats must return zeroed dict when not connected."""
        import asyncio
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        repo.is_connected = False
        result = asyncio.run(repo.get_trade_stats())
        assert result == {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "avg_duration": 0.0,
        }

    def test_get_recent_trades_ordering(self) -> None:
        """get_recent_trades must ORDER BY exit_at DESC and LIMIT."""
        import asyncio
        from royaltdn.db.repository import DBRepository

        repo = DBRepository(dsn="postgresql://u:p@h:5432/db")
        fake_rows = [
            {"id": 1, "symbol": "BTCUSDT", "direction": "long", "pnl": 200.0},
            {"id": 2, "symbol": "ETHUSDT", "direction": "short", "pnl": -50.0},
        ]
        pool = _make_fake_pool(fake_rows)
        repo._pool = pool
        repo.is_connected = True

        result = asyncio.run(repo.get_recent_trades(limit=2))

        assert len(result) == 2
        assert result[0]["symbol"] == "BTCUSDT"


# ── Factory ─────────────────────────────────────────────────────────────


class TestGetRepository:
    """get_repository() factory behaviour."""

    def test_default_is_null(self) -> None:
        """Before init_pool(), get_repository() returns NullDBRepository."""
        # Reset the singleton between tests
        import royaltdn.db.repository as mod

        mod._repository = None
        from royaltdn.db.repository import get_repository

        repo = get_repository()
        from royaltdn.db.repository import NullDBRepository

        assert isinstance(repo, NullDBRepository)

    def test_singleton_returns_same_instance(self) -> None:
        """get_repository() must return the same instance on subsequent calls."""
        import royaltdn.db.repository as mod

        mod._repository = None
        from royaltdn.db.repository import get_repository

        r1 = get_repository()
        r2 = get_repository()
        assert r1 is r2

    def test_never_returns_none(self) -> None:
        """get_repository() must never return None."""
        import royaltdn.db.repository as mod

        mod._repository = None
        from royaltdn.db.repository import get_repository

        repo = get_repository()
        assert repo is not None


# ── init_pool ──────────────────────────────────────────────────────────


class TestInitPool:
    """init_pool() startup behaviour."""

    def test_returns_null_on_failure(self) -> None:
        """When DB is unreachable, init_pool() must return NullDBRepository."""
        import asyncio
        from royaltdn.db.repository import init_pool, NullDBRepository, DBRepository

        async def _run() -> None:
            with patch.object(DBRepository, "connect", AsyncMock(return_value=False)):
                repo = await init_pool(dsn="postgresql://u:p@h:5432/db")
                assert isinstance(repo, NullDBRepository)

        asyncio.run(_run())

    def test_returns_db_repo_on_success(self) -> None:
        """When DB is reachable, init_pool() must return DBRepository."""
        import asyncio
        from royaltdn.db.repository import init_pool, DBRepository

        async def _run() -> None:
            with patch.object(DBRepository, "connect", AsyncMock(return_value=True)):
                repo = await init_pool(dsn="postgresql://u:p@h:5432/db", min_size=1, max_size=2)
                assert isinstance(repo, DBRepository)

        asyncio.run(_run())


# ── DSN builder ────────────────────────────────────────────────────────


class TestBuildDSN:
    """_build_dsn() must construct correct DSNs from env vars."""

    def test_defaults_when_no_env(self) -> None:
        """Without any env vars, return localhost defaults."""
        from royaltdn.db.repository import _build_dsn

        with patch.dict(os.environ, {}, clear=True):
            dsn = _build_dsn()
            assert dsn == "postgresql://botuser:botpassword@localhost:5432/trading_bot"

    def test_env_vars_override_defaults(self) -> None:
        """DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME override defaults."""
        from royaltdn.db.repository import _build_dsn

        with patch.dict(os.environ, {
            "DB_HOST": "timescaledb",
            "DB_PORT": "5555",
            "DB_USER": "admin",
            "DB_PASSWORD": "secret123",
            "DB_NAME": "royaltdn",
        }, clear=True):
            dsn = _build_dsn()
            assert dsn == "postgresql://admin:secret123@timescaledb:5555/royaltdn"

    def test_fallback_to_database_url(self) -> None:
        """When DATABASE_URL is set, use it directly."""
        from royaltdn.db.repository import _build_dsn

        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://custom:pass@server:9999/mydb",
        }, clear=True):
            dsn = _build_dsn()
            assert dsn == "postgresql://custom:pass@server:9999/mydb"


# Need os for test_env_vars_override_defaults patching
import os
