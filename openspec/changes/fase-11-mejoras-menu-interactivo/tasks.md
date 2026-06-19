# Tasks: FASE 11 — Mejoras del menú interactivo

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

~18 new/modified functions across `app.py` + orchestrator.py → ~800-1200 lines. Exceeds 400-line budget.

| PR | Scope | Base |
|----|-------|------|
| 1 | Foundation + PAUSADO | `feature/fase-11` |
| 2 | Estrategias | PR 1 branch |
| 3 | Dashboard + Trades | PR 2 branch |
| 4 | Control + Simulation + Activity | PR 3 branch |

## Phase 1: Cross-cutting Foundation

- [x] 1.1 `app.py` — `_log_activity(mensaje, logs_dir)` appends to `logs/user_activity.log`, OSError silently ignored
- [x] 1.2 `app.py` — `_is_bot_paused(logs_dir)` reads `status.json`, checks `paused + bot_status`, FileNotFound→False
- [x] 1.3 `app.py` — Module-level `_last_menu_visit: float = 0.0`
- [x] 1.4 `app.py` — `_check_notifications(state_loader)` → `{signals: N, trades: N, paused: bool}`

## Phase 2: PAUSADO Correction

- [x] 2.1 `orchestrator.py` — `_publish_status()`: `bot_status = "PAUSADO"` when `self.paused`
- [x] 2.2-2.4 `app.py` — `_print_header()`, `_show_control()`, `_build_kpis()`: render "PAUSADO" bold yellow via `_is_bot_paused()`

## Phase 3: Estrategias Improvements

- [x] 3.1 `app.py` — `_get_strategy_params_summary(config)` → compact param string (≤50 chars)
- [x] 3.2 `app.py` — `_show_estrategias()`: unified table (Nombre, Tipo, Activa, Parámetros), sorted alphabetically
- [x] 3.3 `app.py` — `_toggle_strategy(name, active, is_user, logs_dir)` writes `active` field to strategies.json / StrategyStore
- [x] 3.4 `orchestrator.py` — `_build_strategies_list()` + `_run_legacy_loop()` skip strategies with `active: false`
- [x] 3.5 `app.py` — Strategy submenu: Toggle, Edit (user-only), Delete (user-only), Quick Backtest; all call `_log_activity()`
- [x] 3.6 `app.py` — `_builder_flow(console, existing_config=None, logs_dir="logs")`: preload on edit, Enter=keep, saves as new version

## Phase 4: Dashboard Auto-refresh + Badges

- [x] 4.1 `app.py` — `_show_dashboard()`: countdown loop, `time.sleep(1)`, custom interval, Ctrl+C exit
- [x] 4.2 `app.py` — `_print_menu()`: accept `badges: dict | None`, append badge counts to option labels

## Phase 5: Trades Improvements

- [x] 5.1 `app.py` — `_show_trades()`: symbol → period filter (1 Hoy/2 Semana/3 Mes/4 Todo/5 Custom) → submenu
- [x] 5.2 `app.py` — `_filter_trades_by_date(trades, start_date, end_date)` → filtered list
- [x] 5.3 `app.py` — `_show_performance_by_strategy(trades, console)`: group by strategy field, show P&L
- [x] 5.4 `app.py` — `_export_trades(trades, console, logs_dir)`: CSV/JSON to `exports/`, call `_log_activity()`
- [x] 5.5 `app.py` — `_show_advanced_stats(trades, console)`: win/loss streaks, avg duration, best/worst day

## Phase 6: Control — Alert Thresholds

- [ ] 6.1 `app.py` — `_show_alert_config(console, logs_dir)`: read/write `logs/alert_thresholds.json`
- [ ] 6.2 `app.py` — `_show_control()`: add "4 Alertas" option, dispatch to `_show_alert_config()`

## Phase 7: Simulation + Activity Viewer

- [ ] 7.1 `app.py` — `_show_simulation(state_loader, console, logs_dir)`: strategy picker, param editor, comparison table
- [ ] 7.2 `app.py` — `_simulate_trades(trades, param, new_value)`: recalc P&L adjusting stop/TP/size → stats dict
- [ ] 7.3 `app.py` — `_show_activity(console, logs_dir)`: last 20 lines from `user_activity.log`, text search
- [ ] 7.4 `app.py` — `run_menu()`: options 7+8 dispatch, `_last_menu_visit`, `_check_notifications`, `_log_activity()`
