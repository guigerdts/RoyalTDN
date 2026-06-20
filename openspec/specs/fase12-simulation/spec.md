# FASE 12 — Simulación: Advertencia de Mínimo de Trades

## Purpose

Add a blocking warning before simulation execution when there are fewer than 30 historical trades, ensuring statistical validity awareness.

## Requirements

### RQ-SI-01 — Warning < 30 historical trades

SHALL check `len(all_trades)` before showing the strategy selection menu. If < 30, SHALL display a blocking prompt.

**Warning text:** `"⚠️  Solo {N} trades históricos. Mínimo recomendado: 30 para resultados estadísticamente significativos."` (bold yellow)

**Prompt:** `"¿Continuar de todas formas? (s/N):"`

- `s` / `S` → proceed to strategy selection
- anything else (including Enter) → return to simulation menu

## Color/Style Contract

| Element | Style |
|---------|-------|
| Warning text | `bold yellow` |
| Prompt | default |

## UI Text Contract

| Context | Spanish String |
|---------|---------------|
| Warning text | `"⚠️  Solo {N} trades históricos. Mínimo recomendado: 30 para resultados estadísticamente significativos."` |
| Confirmation prompt | `"¿Continuar de todas formas? (s/N):"` |
