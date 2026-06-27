"""Integration tests for the TimescaleDB persistence layer (M5, PR 3).

Tests T3.1 and T3.2 — require Docker and testcontainers to run.
These create a real TimescaleDB container, apply the schema, and verify
hypertables, retentions, and round-trip CRUD via ``DBRepository``.

Skip behaviour
--------------
- ``pytest.mark.docker`` — test is tagged as Docker-dependent
- If ``shutil.which("docker")`` is falsy, the module is skipped outright
- If ``testcontainers`` is not installed, ``pytest.importorskip`` skips
  the individual test so that consumers get a clear install hint
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# ── Module-level skip (no Docker at all) ───────────────────────────────

pytestmark = [
    pytest.mark.skipif(
        not shutil.which("docker"),
        reason="Docker is not available — integration tests require a "
        "running Docker daemon",
    ),
    pytest.mark.docker,
]

# ── Paths ───────────────────────────────────────────────────────────────

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "src" / "royaltdn" / "db" / "schema.sql"


# ── Helpers ─────────────────────────────────────────────────────────────


def _clean_dsn(pg_container) -> str:
    """Return an asyncpg-compatible DSN from a testcontainers PostgreSQL container.

    Strips any driver suffix (e.g. ``+psycopg2``) that ``asyncpg`` does not
    understand.
    """
    url = pg_container.get_connection_url()
    if "+" in url.replace("://", "XX"):  # only check after scheme
        # postgresql+psycopg2:// → postgresql://
        scheme, _, rest = url.partition("://")
        if "+" in scheme:
            scheme = scheme.split("+")[0]
        url = f"{scheme}://{rest}"
    return url


# ── T3.1 — Schema verification ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_creates_hypertables():
    """Apply schema.sql and verify hypertables, retention, and _meta table.

    This test starts a real TimescaleDB container, runs the full DDL,
    and introspects system catalogs to confirm the schema was applied
    correctly.
    """
    pytest.importorskip(
        "testcontainers",
        reason="testcontainers library not installed — install with: "
        "pip install testcontainers",
    )
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("timescale/timescaledb:latest-pg16") as pg:
        dsn = _clean_dsn(pg)
        import asyncpg

        conn = await asyncpg.connect(dsn)
        try:
            # ── Apply schema ──────────────────────────────────────────
            with open(_SCHEMA_PATH) as f:
                ddl = f.read()
            await conn.execute(ddl)

            # ── Verify hypertables exist ──────────────────────────────
            rows = await conn.fetch(
                "SELECT hypertable_name "
                "FROM timescaledb_information.hypertables"
            )
            hypertables = {r["hypertable_name"] for r in rows}
            assert "equity_snapshots" in hypertables, (
                f"equity_snapshots hypertable not found; "
                f"got {hypertables}"
            )
            assert "system_events" in hypertables, (
                f"system_events hypertable not found; "
                f"got {hypertables}"
            )

            # ── Verify retention policies ─────────────────────────────
            # TimescaleDB stores retention policies as jobs with
            # proc_name containing 'retention'.  We check that at least
            # one retention job exists for each hypertable.
            rows = await conn.fetch(
                "SELECT hypertable_name "
                "FROM timescaledb_information.jobs "
                "WHERE proc_name LIKE '%retention%' "
                "   OR proc_name LIKE '%policy_retention%'"
            )
            retained_hypertables = {r["hypertable_name"] for r in rows}
            assert "equity_snapshots" in retained_hypertables, (
                f"No retention policy found for equity_snapshots; "
                f"jobs: {retained_hypertables}"
            )
            assert "system_events" in retained_hypertables, (
                f"No retention policy found for system_events; "
                f"jobs: {retained_hypertables}"
            )

            # ── Verify _meta table exists ─────────────────────────────
            row = await conn.fetchrow(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_name = '_meta'"
                ")"
            )
            assert row[0] is True, "_meta table was not created"
        finally:
            await conn.close()


# ── T3.2 — Round-trip insert + select ──────────────────────────────────


@pytest.mark.asyncio
async def test_round_trip_insert_and_select():
    """Insert a trade, snapshot, signal, event and verify via query methods.

    Uses ``DBRepository`` directly against a live TimescaleDB container
    and checks that ``get_recent_trades``, ``get_equity_curve``, and
    ``get_trade_stats`` return the expected data.
    """
    pytest.importorskip(
        "testcontainers",
        reason="testcontainers library not installed — install with: "
        "pip install testcontainers",
    )
    from testcontainers.postgres import PostgresContainer

    from royaltdn.db.repository import DBRepository

    with PostgresContainer("timescale/timescaledb:latest-pg16") as pg:
        dsn = _clean_dsn(pg)
        repo = DBRepository(dsn=dsn, min_size=1, max_size=2)

        try:
            connected = await repo.connect()
            assert connected, "DBRepository.connect() returned False"

            # -- Insert a trade --------------------------------------------
            await repo.save_trade({
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
            })

            # -- Insert an equity snapshot ---------------------------------
            await repo.save_equity_snapshot({
                "timestamp": "2025-01-01T10:00:00Z",
                "total_value": 105000.0,
                "capital": 95000.0,
                "drawdown": 0.05,
                "peak_value": 110000.0,
            })

            # -- Insert a signal -------------------------------------------
            await repo.save_signal({
                "timestamp": "2025-01-01T10:00:00Z",
                "cell_name": "swing_1",
                "symbol": "BTCUSDT",
                "action": "BUY",
                "approved": True,
                "price": 30000.0,
                "qty": 0.1,
                "metadata": '{"cell_name": "swing_1", "approved": true}',
            })

            # -- Insert an event -------------------------------------------
            await repo.save_event({
                "timestamp": "2025-01-01T10:00:00Z",
                "event_type": "risk_rejection",
                "symbol": "BTCUSDT",
                "data": {"reason": "max_drawdown_exceeded", "drawdown": 0.12},
            })

            # -- Verify get_recent_trades ----------------------------------
            trades = await repo.get_recent_trades(limit=10)
            assert len(trades) >= 1, "Expected at least 1 trade"
            assert trades[0]["symbol"] == "BTCUSDT", (
                f"Expected BTCUSDT, got {trades[0]['symbol']}"
            )
            assert trades[0]["direction"] == "long"
            assert trades[0]["pnl"] == 200.0

            # -- Verify get_equity_curve -----------------------------------
            curve = await repo.get_equity_curve()
            assert len(curve) >= 1, "Expected at least 1 snapshot"
            assert curve[0]["total_value"] == 105000.0
            assert curve[0]["capital"] == 95000.0

            # -- Verify get_trade_stats ------------------------------------
            stats = await repo.get_trade_stats()
            assert stats["total_trades"] >= 1
            assert stats["total_pnl"] > 0
            assert stats["win_rate"] > 0

        finally:
            await repo.close()
