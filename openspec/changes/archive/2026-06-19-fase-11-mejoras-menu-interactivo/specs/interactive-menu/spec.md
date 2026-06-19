# Delta for Interactive Menu

## ADDED Requirements

### Requirement: PAUSADO Status Display

MUST render `bot_status` in header, Control, Dashboard KPI. `_log_activity()` on pause/resume.

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| Pause → PAUSADO | ONLINE | user pauses | header "PAUSADO" bold yellow, Control "Bot: PAUSADO", Dashboard KPI "PAUSADO" |
| Resume → ONLINE | PAUSADO | user resumes | header + Control "ONLINE" |
| Immediate switch | ONLINE | pause_signal.json `action:"pause"` | status.json `bot_status` → "PAUSADO" |

### Requirement: Dashboard Auto-Refresh

"¿Auto-refresh? (Enter=5s, número=N, N=manual)". Enter/num → loop + countdown. Ctrl+C exits.

| Scenario | WHEN | THEN |
|----------|------|------|
| Timer | Enter | 5s loop |
| Custom | "10" | 10s loop |
| Cancel | 0 | manual |
| Exit | Ctrl+C | menu |

### Requirement: Menu Badges

Detect signals/trades via mtime vs `_last_menu_visit`. Badges: "2 Scanner 🔔 (N)", "4 Trades 💰 (N)". First visit: skip.

| Scenario | GIVEN | THEN |
|----------|-------|------|
| New signals | 3 since last visit | badge on option 2 |
| First visit | no baseline | none |

## MODIFIED Requirements

### Requirement: Main Menu Loop

SHALL display header + PAUSADO (bold yellow) + 8 options + badges + 0 exit. Invalid: error. Ctrl+C: "¿Salir?" → `orch.stop()`.
(Previously: 6 options)

| Scenario | WHEN | THEN |
|----------|------|------|
| Navigate | "1" | Dashboard |
| Option 7 | "7" | What-If |
| Option 8 | "8" | Activity Log |
| Invalid | "9" | error + re-prompt |
| Ctrl+C exit | Ctrl+C+"s" | orch.stop() |

### Requirement: Dashboard

SHALL render KPIs (PAUSADO bold yellow) + Positions + Signals + Trades + Logs + auto-refresh per ADDED.
(Previously: Fixed Enter/N/0 prompt)

#### Scenario: Paused KPI
- GIVEN `bot_status: "PAUSADO"`
- WHEN Dashboard renders
- THEN KPI status shows "PAUSADO" bold yellow

### Requirement: Estrategias & Builder

Unified table: Nombre, Tipo, Símbolo, Timeframe, Activa, Parámetros. Sorted. Parámetros: compact, trunc 40 chars. Submenu: Seleccionar/Builder/Cargar/Volver. Strategy submenu: Toggle/Editar(user)/Eliminar(user)/Backtest. All ops call `_log_activity()`.
(Previously: Basic Ver/Builder/Cargar, no CRUD)

Builder accepts `existing_config`: preloads + "Valor actual: X. Enter" + skippable.

Toggle writes `active` to strategies.json; orchestrator skips inactive.

Eliminar: confirm → `StrategyStore.delete()`. Predefined: no Delete.

| Scenario | WHEN | THEN |
|----------|------|------|
| Full flow | 10 builder steps | saved to user_strategies/ |
| Toggle | select + Toggle | `active` field updated |
| Delete user | Eliminar + "s" | StrategyStore.delete() |
| Edit | builder with config | preloaded values |
| Quick backtest | Backtest + Enter | metrics table |

### Requirement: Trades

Symbol → period filter (1 Hoy, 2 Semana, 3 Mes, 4 Todo, 5 Custom). Metrics recalculated. Submenu: Rendimiento por estrategia (group by `strategy`), Exportar (CSV/JSON), Estadísticas (streaks, avg duration, best/worst day).
(Previously: Symbol filter only)

#### Scenario: Filter
- GIVEN 10 trades across 3 symbols
- WHEN user enters "SPY"
- THEN only SPY trades shown

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| Date filter | 50 trades | "1 Hoy" | today only, recalc'd |
| Per-strategy | `strategy` field | Rendimiento | grouped by P&L |
| Export | filtered set | Exportar+CSV | exports/trades.csv |
| No data | 0 matches | period filter | "[dim]No trades[/]" |

### Requirement: Control

SHOW status (Estado: PAUSADO bold yellow). Submenu: Pausar/Reanudar/Forzar scanner/Alertas. Read `logs/alert_thresholds.json` (defaults: drawdown 3%, max losses 5). Edit-by-number, validate, write.
(Previously: 3 submenu items, no alerts)

#### Scenario: Pause
- GIVEN bot ONLINE
- WHEN "1"
- THEN pause_bot() called

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| Alert config | — | "4" | thresholds shown |
| Update | — | edit→"5" | file updated |
| Invalid | — | "abc" | error+retry |
| Corrupt file | invalid JSON | open | defaults silently |
