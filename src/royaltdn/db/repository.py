"""Async TimescaleDB repository with connection pool and typed CRUD.

Provides ``DBRepository`` (asyncpg-backed), ``NullDBRepository`` (no-op
fallback), and ``init_pool()`` / ``get_repository()`` entry points for
the application bootstrap.
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

# ── DSN helpers ──────────────────────────────────────────────────────────

_DEFAULT_USER = "botuser"
_DEFAULT_PASSWORD = "botpassword"
_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = "5432"
_DEFAULT_DB = "trading_bot"


def _build_dsn() -> str:
    """Build a PostgreSQL DSN from ``DB_*`` environment variables.

    Falls back to the existing ``DATABASE_URL`` when set, and then to
    individual ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASSWORD``
    / ``DB_NAME`` variables.  When none are configured, returns a
    localhost default compatible with ``docker-compose`` defaults.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    host = os.environ.get("DB_HOST", _DEFAULT_HOST)
    port = os.environ.get("DB_PORT", _DEFAULT_PORT)
    user = os.environ.get("DB_USER", _DEFAULT_USER)
    password = os.environ.get("DB_PASSWORD", _DEFAULT_PASSWORD)
    database = os.environ.get("DB_NAME", _DEFAULT_DB)
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def _get_pool_size() -> tuple[int, int]:
    """Read ``DB_POOL_MIN`` and ``DB_POOL_MAX`` from the environment."""
    min_size = int(os.environ.get("DB_POOL_MIN", "2"))
    max_size = int(os.environ.get("DB_POOL_MAX", "10"))
    return min_size, max_size


# ── Repository ───────────────────────────────────────────────────────────


class DBRepository:
    """Async TimescaleDB repository via ``asyncpg`` connection pool.

    All ``save_*`` methods are safe to call when the pool is not
    connected — they log a warning and no-op if ``is_connected`` is
    ``False``.

    Args:
        dsn: PostgreSQL connection string.
        min_size: Minimum pool connections (default 2).
        max_size: Maximum pool connections (default 10).
    """

    def __init__(
        self,
        dsn: str,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None
        self.is_connected: bool = False

    # -- Pool lifecycle ------------------------------------------------------

    async def connect(self) -> bool:
        """Create the connection pool and apply the schema.

        Returns:
            ``True`` when the pool was created successfully and schema
            was applied.  ``False`` on failure — the bot should continue
            running with a ``NullDBRepository``.
        """
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
            )
        except Exception:
            self.is_connected = False
            self._pool = None
            return False

        self.is_connected = True

        try:
            await self._ensure_schema()
        except Exception:
            # Schema failure is non-fatal — tables may already exist.
            pass

        return True

    async def close(self) -> None:
        """Close the connection pool and mark as disconnected."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        self.is_connected = False

    # -- Schema management ---------------------------------------------------

    async def _ensure_schema(self) -> None:
        """Read and execute ``schema.sql`` idempotently."""
        if self._pool is None:
            return

        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r") as f:
            ddl = f.read()

        async with self._pool.acquire() as conn:
            await conn.execute(ddl)

    # -- Writes (fire-and-forget safe) ---------------------------------------

    async def save_trade(self, trade: dict[str, Any]) -> None:
        """Insert a closed trade into the ``trades`` hypertable.

        Args:
            trade: Dict with keys matching ``Trade`` dataclass fields:
                ``symbol``, ``direction``, ``entry_price``, ``exit_price``,
                ``qty``, ``pnl``, ``pnl_pct``, ``strategy_name``,
                ``entry_time``, ``exit_time``, ``duration_seconds``,
                ``exit_reason``, ``fees``.
        """
        if not self.is_connected or self._pool is None:
            logger.warning(
                "DB save_trade skipped: repository is disconnected "
                "(symbol={})",
                trade.get("symbol", "?"),
            )
            return

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO trades (
                    symbol, side, entry_price, exit_price, qty,
                    pnl, pnl_pct, entry_at, exit_at, duration_seconds,
                    exit_reason, fees, strategy
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                trade.get("symbol", ""),
                trade.get("direction", "long"),
                trade.get("entry_price", 0.0),
                trade.get("exit_price", 0.0),
                trade.get("qty", 0),
                trade.get("pnl", 0.0),
                trade.get("pnl_pct", 0.0),
                trade.get("entry_time"),
                trade.get("exit_time"),
                trade.get("duration_seconds", 0),
                trade.get("exit_reason", "signal"),
                trade.get("fees", 0.0),
                trade.get("strategy_name", ""),
            )

    async def save_equity_snapshot(self, state: dict[str, Any]) -> None:
        """Insert a portfolio snapshot into ``equity_snapshots``.

        Args:
            state: Dict with keys ``timestamp``, ``total_value``,
                ``capital``, ``drawdown``, ``peak_value``.
        """
        if not self.is_connected or self._pool is None:
            logger.warning(
                "DB save_equity_snapshot skipped: repository is disconnected"
            )
            return

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO equity_snapshots (time, total_value, capital, drawdown, peak_value)
                VALUES ($1, $2, $3, $4, $5)
                """,
                state.get("timestamp"),
                state.get("total_value", 0.0),
                state.get("capital", 0.0),
                state.get("drawdown", 0.0),
                state.get("peak_value", 0.0),
            )

    async def save_signal(self, signal: dict[str, Any]) -> None:
        """Insert a signal into the ``signals`` hypertable.

        Maps high-level signal fields to the existing table layout:
        ``action`` → ``signal`` (int: BUY=1, SELL=-1, SHORT=-1, HOLD=0),
        extra fields (``cell_name``, ``approved``, ``reason``, ``qty``)
        are stored in the ``metadata`` JSONB column.

        Args:
            signal: Dict with keys ``timestamp``, ``cell_name``,
                ``symbol``, ``action``, ``approved``, ``reason``,
                ``price``, ``qty``.
        """
        if not self.is_connected or self._pool is None:
            logger.warning(
                "DB save_signal skipped: repository is disconnected "
                "(symbol={}, action={})",
                signal.get("symbol", "?"),
                signal.get("action", "?"),
            )
            return

        action = signal.get("action", "")
        signal_int = {"BUY": 1, "SELL": -1, "SHORT": -1}.get(action, 0)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO signals (time, symbol, signal, fast_ma, slow_ma, price, metadata)
                VALUES ($1, $2, $3, 0, 0, $4, $5::jsonb)
                """,
                signal.get("timestamp"),
                signal.get("symbol", ""),
                signal_int,
                signal.get("price", 0.0),
                signal.get("metadata", "{}"),
            )

    async def save_event(self, event: dict[str, Any]) -> None:
        """Insert a system event into the ``system_events`` hypertable.

        Args:
            event: Dict with keys ``timestamp``, ``event_type``,
                ``symbol``, ``data`` (arbitrary dict stored as JSONB).
        """
        if not self.is_connected or self._pool is None:
            logger.warning(
                "DB save_event skipped: repository is disconnected "
                "(type={})",
                event.get("event_type", "?"),
            )
            return

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_events (time, event_type, symbol, data)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                event.get("timestamp"),
                event.get("event_type", ""),
                event.get("symbol"),
                event.get("data", {}),
            )

    # -- Queries -------------------------------------------------------------

    async def get_recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent trades ordered by exit time descending.

        Args:
            limit: Maximum number of trades to return (default 50).

        Returns:
            List of trade dicts with DB column keys.
        """
        if not self.is_connected or self._pool is None:
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, symbol, side AS direction, entry_price, exit_price,
                       qty, pnl, pnl_pct, entry_at AS entry_time,
                       exit_at AS exit_time, duration_seconds, exit_reason,
                       fees, strategy AS strategy_name
                FROM trades
                ORDER BY exit_at DESC
                LIMIT $1
                """,
                limit,
            )

        return [dict(row) for row in rows]

    async def get_equity_curve(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return equity snapshots within a date range, ordered ascending.

        Args:
            from_date: Inclusive lower bound (ISO string or ``None`` for no bound).
            to_date: Inclusive upper bound (ISO string or ``None`` for no bound).

        Returns:
            List of snapshot dicts with keys ``time``, ``total_value``,
            ``capital``, ``drawdown``, ``peak_value``.
        """
        if not self.is_connected or self._pool is None:
            return []

        async with self._pool.acquire() as conn:
            if from_date and to_date:
                rows = await conn.fetch(
                    """
                    SELECT time, total_value, capital, drawdown, peak_value
                    FROM equity_snapshots
                    WHERE time >= $1 AND time <= $2
                    ORDER BY time ASC
                    """,
                    from_date,
                    to_date,
                )
            elif from_date:
                rows = await conn.fetch(
                    """
                    SELECT time, total_value, capital, drawdown, peak_value
                    FROM equity_snapshots
                    WHERE time >= $1
                    ORDER BY time ASC
                    """,
                    from_date,
                )
            elif to_date:
                rows = await conn.fetch(
                    """
                    SELECT time, total_value, capital, drawdown, peak_value
                    FROM equity_snapshots
                    WHERE time <= $1
                    ORDER BY time ASC
                    """,
                    to_date,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT time, total_value, capital, drawdown, peak_value
                    FROM equity_snapshots
                    ORDER BY time ASC
                    """,
                )

        return [dict(row) for row in rows]

    async def get_trade_stats(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Return aggregate trade statistics for a date range.

        Args:
            from_date: Inclusive lower bound or ``None``.
            to_date: Inclusive upper bound or ``None``.

        Returns:
            Dict with ``total_trades``, ``win_rate``, ``profit_factor``,
            ``total_pnl``, ``avg_duration``.
        """
        if not self.is_connected or self._pool is None:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "avg_duration": 0.0,
            }

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)                                         AS total_trades,
                    COALESCE(AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0.0 END), 0.0)
                                                                     AS win_rate,
                    COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 0.0)
                    / NULLIF(ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)), 0.0)
                                                                     AS profit_factor,
                    COALESCE(SUM(pnl), 0.0)                          AS total_pnl,
                    COALESCE(AVG(duration_seconds), 0.0)             AS avg_duration
                FROM trades
                WHERE ($1::timestamptz IS NULL OR exit_at >= $1::timestamptz)
                  AND ($2::timestamptz IS NULL OR exit_at <= $2::timestamptz)
                """,
                from_date,
                to_date,
            )

        return dict(row) if row else {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "avg_duration": 0.0,
        }


# ── Null repository (graceful degradation) ───────────────────────────────


class NullDBRepository:
    """No-op fallback repository used when TimescaleDB is unreachable.

    Every method has the same signature as ``DBRepository`` but performs
    no I/O.  ``is_connected`` is always ``False``.

    This lets the engine, portfolio, and bus subscribers call ``save_*``
    unconditionally without checking connectivity.
    """

    is_connected: bool = False

    async def connect(self) -> bool:
        """Simulate a failed connection — always returns ``False``."""
        return False

    async def close(self) -> None:
        """No-op: nothing to close."""

    async def save_trade(self, trade: dict[str, Any]) -> None:
        """No-op: trade is not persisted."""

    async def save_equity_snapshot(self, state: dict[str, Any]) -> None:
        """No-op: snapshot is not persisted."""

    async def save_signal(self, signal: dict[str, Any]) -> None:
        """No-op: signal is not persisted."""

    async def save_event(self, event: dict[str, Any]) -> None:
        """No-op: event is not persisted."""

    async def get_recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return an empty list — no data available."""
        return []

    async def get_equity_curve(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return an empty list — no data available."""
        return []

    async def get_trade_stats(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Return zero-valued stats — no data available."""
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "avg_duration": 0.0,
        }


# ── Factory ──────────────────────────────────────────────────────────────

_repository: DBRepository | NullDBRepository | None = None


def get_repository() -> DBRepository | NullDBRepository:
    """Return the singleton repository instance.

    Returns the existing instance if one was previously created.  If
    ``init_pool()`` has not been called, returns a fresh
    ``NullDBRepository`` so callers never receive ``None``.

    Returns:
        ``DBRepository`` or ``NullDBRepository`` singleton.
    """
    global _repository
    if _repository is None:
        _repository = NullDBRepository()
    return _repository


async def init_pool(
    dsn: str | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
) -> DBRepository | NullDBRepository:
    """Create a ``DBRepository``, initialise the connection pool, and
    apply the schema.

    Called once at startup from ``run.py``.  On failure (unreachable DB,
    bad credentials, network error) returns a ``NullDBRepository`` so the
    bot continues running without persistence.

    Args:
        dsn: Optional DSN override.  Defaults to ``_build_dsn()``.
        min_size: Pool min connections override.
        max_size: Pool max connections override.

    Returns:
        Connected ``DBRepository`` on success, ``NullDBRepository`` on
        failure.
    """
    global _repository

    dsn = dsn or _build_dsn()
    if min_size is None or max_size is None:
        _min, _max = _get_pool_size()
        min_size = min_size or _min
        max_size = max_size or _max

    repo = DBRepository(dsn=dsn, min_size=min_size, max_size=max_size)
    connected = await repo.connect()

    if not connected:
        _repository = NullDBRepository()
        return _repository

    _repository = repo
    return repo
