-- RoyalTDN — TCA Migration: añade columna slippage_bps a trades
-- Fase 4, Bloque 5 (documento 6, sección 6.4.5)
--
-- Ejecutar contra TimescaleDB:
--   docker compose exec db psql -U botuser -d trading_bot -f db/migrations/002_add_slippage.sql

BEGIN;

ALTER TABLE trades ADD COLUMN IF NOT EXISTS slippage_bps NUMERIC(8,2);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS arrival_price NUMERIC(10,2);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS execution_method VARCHAR(20) DEFAULT 'market';

COMMENT ON COLUMN trades.slippage_bps IS 'Deslizamiento en basis points (positivo = peor precio para el comprador)';
COMMENT ON COLUMN trades.arrival_price IS 'Precio de mercado al momento de la decisión (último tick)';
COMMENT ON COLUMN trades.execution_method IS 'Método de ejecución: market, twap, limit';

COMMIT;
