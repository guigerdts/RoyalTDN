# Tasks: Fase 10 — Menú de texto interactivo universal

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~520 (400 new + 120 tests) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Hito 1: app.py foundation + screens, ~250) → PR 2 (Hito 2–3: builder + integration + tests, ~200) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Hito 1: app.py main loop + 6 screen functions + `__init__.py` | PR 1 | Base = feature/tracker branch. 250 lines. Independent, verifiable. |
| 2 | Hito 2–3: Builder 12-stage wizard + main.py swap + pyproject.toml + tests | PR 2 | Base = PR 1 branch. ~270 lines. Depends on app.py existing. |

## Phase 1: Foundation — Main loop + helpers

- [x] 1.1 Create `menu/__init__.py` exporting `run_menu`
- [x] 1.2 Create `menu/app.py` with `run_menu()` — `Console(color_system="standard")`, `StateLoader(logs_dir)`, `LogBuffer(200)`, `setup_console_log_handler(buffer)`, main `while True` loop
- [x] 1.3 Implement `_clear_screen()` via `\033[2J\033[H` and `_print_header()` with ASCII-box header
- [x] 1.4 Implement `_print_menu()` with 6 numbered options (1–6) + 0 exit; invalid input → error + "Presiona Enter"
- [x] 1.5 Ctrl+C handling: KeyboardInterrupt → "¿Salir? (s/n):" → `orch.stop()` + break on 's'

## Phase 2: Screens

- [x] 2.1 `_show_dashboard(loader, buffer, console)` — KPIs grid (`Table.grid`), positions table, signals via `_load_file("signals.json")`, trade summary (total_trades, win_rate, profit_factor, total_pnl), last 20 logs; refresh loop with Enter / Ns auto
- [x] 2.2 `_show_scanner(loader, console)` — show `state["scanner"]` results; "s" → `trigger_scanner()` + 5s sleep + reload
- [x] 2.3 `_show_trades(loader, console)` — trade history table + metrics; symbol filter prompt
- [x] 2.4 `_show_logs(buffer, console)` — colored logs (level filter: INFO/WARNING/ERROR/Todos + search + 2s auto-refresh)
- [x] 2.5 `_show_control(console, logs_dir)` — bot status display + submenu: pause/resume/trigger_scanner + confirmation
- [x] 2.6 `_show_strategies(loader, console)` — loaded strategies list + submenu (Ver / Builder / Cargar) → routes to builder

## Phase 3: Builder wizard

- [x] 3.1 `_builder_flow(console)` — entry point for 12-stage wizard, in-memory builder dict
- [x] 3.2 Stage 1: strategy name input (alphanumeric + spaces) with validation
- [x] 3.3 Stages 2–4: indicator pick (numbered from `INDICATOR_DEFS`), param config per type (int/float/select), loop for more indicators
- [x] 3.4 Stages 5–6: ENTRY rule — indicator selector + operator from `OPERATOR_GROUPS` + value (only if operator in `NEEDS_VALUE`) + AND/OR logic
- [x] 3.5 Stage 7: EXIT rule (same pattern as ENTRY)
- [x] 3.6 Stage 8–9: symbol + timeframe + period inputs for backtest
- [x] 3.7 Stage 10: `validate_config()` — show valid/error, re-prompt on failure
- [x] 3.8 Stage 10 (cont): `run_backtest()` — show metrics in Rich Table
- [x] 3.9 Stage 11–12: "¿Guardar?" → `StrategyStore().save(config)` → confirm path

## Phase 4: Integration

- [x] 4.1 Modify `main.py`: replace `from royaltdn.frontend.textual import RoyalTDNApp` with `from royaltdn.frontend.menu.app import run_menu`; swap `RoyalTDNApp().run()` for `run_menu()`
- [x] 4.2 Modify `pyproject.toml`: add `rich>=13.0` as required dep, move `textual` to optional extras

## Phase 5: Testing

- [x] 5.1 Unit tests: `_build_kpis`/`_build_positions`/`_build_signals`/`_build_summary` render without crash
- [x] 5.2 Unit tests: builder input validation — Ctrl+C handling, full builder flow with mocked inputs
- [x] 5.3 Integration: `run_menu()` with mock `KeyboardInterrupt` — verify graceful exit
- [x] 5.4 Integration: builder flow end-to-end — mock `input()` → verify flow completes for all 12 stages
- [x] 5.5 Verify imports, compile, no hex colors, no Textual imports (all verified)

## Implementation Order

Phase 1 first (app.py must exist). Phase 2 can proceed in parallel within the same file — screens are independent functions. Phase 3 depends on app.py structure from Phase 1. Phase 4 is last (only touches main.py and pyproject.toml). Phase 5 can start alongside Phase 2.

### Key Constraints
- `Console(color_system="standard")` — only ANSI-safe colors, NO 24-bit hex
- Signals loaded via `loader._load_file("signals.json", {})` — `load_all()` does NOT include signals
- Ctrl+C must never crash — always catch and return to main loop or exit gracefully
- Builder state is in-memory dict, `_build_tree()` from builder_state.py for rule tree
- `StateLoader.load_all()` returns `scanner` key (not `scanner_results`)
