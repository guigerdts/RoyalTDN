# What-If Simulation — Delta Specification

## ADDED Requirements

### Requirement: RQ-SI-01 — Warning when fewer than 30 historical trades

SHALL check the number of historical trades BEFORE the strategy selection step. If `len(all_trades) < 30`, SHALL display a blocking warning prompt in bold yellow and require user confirmation before proceeding.

#### Scenario: Warning shown and user proceeds

- GIVEN the simulation screen is open with 15 historical trades
- WHEN the user selects a strategy to simulate
- THEN a bold yellow warning is displayed: `"⚠️  Solo 15 trades históricos. Mínimo recomendado: 30 para resultados estadísticamente significativos."`
- AND the system asks `"¿Continuar de todas formas? (s/N):"`
- WHEN the user enters "s" or "S"
- THEN the simulation proceeds normally

#### Scenario: Warning shown and user declines

- GIVEN the simulation screen is open with 15 historical trades
- WHEN the warning prompt asks `"¿Continuar de todas formas? (s/N):"`
- WHEN the user enters anything other than "s" or "S" (including Enter with no input)
- THEN the simulation is cancelled
- AND the screen returns to the simulation menu (strategy selection is not shown)

#### Scenario: No warning when ≥ 30 trades

- GIVEN the simulation screen is open with exactly 30 historical trades
- WHEN the user navigates to strategy selection
- THEN no warning is displayed
- AND the simulation proceeds directly to strategy selection

#### Scenario: No trades at all

- GIVEN the simulation screen is open with 0 historical trades
- WHEN the check runs
- THEN the warning is displayed (0 < 30)
- AND the user sees the blocking prompt
- AND if they proceed (enter "s"), the simulation will still show "No hay trades históricos para simular."

#### Scenario: Warning color

- GIVEN the warning is displayed
- THEN the warning text uses Rich style `"bold yellow"`
- AND it's rendered via `console.print("[bold yellow]...")`
