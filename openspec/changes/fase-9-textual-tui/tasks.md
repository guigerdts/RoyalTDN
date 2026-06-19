# Tasks: Fase 9 — Textual TUI Migration + Builder Reconstruction

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1700-1800 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (foundation) → PR 2 (builder) → PR 3 (polish) |
| Delivery strategy | force-chained |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation + 6 base screens + CSS + main.py swap | PR 1 (~800) | Base for all screens |
| 2 | BuilderScreen + BuilderCanvas + backtesting | PR 2 (~600) | Depends on PR 1 structure |
| 3 | HelpScreen + tests + polish + cleanup | PR 3 (~400) | Depends on PR 1+2; delete console/ last |

## Phase 1: Foundation + 6 Base Screens (PR 1)

- [x] 1.1 Create `textual/__init__.py`, `screens/__init__.py`, `widgets/__init__.py`
- [x] 1.2 Create `app.py` — RoyalTDNApp: BINDINGS, compose, on_mount, refresh_data, switch_screen actions
- [x] 1.3 Create `widgets/header.py` — RoyalTDNHeader (mode, status, uptime, scanner_info)
- [x] 1.4 Create `widgets/footer.py` — RoyalTDNFooter (key bindings row)
- [x] 1.5 Create `widgets/metrics_grid.py` — MetricsGrid (Static KPI card grid)
- [x] 1.6 Create `widgets/log_panel.py` — LogPanel (RichLog wrapper, color by level, set_level filter)
- [x] 1.7 Create `screens/dashboard.py` — DashboardScreen (KPIs, positions DataTable, signals, risk, LogPanel)
- [x] 1.8 Create `screens/scanner.py` — ScannerScreen (signals + history DataTable)
- [x] 1.9 Create `screens/estrategias.py` — EstrategiasScreen (predefined + user strategies DataTable)
- [x] 1.10 Create `screens/trades.py` — TradesScreen (metrics Static + trades DataTable)
- [x] 1.11 Create `screens/logs.py` — LogsScreen (level filter Input + colored RichLog)
- [x] 1.12 Create `css/app.tcss` — base styles, low-color Termux compat
- [x] 1.13 Modify `main.py` — import RoyalTDNApp, replace `run_console()` call
- [x] 1.14 Modify `pyproject.toml` — add `textual>=8.0,<9`, `pytest-textual`
- Verify: keys 1-5 switch screens, p/r/s execute IPC, q exits cleanly

## Phase 2: BuilderScreen + BuilderCanvas (PR 2)

- [x] 2.1 Create `css/builder.tcss` — Builder-specific styles
- [x] 2.2 Create `screens/builder.py` — BuilderScreen with TabbedContent (4 tabs)
- [x] 2.3 Tab "Indicadores": Select(16 indicators), Inputs(params), Button("Agregar indicador") — uses builder_state
- [x] 2.4 Tab "Reglas": ListView(conditions), Select(operator_groups), Buttons("Agregar/Eliminar condición")
- [x] 2.5 Tab "Backtesting": symbol/timeframe/period, Button("Ejecutar Backtesting"), RichLog(results) — calls run_backtest()
- [x] 2.6 Tab "Guardar/Cargar": Input(name), Buttons("Guardar/Cargar/Refrescar"), Select(saved) — calls strategy_store
- [x] 2.7 Create `widgets/builder_canvas.py` — ConditionRow helper widget
- Verify: full flow select indicator → config → rule → backtest → save works end-to-end

## Phase 3: HelpScreen + Tests + Polish + Cleanup (PR 3)

- [x] 3.1 Create `screens/help.py` — HelpScreen (Static command reference table)
- [x] 3.2 Create `tests/test_tui.py` pilot test scaffold (6 tests: Dashboard, Nav, IPC, Builder, Help, Quit)
- [x] 3.3 Screen render tests: mount each screen, assert no crash on empty data
- [x] 3.4 Builder flow test: tab switch → indicator select → add indicator
- [x] 3.5 Keyboard nav test: pilot presses keys, assert screen changes
- [x] 3.6 Delete `src/royaltdn/frontend/console/` — app.py, screens/, components/__init__.py, components/widgets.py
- [x] 3.7 Clean unused imports (threading, queue, select, rich.live) from textual/ + cleanup requirements
- [x] 3.8 Final CSS polish + Termux `TEXTUAL_COLORS=16` verification
- [x] Verify: rewrite cmd_status() to not depend on deleted console screens
- Verify: all 6 tests pass, TUI works in low-color, Builder creates deployable strategies
