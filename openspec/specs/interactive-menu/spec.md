# Interactive Menu Specification

## Purpose

`input()`+Rich text menu — 6 screens (Dashboard, Scanner, Estrategias, Trades, Logs, Control) + strategy Builder wizard. Reuses StateLoader, LogBuffer, commands.py, builder_state.py. Replaces Textual TUI as default for Termux/SSH/desktop.

## Requirements

### Requirement: Main Menu Loop

SHALL display ASCII-box header + 6 numbered options + 0 exit. Input via `input(">> ")`, strip. Invalid: error + "Presiona Enter", loop. Ctrl+C: "¿Salir? (s/n):", break on 's', call `orch.stop()`.

| Scenario | WHEN | THEN |
|----------|------|------|
| Navigate | user enters "1" | Dashboard screen renders |
| Invalid | user enters "9" | error + re-prompt |
| Ctrl+C exit | Ctrl+C + "s" | orch.stop() + loop ends |

### Requirement: Dashboard

SHALL load `StateLoader.load_all()`, render KPIs via `Table.grid(padding=(0,2))` + `Text.assemble()`, then Positions table, Signals, Trade Summary, Logs (20 lines). Prompt: "¿Actualizar? (Enter = sí, 0 = volver, número = segundos)". Enter re-renders, 0 returns, N auto-refresh until key.

#### Scenario: Empty state
- GIVEN StateLoader returns empty dicts
- WHEN Dashboard renders
- THEN KPIs show "—" AND tables show "[dim]No data[/]"

### Requirement: Scanner

SHOW `state["scanner_results"]` or "No hay resultados aún." Prompt "¿Forzar escaneo? (s/n):" — 's' calls `trigger_scanner()`, sleep 5s, reload, show updated.

#### Scenario: Force scan
- GIVEN no scanner results
- WHEN user enters "s"
- THEN trigger_scanner() called + updated shown after 5s

### Requirement: Estrategias & Builder

SHOW loaded strategies from state. Submenu: 1. Ver / 2. Builder / 3. Cargar / 0. Volver.

Builder (10-step): Name (alphanumeric) → Pick indicator from 16 `INDICATOR_DEFS` → Param values → Loop indicators → Entry rule (indicator + operator from `OPERATOR_GROUPS` + value) → Exit rule → Symbol/timeframe/period → `validate_config()` → `run_backtest()` → "¿Guardar?" calls `StrategyStore().save()`.

| Scenario | WHEN | THEN |
|----------|------|------|
| Full flow | user completes 10 steps | strategy saved to user_strategies/ |
| Invalid indicator | enters "99" at pick | error + re-prompt |
| Param type error | enters "abc" for numeric | error + re-prompt |

### Requirement: Trades

SHOW `state["trades"]` table + metrics (total_trades, win_rate, profit_factor, total_pnl). Prompt "Filtrar por símbolo (Enter = todos):" → filter + show filtered.

#### Scenario: Filter
- GIVEN 10 trades across 3 symbols
- WHEN user enters "SPY"
- THEN only SPY trades shown

### Requirement: Logs

SHOW last 20 lines from `log_buffer.get_lines()` with Rich colors. Submenu: 1. INFO / 2. WARNING / 3. ERROR / 4. Todos / 5. Buscar / 0. Volver. Search prompts text, greps buffer. Auto-refresh: "Actualizando cada 2s. Presiona Enter."

| Scenario | WHEN | THEN |
|----------|------|------|
| Level filter | user selects "1" (INFO) | only INFO lines shown |
| Search | selects "5" + "error" | matching lines shown |

### Requirement: Control

SHOW status (Estado, Modo, Uptime). Submenu: 1. Pausar / 2. Reanudar / 3. Forzar scanner / 0. Volver. Action calls `commands.pause_bot/resume_bot/trigger_scanner()`, shows confirmation.

#### Scenario: Pause
- GIVEN bot ONLINE
- WHEN user selects "1"
- THEN pause_bot() called + confirmation shown

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
