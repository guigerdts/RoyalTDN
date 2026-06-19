# Design: Fase 10 — Menú de texto interactivo universal

## Technical Approach

Replace Textual TUI with `input()` + Rich inline rendering. Single `run_menu()` loop dispatches to screen functions, each loading state via `StateLoader.load_all()` + `_load_file("signals.json")` and rendering with `Console(color_system="standard")`. Builder wizard is a sequential 12-step flow reusing `builder_state.py`, `schema.py`, `backtesting.py`, and `StrategyStore`. Orchestrator thread runs unchanged — menu is a drop-in replacement for `RoyalTDNApp().run()`.

## Architecture Decisions

| Decision | Options | Chosen | Rationale |
|----------|---------|--------|-----------|
| Console init | auto vs standard | `color_system="standard"` | Forces 16-color, avoids Termux breakage |
| Screen clearing | os.system('clear') vs ANSI | `print("\033[2J\033[H", end="")` | No subprocess, works cross-platform |
| Log refresh | Thread vs loop | Loop with `time.sleep(N)` | Simpler, no threading for display |
| Builder state | In-memory vs file | In-memory dict during wizard, atomic save at end | No partial files, clean rollback |
| Signals loading | From load_all vs manual | Manual `loader._load_file("signals.json", {})` | `load_all()` lacks `signals` key — Textual dashboard uses same pattern |
| Error handling | Per-input vs global | Per-input + global KeyboardInterrupt | Precise messages per field |

## Data Flow

```
cmd_run() [main.py]
  │
  ├── setup_logging()
  ├── Orchestrator → thread (daemon) → orch.start()
  │
  └── run_menu(logs_dir)
        │
        ├── StateLoader(logs_dir) ─── reads logs/*.json
        ├── LogBuffer(max_lines=200)
        ├── setup_console_log_handler(buffer) ─── Loguru → buffer
        └── Console(color_system="standard")
              │
              └── WHILE True:
                    ├── clear() + header + menu
                    ├── "1" → _show_dashboard(loader, buffer, console)
                    │         ├── loader.load_all() + _load_file("signals.json")
                    │         ├── Rich Group (KPIs | Positions | Signals | Summary | Logs)
                    │         └── Refresh loop: Enter/s/N auto
                    ├── "2" → _show_scanner()
                    │         ├── show loader.load_all()["scanner"]
                    │         └── [s] → trigger_scanner() → sleep 5 → reload
                    ├── "3" → _show_strategies() → submenu → _builder_flow()
                    │         ├── 12-step wizard (name→indicators→rules→backtest→save)
                    │         └── Integration: builder_state → schema → backtesting → store
                    ├── "4" → _show_trades() ─── filter by symbol
                    ├── "5" → _show_logs() ─── filter level/search + 2s auto-refresh
                    ├── "6" → _show_control() ─── pause / resume / scanner
                    └── "0" → break → orch.stop()
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/royaltdn/frontend/menu/__init__.py` | Create | Package init, exports `run_menu` |
| `src/royaltdn/frontend/menu/app.py` | Create | ~400 lines: main loop + 6 screen functions + builder |
| `src/royaltdn/main.py` | Modify | `cmd_run()`: swap `RoyalTDNApp().run()` for `run_menu()` |
| `pyproject.toml` | Modify | `rich>=13.0` as required dep; `textual` moved to optional extras |

## Interfaces / Contracts

### run_menu() entry point
```python
def run_menu(logs_dir: str = "logs") -> None:
    """Interactive text menu. Blocks until user selects 0 or Ctrl+C."""
```

### API contract (reused, not new)
| Module | Interface | Returns |
|--------|-----------|---------|
| `StateLoader(logs_dir).load_all()` | `dict` with keys: `status`, `equity`, `positions`, `scanner`, `strategies`, `trades` | |
| `StateLoader._load_file("signals.json", {})` | `dict` — signals require manual load (not in `load_all`) | |
| `LogBuffer.get_lines(level_filter, text_filter, last_n)` | `list[str]` | |
| `commands.pause_bot/resume_bot/trigger_scanner(logs_dir)` | `None` — writes signal JSON | |
| `StrategyStore(store_dir).save(config)` | `str` — saved file path | |
| `run_backtest(config, symbol, timeframe, period)` | `dict` with keys `metrics`, `trades`, `error` | |
| `validate_config(config)` | `(bool, str)` — valid + error message | |
| `INDICATOR_DEFS` / `OPERATOR_GROUPS` | `list[dict]` — 16 indicators, 7 operator groups | |
| `_build_tree(logic, conditions)` | `dict` — rule tree for strategy config | |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Builder input validation | Param type/range prompts, 16 indicator picker |
| Unit | _clear_screen, _print_header, _print_menu | Smoke test: renders without crash |
| Unit | Ctrl+C handling | KeyboardInterrupt → "¿Salir?" → break |
| Integration | run_menu with mock StateLoader | Monkeypatch load_all, verify screen functions call it |
| Integration | Builder flow end-to-end | Mock input() → verify save called with valid config |

## Migration / Rollout

No migration required. `textual/` tree left intact for future `--tui` flag. `cmd_run()` currently imports `RoyalTDNApp` directly; change is a single import swap + pyproject.toml dep adjustment.

## Open Questions

- [ ] `signals.json` missing from `load_all()` — menu will call `_load_file` manually. Consider adding `load_signals()` to StateLoader in a follow-up.
- [ ] Builder 12-step wizard: the `_build_tree()` function expects specific dict shapes. Verify each step's output matches schema v1 before `validate_config()`.
