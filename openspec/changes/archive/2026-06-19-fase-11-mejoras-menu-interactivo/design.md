# Design: FASE 11 — Mejoras del menú interactivo

## Technical Approach

Monolithic enhancement of `app.py` (1429 lines) following its existing patterns: function-level lazy imports, Rich console, StateLoader reads. Minimal `orchestrator.py` changes for PAUSADO and `active` filtering. All new functions follow `_show_*` / `_build_*` naming convention. StateLoader TTL (1s) accepted — for immediate PAUSADO rendering, call `load_all()` fresh each render (already happening in dashboard loop).

## Architecture Decisions

| Decision | Options | Chosen | Rationale |
|----------|---------|--------|-----------|
| PAUSADO | orchestrator writes `"PAUSADO"` in status.json vs app.py infers from `paused` field | Both: orchestrator writes `bot_status: "PAUSADO"`, app.py also checks `paused` field directly | Double insurance — orchestrator changes status string, app.py also reads `paused` for immediate UI feedback |
| Builder edit | Thread `existing_config` param vs clone builder entirely | Single `_builder_flow()` with `existing_config=None` default | Reuses all 12 stages; pre-fill logic is a few conditionals per stage |
| Strategy filtering | orchestrator skips inactive vs app.py hides them | orchestrator skips inactive in `_build_strategies_list()` | Centralized — all consumers (dashboard, menu) see consistent set |
| Badges detection | Poll mtime of files vs read timestamp from JSON | Read `last_signals[0].timestamp` and `trades[-1].exit_at` from StateLoader | No extra file reads; data already loaded |
| What-if simulation | Re-run full backtest vs recalculate P&L from trades | `_simulate_trades()` recalculates from historical trades | No data download, instant, uses real historical data |

## Data Flow

```
pause/resume action (app.py)
  → commands.pause_bot()/resume_bot()
  → pause_signal.json written
  → orchestrator._check_signals() reads file
  → orchestrator.paused = True/False
  → orchestrator._publish_status() writes status.json with bot_status: "PAUSADO"/"ONLINE"
  → app.py StateLoader.load_all() → status dict → _print_header, _build_kpis, _show_control

strategy toggle (app.py)
  → _toggle_strategy() writes `active` field to strategies.json
  → orchestrator._build_strategies_list() reads strategies.json, skips active:false
  → StateLoader.load_strategies() reflects new state on next render
```

## File Changes

### src/royaltdn/frontend/menu/app.py — 18 changes

| Function | Action | Signature |
|----------|--------|-----------|
| `_log_activity` | **New** | `(mensaje: str, logs_dir: str = "logs") -> None` |
| `_is_bot_paused` | **New** | `(logs_dir: str = "logs") -> bool` |
| `_check_notifications` | **New** | `(state_loader) -> dict` |
| `_print_header` | **Modify** | Add PAUSADO check via `_is_bot_paused()` |
| `_print_menu` | **Modify** | Accept `badges: dict \| None = None`, add options 7, 8 |
| `_build_kpis` | **Modify** | Color status "PAUSADO" bold yellow |
| `run_menu` | **Modify** | Track `_last_menu_visit`, call `_check_notifications`, call `_log_activity` |
| `_show_dashboard` | **Modify** | Auto-refresh countdown (`time.sleep(1)` loop) |
| `_show_estrategias` | **Rewrite** | Unified table, strategy submenu (toggle/edit/delete/backtest) |
| `_get_strategy_params_summary` | **New** | `(config: dict) -> str` |
| `_toggle_strategy` | **New** | `(name: str, active: bool, is_user: bool, logs_dir: str) -> bool` |
| `_builder_flow` | **Modify** | Accept `existing_config: dict \| None = None` |
| `_show_trades` | **Rewrite** | Loop with date filter, submenu (per-strategy/export/stats) |
| `_filter_trades_by_date` | **New** | `(trades: list[dict], period: str, start, end) -> list[dict]` |
| `_show_performance_by_strategy` | **New** | `(trades: list[dict], console)` |
| `_export_trades` | **New** | `(trades: list[dict], console)` |
| `_show_advanced_stats` | **New** | `(trades: list[dict], console)` |
| `_show_control` | **Modify** | Add option 4 for alert config |
| `_show_alert_config` | **New** | `(console, logs_dir: str)` |
| `_show_simulation` | **New** | `(state_loader, console, logs_dir: str)` |
| `_simulate_trades` | **New** | `(trades: list[dict], param: str, new_value: float) -> dict` |
| `_show_activity` | **New** | `(console, logs_dir: str)` |

Module-level: `_last_menu_visit: float = 0.0`

### src/royaltdn/orchestrator.py — 2 changes

| Line | Change | Details |
|------|--------|---------|
| 626 | `_publish_status` | `bot_status = "PAUSADO" if self.paused else ("KILLED" if self._killed else "ONLINE")` |
| 444 | `_build_strategies_list` | Skip user strategies with `active: False` in config; predefined strategies get `active` from strategy status |

### src/royaltdn/frontend/console/commands.py — 0 changes

Reusing existing `pause_bot()`, `resume_bot()`, `trigger_scanner()`, `get_bot_status()` as-is.

## Cross-cutting Mechanisms

```
_log_activity(mensaje, logs_dir="logs"):
  → append "[{now}] {mensaje}\n" to logs/user_activity.log
  → OSError silently ignored

_is_bot_paused(logs_dir="logs") -> bool:
  → read status.json, return data.get("paused", False) or data.get("bot_status") == "PAUSADO"
  → FileNotFound/JSONDecode → return False

_check_notifications(state_loader) -> dict:
  → load signals.json, trades.json, check pause_signal.json existence
  → return {"signals": int, "trades": int, "paused": bool}

Badges: _print_menu(console, badges) appends "🔔 (N nuevas)" to option descriptions
```

## Builder Refactoring

`_builder_flow(existing_config: dict | None = None, console, logs_dir: str = "logs")`:

When `existing_config` is provided:
- Stage 1 (Name): show `"Valor actual: {name}. Enter para mantener"`, pre-fill
- Stages 2-4 (Indicators): load existing indicators, skip if Enter (keeps)
- Stages 5-6 (Entry/Exit rules): pre-load entry_tree/exit_tree, skip if Enter
- Stages 7-9 (Symbol/Timeframe/Period): pre-fill, Enter keeps
- Stage 10 (Backtest): run with current config
- Stage 11 (Save): `StrategyStore().save(config)` creates NEW timestamped version

When `existing_config` is None: current behavior unchanged.

## Simulation Contract

```
_simulate_trades(
  trades: list[dict],        # from trades.json["trades"]
  param: str,                # "stop_loss" | "take_profit" | "position_size"
  new_value: float           # new multiplier/ratio/pct
) -> dict:
  # Returns {"total_pnl": float, "max_drawdown": float, "win_rate": float, "num_trades": int}

Algorithm per trade:
  entry = trade["entry_price"]
  exit   = trade["exit_price"]
  qty    = trade.get("qty", 1)
  direction = 1 (long)  # assumes long-only

  if param == "stop_loss":
    atr = entry * 0.01  # default ATR = 1% of entry
    new_exit = entry - atr * new_value  # tighter stop
    exit = min(exit, new_exit) if exit > entry else exit  # limit exit
  elif param == "take_profit":
    ratio = new_value / 100.0
    new_exit = entry * (1 + ratio)
    exit = min(exit, new_exit) if exit > entry else exit
  elif param == "position_size":
    qty = int(10000 * new_value / 100 / entry)  # % of $10k capital
    qty = max(1, qty)

  pnl = (exit - entry) * qty * direction
```

## Implementation Plan

### Sequential order (with dependency graph)

```
Step 1: PAUSADO correction ────────────────────────────────── (no deps)
Step 2: _log_activity() helper ────────────────────────────── (no deps)
Step 3: Estrategias (toggle/delete/edit/params/unified/backtest)
         └── depends on step 2
Step 4: Dashboard (auto-refresh, badges)
         └── depends on step 2
Step 5: Trades (date filter, per-strategy, export, stats)
         └── depends on step 2
Step 6: Control alerts
         └── depends on step 2
Step 7: What-if simulation
         └── depends on step 2
Step 8: Activity viewer
         └── depends on step 2
```

### Verification milestones

| Step | Verify |
|------|--------|
| 1 | Pause → header/Control/KPI show "PAUSADO" bold yellow |
| 2 | `user_activity.log` created with timestamped entries |
| 3 | Toggle active/inactive, delete user strategy, edit with preload, unified table, quick backtest |
| 4 | Auto-refresh countdown, badges appear on new signals/trades |
| 5 | Date filter recalculates metrics, CSV/JSON export, win/loss streaks |
| 6 | Alert thresholds editable, written to `logs/alert_thresholds.json` |
| 7 | Strategy param change shows comparison table |
| 8 | Last 20 lines from `user_activity.log` display |

## Navigation Flow

```
run_menu()
│
├── 1 → _show_dashboard()
│       Loop: countdown timer, sleep(1), re-render,
│       prompt "Próxima actualización en Xs... (0=volver)"
│
├── 2 → _show_scanner()  (unchanged)
│
├── 3 → _show_estrategias()
│       Unified table (Predefinida + Usuario, sorted)
│       Submenu: [N] select → [Toggle/Editar*/Eliminar*/Backtest]
│                [B] builder [C] cargar [0] volver
│       * only for user strategies
│
├── 4 → _show_trades()
│       Filter: symbol → period (1 Hoy/2 Semana/3 Mes/4 Todo/5 Custom)
│       Submenu: [P] per-strategy [E] export [S] stats [0] volver
│
├── 5 → _show_logs()  (unchanged)
│
├── 6 → _show_control()
│       Status: "PAUSADO" bold yellow
│       [1] Pausar [2] Reanudar [3] Scanner [4] Alertas
│
├── 7 → _show_simulation()         ★ NEW
│       Select strategy → param → value → comparison table
│
├── 8 → _show_activity()           ★ NEW
│       Last 20 lines, text search
│
└── 0 → stop bot, exit
        _log_activity("Menú finalizado")
```
