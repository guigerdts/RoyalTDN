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

#### Scenarios

##### Warning shown and user proceeds
- GIVEN the simulation screen is open with 15 historical trades
- WHEN the user selects a strategy to simulate
- THEN a bold yellow warning is displayed: `"⚠️  Solo 15 trades históricos. Mínimo recomendado: 30 para resultados estadísticamente significativos."`
- AND the system asks `"¿Continuar de todas formas? (s/N):"`
- WHEN the user enters "s" or "S"
- THEN the simulation proceeds normally

##### Warning shown and user declines
- GIVEN the simulation screen is open with 15 historical trades
- WHEN the warning prompt asks `"¿Continuar de todas formas? (s/N):"`
- WHEN the user enters anything other than "s" or "S" (including Enter with no input)
- THEN the simulation is cancelled
- AND the screen returns to the simulation menu (strategy selection is not shown)

##### No warning when ≥ 30 trades
- GIVEN the simulation screen is open with exactly 30 historical trades
- WHEN the user navigates to strategy selection
- THEN no warning is displayed
- AND the simulation proceeds directly to strategy selection

##### No trades at all
- GIVEN the simulation screen is open with 0 historical trades
- WHEN the check runs
- THEN the warning is displayed (0 < 30)
- AND the user sees the blocking prompt
- AND if they proceed (enter "s"), the simulation will still show "No hay trades históricos para simular."

##### Warning color
- GIVEN the warning is displayed
- THEN the warning text uses Rich style `"bold yellow"`
- AND it's rendered via `console.print("[bold yellow]...")`

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
