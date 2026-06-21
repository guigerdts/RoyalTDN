# Textual TUI Specification

## Purpose

Textual-based TUI replacing the Rich console: 7 keyboard-driven screens with IPC control. Reuses StateLoader, LogBuffer, commands.py, builder_state.py.

## Requirements

### Requirement: Screen Navigation

MUST switch screens via BINDINGS (no Enter): `1-6`→screens, `h`→Help, `p`→pause, `r`→resume, `s`→scan, `q`/ctrl+c→quit.

#### Scenario: Quick switch
- GIVEN DashboardScreen is active
- WHEN user presses `3`
- THEN EstrategiasScreen pushes immediately

#### Scenario: Pause bot
- GIVEN app is running
- WHEN user presses `p`
- THEN pause_signal.json written AND StatusBar shows "Paused"

### Requirement: Live Polling

Each screen SHALL call set_interval() in on_mount(). _poll_state() loads StateLoader data and routes to current screen's refresh_data().

| Screen | Timer | Sources |
|--------|-------|---------|
| Dashboard | 2s | state[account, positions, signals, risk] |
| Scanner | 2s | state[signals, scan_history] |
| Estrategias | 5s | state[strategies] |
| Trades | 3s | state[trades] |
| Logs | 1s | LogBuffer (filtered) |
| Builder | None | builder_state defs |
| Help | None | Hardcoded |

#### Scenario: Timer update
- GIVEN DashboardScreen is visible
- WHEN 2s elapse
- THEN refresh_data() called with fresh state

#### Scenario: Stale data
- GIVEN last_updated > 30s ago
- WHEN _poll_state() runs
- THEN StatusBar shows "Stale"

### Requirement: Empty Data Resilience

All screens MUST render without errors when StateLoader returns empty dicts. Show "Waiting for bot..." or "—" values.

#### Scenario: Empty dashboard
- GIVEN StateLoader returns empty dicts
- WHEN DashboardScreen renders
- THEN KPI cards show "—" AND no errors

### Requirement: Dashboard Broker Column

SHALL display a "Broker" column in the DashboardScreen's positions DataTable, positioned after the "P&L" column. Each row SHALL show the broker name (`"Alpaca"` or `"Binance"`) for the corresponding position.

#### Scenario: Mixed broker positions
- GIVEN positions from both Alpaca and Binance are loaded
- WHEN the DashboardScreen renders the positions DataTable
- THEN the "Broker" column shows `"Alpaca"` for stock positions and `"Binance"` for crypto positions

#### Scenario: All Alpaca positions
- GIVEN only Alpaca positions exist
- WHEN the DashboardScreen renders the positions DataTable
- THEN the "Broker" column shows `"Alpaca"` for all rows

### Requirement: Screen Composition

Dashboard: Static KPIs, DataTable positions, ListView signals, Static risk, LogPanel.
Scanner: DataTable signals+history, Static metadata.
Estrategias: DataTable name, indicators, rules, status.
Trades: DataTable ID/symbol/side/qty/entry/exit/P&L, Static KPIs.
Logs: Input level filter, RichLog auto-scroll, color by level.
Help: Static table of bindings.

#### Scenario: Log coloring
- GIVEN LogsScreen is active with mixed levels
- WHEN logs arrive
- THEN RichLog shows green INFO, yellow WARN, red ERROR, dim DEBUG

### Requirement: BuilderScreen

4 tabs: Indicators, Rules, Backtesting, Save/Load.

**Indicators:** Select from INDICATOR_REGISTRY (16); config Inputs on selection; "Add to Rule".

**Rules:** ListView of conditions `{src} {op} {target}`; operator_groups (7); "Test Rule" validates; "Clear All" resets.

**Backtesting:** Rule summary; date Inputs; "Run Backtest" → run_backtest(); results DataTable (Sharpe, Profit Factor, Win Rate, Drawdown, CAGR, Total Return). MUST validate rule first.

**Save/Load:** "Save Strategy" → strategy_store.save_strategy(); "Deploy" → writes to active/; ListView of saved strategies.

#### Scenario: Full builder flow
- GIVEN BuilderScreen on Indicators tab
- WHEN user selects RSI(14), sets period, adds condition "RSI(14) < 30"
- AND runs backtest with valid dates AND saves as "my_strat"
- THEN strategy saved to user_strategies/ AND app.notify() confirms

#### Scenario: Block incomplete
- GIVEN rule has no conditions
- WHEN user presses "Run Backtest"
- THEN app.notify() shows "Rule not complete" AND backtest does not run

### Requirement: Custom Widgets

RoyalTDNHeader (app name, screen title, status, timestamp; dark blue/white).
RoyalTDNFooter (available keys, scanner status).
MetricsGrid (Static card grid, N columns by width).
LogPanel (wraps RichLog, color by level, set_level() filter).

### Requirement: Orchestrator Integration

Same process, separate thread. IPC via signal files. main.py imports RoyalTDNApp. Rich stays for CLI-only.

#### Scenario: Main entry
- GIVEN `python -m royaltdn` called
- THEN RoyalTDNApp launches AND Orchestrator thread starts

### Requirement: Termux Compatibility

MUST work with TEXTUAL_COLORS=16. Minimum 80×24; graceful degradation.

#### Scenario: Low-color mode
- GIVEN TEXTUAL_COLORS=16
- WHEN app starts on Termux
- THEN screens render without color errors

## Acceptance Criteria

- [ ] All 7 screens render on empty data (no crashes)
- [ ] Screen switch via single key (no Enter)
- [ ] P/R/S keys execute IPC and update StatusBar
- [ ] Builder: indicator + rule + backtest + save under 2 min
- [ ] LogsScreen colors by level, HelpScreen shows bindings
- [ ] Works in Termux with TEXTUAL_COLORS=16
- [ ] Existing StateLoader/LogBuffer tests pass
