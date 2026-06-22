# Proposal: Fase 10 — Menú de texto interactivo universal

## Intent

Replace Textual TUI (incompatible with Termux) with `input()`+Rich menu — works on Termux, SSH, desktop — reusing backend modules without curses.

## Scope

### In Scope
- `frontend/menu/app.py` with `run_menu()` — 6-option main loop
- `main.py` — swap Textual import for menu, keep Orchestrator thread
- Dashboard, Scanner, Estrategias, Trades, Logs, Control screens
- Builder paso a paso (indicator → rule → backtest → save)
- All screens render via Rich (Tables, Panels, Text) using `StateLoader`, `LogBuffer`, `commands.py`

### Out of Scope
- curses / getch / any single-key input library
- Textual TUI modifications (keep `textual/` untouched for future VPS)
- Persistent UI state (no ncurses buffers, no screen history)

## Capabilities

### New Capabilities
- `interactive-menu`: `input()`+Rich menu — 6 screens, builder wizard, Rich inline rendering

### Modified Capabilities
- `textual-tui`: superseded by interactive-menu for Termux; `textual/` tree preserved for future VPS

## Approach

- **Main loop**: `_clear_screen()` → `_print_header()` → `_print_menu()` → `input(">> ")` → dispatch to screen function
- **Each screen**: loads `StateLoader.load_all()`, renders Rich, waits for Enter
- **Builder wizard**: sequential `input()` — name, indicator, params, conditions, entry/exit rule, backtest, save
- **Refresh loops**: Dashboard/Logs offer inline refresh mini-loop via `input()`
- **Entry point**: `main.py` imports `run_menu`; Orchestrator thread unchanged

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/frontend/menu/__init__.py` | New | Package init |
| `src/royaltdn/frontend/menu/app.py` | New | ~400 lines — main loop + 6 screens |
| `src/royaltdn/main.py` | Modified | ~20 lines — swap textual import |
| `pyproject.toml` | Modified | ~5 lines — Rich dep, textual optional |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `input()` blocks execution | Low | Daemon thread unaffected |
| Builder backtest blocks menu | Low | `run_backtest` is <1s |
| Rich colors break in 16-color | Low | `Console(color_system="standard")` |

## Rollback Plan

1. Revert `main.py` import to `from royaltdn.frontend.textual import RoyalTDNApp`
2. Delete `frontend/menu/` directory
3. Restore `pyproject.toml` deps
4. No backend modules affected

## Success Criteria

- [ ] `python -m royaltdn run` launches text menu (not Textual)
- [ ] Each of 6 screens renders Rich content and returns on Enter
- [ ] Builder creates and saves a strategy end-to-end
- [ ] Pause / Resume / Scanner control signals work from menu
- [ ] Runs in Termux with `TEXTUAL_COLORS=16`
- [ ] All existing tests pass (`pytest`)
