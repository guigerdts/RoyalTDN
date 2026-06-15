"""
RoyalTDN — Database Layer (Fase 3)

Conexión a TimescaleDB vía psycopg2 (sync con wrapper async).

Tablas:
  - market_bars   : hypertable de velas OHLCV
  - orders        : órdenes enviadas al broker
  - trades        : operaciones cerradas con P&L

Uso:
    db = Database(dsn="postgresql://user:pass@host:5432/db")
    await db.connect()
    await db.insert_trade({...})
    await db.close()
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("royaltdn.db")

# ── DDL de respaldo ───────────────────────────────────────────────────────────

DDL_RESEED = """
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS market_bars (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      VARCHAR(10)     NOT NULL,
    open        NUMERIC(10,2)   NOT NULL,
    high        NUMERIC(10,2)   NOT NULL,
    low         NUMERIC(10,2)   NOT NULL,
    close       NUMERIC(10,2)   NOT NULL,
    volume      BIGINT          NOT NULL,
    source      VARCHAR(20)     NOT NULL DEFAULT 'iex'
);
SELECT create_hypertable('market_bars', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    order_id        VARCHAR(50)     NOT NULL UNIQUE,
    symbol          VARCHAR(10)     NOT NULL,
    side            VARCHAR(10)     NOT NULL,
    qty             INTEGER         NOT NULL,
    order_type      VARCHAR(20)     NOT NULL DEFAULT 'market',
    status          VARCHAR(20)     NOT NULL,
    filled_price    NUMERIC(10,2),
    filled_qty      INTEGER,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    filled_at       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS trades (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(10)     NOT NULL,
    side            VARCHAR(10)     NOT NULL,
    entry_price     NUMERIC(10,2)   NOT NULL,
    exit_price      NUMERIC(10,2)   NOT NULL,
    qty             INTEGER         NOT NULL,
    pnl             NUMERIC(12,2)   NOT NULL,
    pnl_pct         NUMERIC(8,4),
    entry_order_id  VARCHAR(50),
    exit_order_id   VARCHAR(50),
    entry_at        TIMESTAMPTZ     NOT NULL,
    exit_at         TIMESTAMPTZ     NOT NULL,
    strategy        VARCHAR(50)     NOT NULL DEFAULT 'sma_crossover'
);

CREATE TABLE IF NOT EXISTS signals (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      VARCHAR(10)     NOT NULL,
    signal      INTEGER         NOT NULL,
    fast_ma     INTEGER         NOT NULL,
    slow_ma     INTEGER         NOT NULL,
    price       NUMERIC(10,2)   NOT NULL,
    metadata    JSONB
);
SELECT create_hypertable('signals', 'time', if_not_exists => TRUE);
"""


class Database:
    """Conexión a TimescaleDB (psycopg2 sync + wrapper async).

    Args:
        dsn: Connection string.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: Any = None
        self._loop = asyncio.get_event_loop()
        self._connected = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Conecta y crea tablas si no existen."""
        try:
            import psycopg2

            self._conn = await self._loop.run_in_executor(
                None,
                lambda: psycopg2.connect(self._dsn),
            )
            self._conn.autocommit = True

            # Crear tablas
            await self._execute(DDL_RESEED)

            self._connected = True
            # Extraer host del DSN para log
            host = self._dsn.split("@")[-1].split("/")[0] if "@" in self._dsn else self._dsn
            logger.info(f"Conectado a TimescaleDB en {host}")
            return True

        except Exception as e:
            logger.warning(f"No se pudo conectar a TimescaleDB: {e}")
            self._connected = False
            return False

    async def close(self):
        """Cierra conexión."""
        if self._conn:
            await self._loop.run_in_executor(None, self._conn.close)
            self._connected = False
            logger.info("Conexión a TimescaleDB cerrada")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Execute ───────────────────────────────────────────────────────────

    async def _execute(self, query: str, params: tuple | None = None) -> None:
        """Ejecuta una query DML."""
        if not self._connected or not self._conn:
            return
        try:
            await self._loop.run_in_executor(
                None,
                lambda: self._execute_sync(query, params),
            )
        except Exception as e:
            logger.error(f"Error DB: {e}")

    def _execute_sync(self, query: str, params: tuple | None = None) -> None:
        """Ejecuta query en el thread actual (sync)."""
        with self._conn.cursor() as cur:
            if params:
                # psycopg2 usa %s no %(name)s con tuplas
                if isinstance(params, dict):
                    cur.execute(query, params)
                else:
                    cur.execute(query, params)
            else:
                cur.execute(query)

    async def _fetch(self, query: str, params: tuple | None = None) -> list[dict]:
        """Ejecuta SELECT y devuelve lista de dicts."""
        if not self._connected or not self._conn:
            return []
        try:
            return await self._loop.run_in_executor(
                None,
                lambda: self._fetch_sync(query, params),
            )
        except Exception as e:
            logger.error(f"Error DB fetch: {e}")
            return []

    def _fetch_sync(self, query: str, params: tuple | None = None) -> list[dict]:
        """Ejecuta SELECT en thread actual."""
        with self._conn.cursor() as cur:
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            cols = [desc[0] for desc in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ── Insert methods ────────────────────────────────────────────────────

    async def insert_bar(self, symbol: str, bar: dict) -> None:
        """Inserta una vela en market_bars."""
        await self._execute(
            "INSERT INTO market_bars (time, symbol, open, high, low, close, volume, source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                bar.get("time", datetime.now(timezone.utc)),
                symbol,
                bar["open"],
                bar["high"],
                bar["low"],
                bar["close"],
                bar["volume"],
                bar.get("source", "iex"),
            ),
        )
        logger.debug(f"Bar insertado: {symbol} @ {bar['close']}")

    async def insert_order(self, order: dict) -> None:
        """Inserta una orden en orders."""
        await self._execute(
            "INSERT INTO orders (order_id, symbol, side, qty, order_type, status, "
            "filled_price, filled_qty, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (order_id) DO NOTHING",
            (
                order["order_id"],
                order["symbol"],
                order["side"],
                order["qty"],
                order.get("order_type", "market"),
                order["status"],
                order.get("filled_price"),
                order.get("filled_qty"),
                order.get("created_at", datetime.now(timezone.utc)),
            ),
        )
        logger.debug(f"Orden insertada: {order['order_id']}")

    async def insert_trade(self, trade: dict) -> None:
        """Inserta una operación cerrada en trades con P&L y TCA."""
        pnl = trade["pnl"]
        entry_price = trade.get("entry_price", 0)
        pnl_pct = trade.get("pnl_pct", pnl / entry_price if entry_price > 0 else 0)

        await self._execute(
            "INSERT INTO trades (symbol, side, entry_price, exit_price, qty, pnl, pnl_pct, "
            "entry_order_id, exit_order_id, entry_at, exit_at, strategy, "
            "slippage_bps, arrival_price, execution_method) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                trade["symbol"],
                trade["side"],
                entry_price,
                trade["exit_price"],
                trade["qty"],
                pnl,
                round(pnl_pct, 4),
                trade.get("entry_order_id"),
                trade.get("exit_order_id"),
                trade["entry_at"],
                trade["exit_at"],
                trade.get("strategy", "sma_crossover"),
                trade.get("slippage_bps"),
                trade.get("arrival_price"),
                trade.get("execution_method", "market"),
            ),
        )
        logger.info(f"Trade registrado: {trade['symbol']} P&L=${pnl:.2f}")

    # ── Queries ───────────────────────────────────────────────────────────

    async def get_equity_curve(self) -> list[dict]:
        """Curva de equity acumulada (últimos 365 días)."""
        return await self._fetch(
            "SELECT exit_at AS date, "
            "SUM(pnl) OVER (ORDER BY exit_at) AS cumulative_pnl, "
            "SUM(pnl_pct) OVER (ORDER BY exit_at) AS cumulative_return_pct "
            "FROM trades "
            "WHERE exit_at >= NOW() - INTERVAL '365 days' "
            "ORDER BY exit_at"
        )
