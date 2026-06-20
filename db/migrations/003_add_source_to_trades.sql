-- Migration 003: Add source column to trades table
-- FASE 16 — Ejecución Automática de Señales del Scanner

ALTER TABLE trades ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'legacy';
