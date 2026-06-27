-- RoyalTDN — Schema DDL for TimescaleDB Persistence Layer (M5)
--
-- Applied idempotently by DBRepository._ensure_schema() on pool init.
-- All statements use IF NOT EXISTS / IF NOT NULL guards.
--
-- New hypertables:
--   equity_snapshots  — portfolio state at bar resolution (90d retention)
--   system_events     — bus events with JSONB payload (30d retention)
--
-- Extended tables:
--   trades   — add duration_seconds, exit_reason, fees, slippage, tags
--   signals  — add fees

-- ═══════════════════════════════════════════════════════════════════════
-- Equity snapshots — portfolio value over time
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS equity_snapshots (
    time        TIMESTAMPTZ     NOT NULL,
    total_value NUMERIC(14, 2)  NOT NULL,
    capital     NUMERIC(14, 2)  NOT NULL,
    drawdown    NUMERIC(8, 4)   NOT NULL,
    peak_value  NUMERIC(14, 2)  NOT NULL
);

SELECT create_hypertable('equity_snapshots', 'time', if_not_exists => TRUE);
SELECT add_retention_policy('equity_snapshots', INTERVAL '90 days', if_not_exists => TRUE);

-- ═══════════════════════════════════════════════════════════════════════
-- System events — bus events with JSONB payload
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS system_events (
    time        TIMESTAMPTZ     NOT NULL,
    event_type  VARCHAR(30)     NOT NULL,
    symbol      VARCHAR(10),
    data        JSONB
);

SELECT create_hypertable('system_events', 'time', if_not_exists => TRUE);
SELECT add_retention_policy('system_events', INTERVAL '30 days', if_not_exists => TRUE);

-- ═══════════════════════════════════════════════════════════════════════
-- Extend existing trades table (created by 01_create_tables.sql)
-- ═══════════════════════════════════════════════════════════════════════

ALTER TABLE trades ADD COLUMN IF NOT EXISTS duration_seconds NUMERIC(10, 2) DEFAULT 0;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS exit_reason     VARCHAR(30)    DEFAULT 'signal';
ALTER TABLE trades ADD COLUMN IF NOT EXISTS fees            NUMERIC(12, 2) DEFAULT 0.00;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS slippage        NUMERIC(8, 4)  DEFAULT 0.0;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tags            JSONB;

-- ═══════════════════════════════════════════════════════════════════════
-- Extend existing signals table (created by 01_create_tables.sql)
-- ═══════════════════════════════════════════════════════════════════════

ALTER TABLE signals ADD COLUMN IF NOT EXISTS fees NUMERIC(10, 2) DEFAULT 0.00;

-- ═══════════════════════════════════════════════════════════════════════
-- Schema version tracking
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS _meta (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMPTZ DEFAULT NOW()
);
