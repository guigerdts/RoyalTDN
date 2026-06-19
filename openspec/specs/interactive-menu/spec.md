# Interactive Menu Specification

## Purpose

`input()`+Rich text menu — 8 screens (Dashboard, Scanner, Estrategias, Trades, Logs, Control, Simulación, Actividad) + strategy Builder wizard. Reuses StateLoader, LogBuffer, commands.py, builder_state.py. Replaces Textual TUI as default for Termux/SSH/desktop.

## Requirements

### Requirement: Main Menu Loop

SHALL display ASCII-box header + PAUSADO status (bold yellow when paused) + 8 numbered options + notification badges + 0 exit. Input via `input(">> ")`, strip. Invalid: error + re-prompt. Ctrl+C: "¿Salir? (s/n):", break on 's', call `orch.stop()`.

| Scenario | WHEN | THEN |
|----------|------|------|
| Navigate | "1" | Dashboard |
| Option 7 | "7" | What-If |
| Option 8 | "8" | Activity Log |
| Invalid | "9" | error + re-prompt |
| Ctrl+C exit | Ctrl+C+"s" | orch.stop() |

### Requirement: Dashboard

SHALL load `StateLoader.load_all()`, render KPIs via `Table.grid(padding=(0,2))` + `Text.assemble()` (PAUSADO bold yellow when paused), then Positions table, Signals, Trade Summary, Logs (20 lines). Auto-refresh via configurable countdown loop: prompt "¿Auto-refresh? (Enter=5s, número=N, 0=manual)". Enter/num → loop with countdown, Ctrl+C exits.

#### Scenario: Empty state
- GIVEN StateLoader returns empty dicts
- WHEN Dashboard renders
- THEN KPIs show "—" AND tables show "[dim]No data[/]"

#### Scenario: Paused KPI
- GIVEN `bot_status: "PAUSADO"`
- WHEN Dashboard renders
- THEN KPI status shows "PAUSADO" bold yellow

| Scenario | WHEN | THEN |
|----------|------|------|
| Timer | Enter | 5s loop |
| Custom | "10" | 10s loop |
| Cancel | 0 | manual |
| Exit | Ctrl+C | menu |

### Requirement: Scanner

SHOW `state["scanner_results"]` or "No hay resultados aún." Prompt "¿Forzar escaneo? (s/n):" — 's' calls `trigger_scanner()`, sleep 5s, reload, show updated.

#### Scenario: Force scan
- GIVEN no scanner results
- WHEN user enters "s"
- THEN trigger_scanner() called + updated shown after 5s

### Requirement: Estrategias & Builder

SHALL display loaded strategies in unified table: Nombre, Tipo, Símbolo, Timeframe, Activa, Parámetros. Sorted alphabetically. Parámetros: compact, trunc 40 chars.

Submenu: [N] select → Toggle/Editar(user)/Eliminar(user)/Backtest, [B] Builder, [C] Cargar, [0] Volver. All ops call `_log_activity()`. Toggle writes `active` field to strategies.json; orchestrator skips inactive. Eliminar: confirm → `StrategyStore.delete()`. Predefined strategies: no Delete.

Builder (10-step): Name (alphanumeric) → Pick indicator from 16 `INDICATOR_DEFS` → Param values → Loop indicators → Entry rule (indicator + operator from `OPERATOR_GROUPS` + value) → Exit rule → Symbol/timeframe/period → `validate_config()` → `run_backtest()` → Save. When editing (`existing_config` provided): preload values, show "Valor actual: X. Enter para mantener", skippable with Enter.

| Scenario | WHEN | THEN |
|----------|------|------|
| Full flow | user completes 10 steps | strategy saved to user_strategies/ |
| Invalid indicator | enters "99" at pick | error + re-prompt |
| Param type error | enters "abc" for numeric | error + re-prompt |
| Toggle | select + Toggle | `active` field updated |
| Delete user | Eliminar + "s" | StrategyStore.delete() |
| Edit | builder with config | preloaded values |
| Quick backtest | Backtest + Enter | metrics table |

### Requirement: Trades

SHOW `state["trades"]` table + metrics (total_trades, win_rate, profit_factor, total_pnl). Symbol → period filter (1 Hoy, 2 Semana, 3 Mes, 4 Todo, 5 Custom). Metrics recalculated. Submenu: Rendimiento por estrategia (group by `strategy`), Exportar (CSV/JSON), Estadísticas (streaks, avg duration, best/worst day).

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

### Requirement: Logs

SHOW last 20 lines from `log_buffer.get_lines()` with Rich colors. Submenu: 1. INFO / 2. WARNING / 3. ERROR / 4. Todos / 5. Buscar / 0. Volver. Search prompts text, greps buffer. Auto-refresh: "Actualizando cada 2s. Presiona Enter."

| Scenario | WHEN | THEN |
|----------|------|------|
| Level filter | user selects "1" (INFO) | only INFO lines shown |
| Search | selects "5" + "error" | matching lines shown |

### Requirement: Control

SHOW status (Estado, PAUSADO bold yellow when paused, Modo, Uptime). Submenu: 1. Pausar / 2. Reanudar / 3. Forzar scanner / 4. Alertas / 0. Volver. Action calls `commands.pause_bot/resume_bot/trigger_scanner()`, shows confirmation. Read `logs/alert_thresholds.json` (defaults: drawdown 3%, max losses 5). Edit-by-number, validate, write.

#### Scenario: Pause
- GIVEN bot ONLINE
- WHEN user selects "1"
- THEN pause_bot() called + `_log_activity()` logged

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| Alert config | — | "4" | thresholds shown |
| Update | — | edit→"5" | file updated |
| Invalid | — | "abc" | error+retry |
| Corrupt file | invalid JSON | open | defaults silently |

### Requirement: PAUSADO Status Display

MUST render `bot_status` in header, Control, Dashboard KPI. `_log_activity()` on pause/resume.

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| Pause → PAUSADO | ONLINE | user pauses | header "PAUSADO" bold yellow, Control "Bot: PAUSADO", Dashboard KPI "PAUSADO" |
| Resume → ONLINE | PAUSADO | user resumes | header + Control "ONLINE" |
| Immediate switch | ONLINE | pause_signal.json `action:"pause"` | status.json `bot_status` → "PAUSADO" |

### Requirement: Menu Badges

Detect signals/trades via mtime vs `_last_menu_visit`. Badges: "2 Scanner 🔔 (N)", "4 Trades 💰 (N)". First visit: skip.

| Scenario | GIVEN | THEN |
|----------|-------|------|
| New signals | 3 since last visit | badge on option 2 |
| First visit | no baseline | none |

### Requirement: Rendering

MUST use `Console(color_system="standard")`. Colors: basic ANSI only (bold, dim, white, green, red, yellow, cyan, magenta, blue). Tables `show_header=True`, `border_style="white"`, `header_style="bold white"`. NO 24-bit hex. Empty: "—" or "[dim]No data[/]".

#### Scenario: 16-color
- GIVEN TEXTUAL_COLORS=16
- WHEN any screen renders
- THEN no color errors

### Requirement: Resilience

SHALL NOT crash on any input or data condition. Ctrl+C → return to main menu. Corrupt JSON → StateLoader returns defaults + error logged. Invalid numeric → re-prompt.

#### Scenario: Corrupt JSON
- GIVEN logs/status.json is corrupt
- WHEN screen loads state
- THEN StateLoader returns {} + screen renders with "[dim]No data[/]"
