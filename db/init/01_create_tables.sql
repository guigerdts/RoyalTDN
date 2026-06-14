-- RoyalTDN — Initialization Script for TimescaleDB
-- Fase 3: Base de datos temporal (velas, trades, señales)
-- 
-- Este script se ejecuta automáticamente cuando el contenedor
-- TimescaleDB arranca por primera vez con datos vacíos.

-- Habilitar TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Tabla: market_bars — Velas diarias OHLCV
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS market_bars (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      VARCHAR(10)     NOT NULL,
    open        NUMERIC(10, 2)  NOT NULL,
    high        NUMERIC(10, 2)  NOT NULL,
    low         NUMERIC(10, 2)  NOT NULL,
    close       NUMERIC(10, 2)  NOT NULL,
    volume      BIGINT          NOT NULL,
    source      VARCHAR(20)     NOT NULL DEFAULT 'iex'  -- iex, sip, polygon
);

-- Convertir a hypertable particionada por tiempo
SELECT create_hypertable('market_bars', 'time', if_not_exists => TRUE);

-- Índices para consultas rápidas por símbolo
CREATE INDEX IF NOT EXISTS idx_market_bars_symbol_time
    ON market_bars (symbol, time DESC);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Tabla: orders — Órdenes enviadas al broker
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    order_id        VARCHAR(50)     NOT NULL UNIQUE,        -- ID de Alpaca
    symbol          VARCHAR(10)     NOT NULL,
    side            VARCHAR(10)     NOT NULL,               -- buy / sell
    qty             INTEGER         NOT NULL,
    order_type      VARCHAR(20)     NOT NULL DEFAULT 'market',
    status          VARCHAR(20)     NOT NULL,               -- filled, cancelled, etc.
    filled_price    NUMERIC(10, 2),
    filled_qty      INTEGER,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    filled_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_orders_created_at
    ON orders (created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Tabla: trades — Operaciones cerradas (entrada + salida)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS trades (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(10)     NOT NULL,
    side            VARCHAR(10)     NOT NULL,               -- long / short
    entry_price     NUMERIC(10, 2)  NOT NULL,
    exit_price      NUMERIC(10, 2)  NOT NULL,
    qty             INTEGER         NOT NULL,
    pnl             NUMERIC(12, 2)  NOT NULL,               -- ganancia/pérdida
    pnl_pct         NUMERIC(8, 4),                          -- % de retorno
    entry_order_id  VARCHAR(50),
    exit_order_id   VARCHAR(50),
    entry_at        TIMESTAMPTZ     NOT NULL,
    exit_at         TIMESTAMPTZ     NOT NULL,
    strategy        VARCHAR(50)     NOT NULL DEFAULT 'sma_crossover'
);

CREATE INDEX IF NOT EXISTS idx_trades_exit_at
    ON trades (exit_at DESC);

CREATE INDEX IF NOT EXISTS idx_trades_strategy
    ON trades (strategy, exit_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Tabla: signals — Señales generadas (auditoría)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS signals (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      VARCHAR(10)     NOT NULL,
    signal      INTEGER         NOT NULL,           -- 0 = flat, 1 = long, -1 = short
    fast_ma     INTEGER         NOT NULL,
    slow_ma     INTEGER         NOT NULL,
    price       NUMERIC(10, 2)  NOT NULL,
    metadata    JSONB
);

SELECT create_hypertable('signals', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_time
    ON signals (symbol, time DESC);
