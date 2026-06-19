# Design: Fase 9 — Textual TUI Migration + Builder Reconstruction

## Technical Approach

Full replacement: build `frontend/textual/` from scratch with Textual 8.x, reuse 4 pure-Python modules unchanged (StateLoader, LogBuffer, commands.py, builder_state.py). 7 screens mapped 1:1 from Rich console, plus rebuilt BuilderScreen from Fase 7 data definitions. Async `set_interval` polling replaces sync 2fps `Live` loop + threaded `input()` hack. `console/` kept untouched until verified — rollback is a git revert.

## Architecture Decisions

| Option | Tradeoffs | Decision |
|--------|-----------|----------|
| Textual `Screen` subclasses vs `Widget` composition | Screens = navigation units; Widgets = reusable UI blocks | **Screen per view** (7), **Widget per component** (Header, Footer, MetricsGrid, LogPanel, BuilderCanvas) |
| `SCREENS` dict vs manual push | Dict enables BINDINGS dispatch via screen name | **SCREENS dict** — matches Textual's `on_screen_reserve` pattern |
| Single timer vs per-screen timers | Single = simpler, one `refresh_data()` entry point; Per-screen = optimized but more setup | **Single timer** at App level, calls `active_screen.update_data()` — spec says per-screen timers but App-level routing is cleaner and matches proposal |
| Import `commands.py` from `console/` vs copy | Import = zero duplication, copy = self-contained textual/ | **Import from `console/commands.py`** — same process, no migration cost |
| RichLog vs custom Textual Log | RichLog exists, has color support, works in Textual; custom needed for advanced filtering | **RichLog wrapped in LogPanel** — color by level (green/yellow/red/dim), `set_level()` filter, auto-scroll |

## Data Flow

```
 Orchestrator thread                Textual App (async)
 ─────────────────────              ─────────────────────
  writes logs/*.json                RoyalTDNApp.on_mount()
       │                                │
       ▼                                ▼
  state file (JSON)      set_interval(0.5s) ──→ refresh_data()
                                                    │
                                          StateLoader.load_all()
                                          LogBuffer.get_lines()
                                                    │
                                          screen.update_data(state, log_buffer)
                                                    │
                                          Widget refresh (reactive)
```

## Class Architecture

```
RoyalTDNApp (App)
├── SCREENS = {dashboard, scanner, estrategias, trades, logs, builder, help}
├── BINDINGS: 1-6→switch_screen, p→pause, r→resume, s→scan, h→help, q→quit
├── compose() → Header + Footer
├── on_mount() → init StateLoader, LogBuffer, set_interval(0.5, refresh_data)
│
├── DashboardScreen → MetricsGrid, DataTable(positions), ListView(signals), Static(risk), LogPanel
├── ScannerScreen   → DataTable(signals+history), Static(metadata)
├── EstrategiasScreen → DataTable(predefined+user)
├── TradesScreen    → DataTable(trades), Static(metrics)
├── LogsScreen      → Input(filter), RichLog(colored)
├── BuilderScreen   → TabbedContent: Indicators/Rules/Backtesting/SaveLoad
└── HelpScreen      → Static(commands table)
```

## BuilderScreen Design

| Tab | Widgets | Data Source |
|-----|---------|-------------|
| Indicadores | Select(16 indicators), Inputs(params), Button("Add to Rule") | `builder_state.INDICATOR_DEFS`, `INDICATOR_MAP` |
| Reglas | ListView(conditions), Select(operator_groups), Button("Test Rule"), Button("Clear All") | `builder_state.OPERATOR_GROUPS`, `builder_state._build_tree()` |
| Backtesting | Static(rule summary), Inputs(start/end), Button("Run Backtest"), DataTable(results) | `backtesting.run_backtest()`, `schema.validate_config()` |
| Guardar/Cargar | Input(strategy name), Button("Save"), Button("Deploy"), ListView(saved) | `strategy_store.save()`, `strategy_store.load_all()` |

**State flow**: Select indicator → config params → "Add to Rule" appends to builder_state conditions → rules tab shows ListView → "Run Backtest" calls `build_tree()` + `validate_config()` + `run_backtest()` → results table → "Save" calls `strategy_store.save()`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/royaltdn/frontend/textual/__init__.py` | Create | Package init |
| `src/royaltdn/frontend/textual/app.py` | Create | RoyalTDNApp — BINDINGS, compose, on_mount, refresh_data, actions |
| `src/royaltdn/frontend/textual/screens/__init__.py` | Create | Screen re-exports |
| `src/royaltdn/frontend/textual/screens/dashboard.py` | Create | DashboardScreen |
| `src/royaltdn/frontend/textual/screens/scanner.py` | Create | ScannerScreen |
| `src/royaltdn/frontend/textual/screens/estrategias.py` | Create | EstrategiasScreen |
| `src/royaltdn/frontend/textual/screens/trades.py` | Create | TradesScreen |
| `src/royaltdn/frontend/textual/screens/logs.py` | Create | LogsScreen with filter + RichLog |
| `src/royaltdn/frontend/textual/screens/builder.py` | Create | BuilderScreen (4 tabs) |
| `src/royaltdn/frontend/textual/screens/help.py` | Create | HelpScreen |
| `src/royaltdn/frontend/textual/widgets/__init__.py` | Create | Widget re-exports |
| `src/royaltdn/frontend/textual/widgets/header.py` | Create | RoyalTDNHeader |
| `src/royaltdn/frontend/textual/widgets/footer.py` | Create | RoyalTDNFooter |
| `src/royaltdn/frontend/textual/widgets/metrics_grid.py` | Create | MetricsGrid for KPIs |
| `src/royaltdn/frontend/textual/widgets/log_panel.py` | Create | LogPanel wrapping RichLog |
| `src/royaltdn/frontend/textual/widgets/builder_canvas.py` | Create | BuilderCanvas (rule tree + tabs) |
| `src/royaltdn/frontend/textual/css/` | Create | app.tcss, screens.tcss, builder.tcss |
| `src/royaltdn/main.py` | Modify | Import RoyalTDNApp, replace `run_console()` |
| `pyproject.toml` | Modify | Add `textual>=8.0,<9`, `pytest-textual` |
| `tests/test_textual/` | Create | Test package |
| `tests/test_console.py` | Modify | Keep StateLoader/LogBuffer/commands tests |

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | StateLoader, LogBuffer, commands | Keep existing tests unchanged |
| Unit | builder_state, schema, backtesting | Keep existing strategy tests |
| Integration | Screen rendering on empty data | `pytest-textual` — mount each screen, assert no crash |
| Integration | Builder flow | Simulate tab switch → indicator select → add rule → backtest |
| E2E | Full app launch + keyboard | `pilot` API: press keys, assert screen changes |

## Migration / Rollout

3 chained PRs:
- **PR 1 (Foundation)**: app.py, Header, Footer, 6 base screens (no Builder), CSS, main.py import swap. ~700 lines.
- **PR 2 (Builder)**: BuilderScreen + BuilderCanvas, backtesting integration, save/load. ~600 lines.
- **PR 3 (Polishing)**: HelpScreen, tests, cleanup (remove old console/ on confirmation). ~400 lines.

console/ is never removed until textual/ is verified — fallback exists at every step.

## Open Questions

- [ ] LogsScreen: use RichLog inside Textual vs native Textual Log widget? RichLog preferred for color parity with existing console.
