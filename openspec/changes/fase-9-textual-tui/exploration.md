## Exploration: Fase 9 — Textual TUI Migration

### Current State

**Console package (`src/royaltdn/frontend/console/`) — ~1,800 lines total:**

| Module | Lines | Role |
|--------|-------|------|
| `app.py` | 257 | Rich `Live` + threaded `input()` daemon. Sync render loop at 2fps. |
| `commands.py` | 55 | IPC signal files (pause/resume/scan via JSON) |
| `builder_state.py` | 199 | Pure data: 16 indicator defs, 7 operator groups, tree builders. **No UI.** |
| `log_handler.py` | 65 | `LogBuffer` — thread-safe circular `deque[str]` |
| `loguru_config.py` | 70 | Loguru setup (3 sinks: file, stderr, optional LogBuffer) |
| `components/state.py` | 142 | `StateLoader` — reads `logs/*.json` with 1s TTL cache |
| `components/widgets.py` | 588 | 16 pure Rich renderable factories (Panel/Table/Layout) |
| `screens/__init__.py` | 17 | Screen registry (6 render functions) |
| `screens/dashboard.py` | 96 | Rich Layout: KPIs, positions, signals, risk, logs |
| `screens/scanner.py` | 98 | Rich Layout: signals table + scan history |
| `screens/estrategias.py` | 43 | Rich Layout: strategies table |
| `screens/trades.py` | 51 | Rich Layout: metrics + trades table |
| `screens/logs.py` | 83 | Rich Layout: filter bar + log panel |
| `screens/help.py` | 73 | Rich Layout: command reference table |

**Builder: dead data definitions, no UI.**
- `builder_state.py` survived Streamlit removal because it's pure Python (no deps)
- `frontend/components/` is **empty** (Streamlit pages removed in Fase 8)
- No `builder.py` exists anywhere — the visual builder was Streamlit-only and got deleted

**Rich usage outside console:**
- `main.py` cmd_status / cmd_logs — uses Rich for one-shot CLI output (KEEP)
- No other Rich usage in `src/royaltdn/`

**Textual already installed** — v8.2.7 (`pip list` confirms)

**Data contract: state files are the backbone.**
- Orchestrator writes 7 JSON files atomically → `logs/` every loop cycle
- `StateLoader` reads them with TTL cache → UI renders from same dict
- Signal files: `pause_signal.json`, `scan_now_signal.json` — orchestator polls them in `_check_signals()`
- **This data contract does NOT change** — Textual screens consume the same dicts

**Tests (`tests/test_console.py`):**
- 336 lines, 5 test classes: StateLoader, LogBuffer, Widgets, Commands, HandleCommand
- StateLoader and LogBuffer tests are reusable. Widget/Command tests need rework for Textual.

### Affected Areas

| Path | Why Affected | Action |
|------|-------------|--------|
| `src/royaltdn/frontend/console/app.py` | Main loop + threaded input | **REMOVE** — replaced by TextualApp |
| `src/royaltdn/frontend/console/screens/*.py` | Rich Layout renderers | **REMOVE** — replaced by Textual Screen classes |
| `src/royaltdn/frontend/console/components/widgets.py` | 16 Rich renderable factories | **REMOVE** — replaced by Textual widgets + .tcss |
| `src/royaltdn/frontend/console/components/__init__.py` | Package init | **REMOVE** |
| `src/royaltdn/frontend/console/screens/__init__.py` | Screen registry | **REMOVE** |
| `src/royaltdn/frontend/console/__init__.py` | Package init | **REMOVE** |
| `src/royaltdn/frontend/console/log_handler.py` | LogBuffer pattern | **KEEP** or adapt to Textual Log widget |
| `src/royaltdn/frontend/console/loguru_config.py` | Loguru setup | **KEEP** — unchanged |
| `src/royaltdn/frontend/console/commands.py` | IPC signal files | **KEEP** — unchanged (import from new textual/ module) |
| `src/royaltdn/frontend/console/builder_state.py` | Pure data defs | **KEEP** — 16 indicators, operators, tree builders |
| `src/royaltdn/frontend/console/components/state.py` | StateLoader | **KEEP** — 100% reusable |
| `src/royaltdn/frontend/__init__.py` | Package init | **UPDATE** — change docstring |
| `src/royaltdn/frontend/` | Package layout | **RESTRUCTURE** — add `textual/` package |
| `src/royaltdn/main.py` | CLI commands | **UPDATE** — import TextualApp instead of run_console |
| `tests/test_console.py` | Existing tests | **UPDATE** — keep StateLoader/LogBuffer tests, rewrite rest |
| `tests/test_textual/` | New test dir | **ADD** — new test package |
| `pyproject.toml` | Dependencies | **UPDATE** — add textual/pytest-textual deps (textual already installed but not declared) |
| `src/royaltdn/strategy/schema.py` | Strategy schema | **Unchanged** — defines valid config structure for builder |
| `src/royaltdn/strategy/strategy_store.py` | Strategy persistence | **Unchanged** — builder saves configs here |

### Approaches

1. **Full replacement — remove `console/`, build `textual/` from scratch**
   - **Pro**: Clean slate, no legacy Rich code to maintain; 1:1 screen mapping; Textual's CSS + async is the correct architecture
   - **Pro**: Only ~1,800 lines to replace; StateLoader, commands, builder_state are pure-python and directly importable
   - **Pro**: Textual 8.2.7 already installed
   - **Con**: Breaks the interactive console until textual/ is complete (but user is replacing it anyway)
   - **Con**: Must rewrite test suite from scratch (except StateLoader/LogBuffer)
   - **Effort**: High (~1,500-2,000 new lines across 15+ files)
   - **Delivery**: Should chain into 2-3 PRs (foundation → screens → builder)

2. **Gradual migration — keep console/ running, build textual/ in parallel**
   - **Pro**: console/ stays functional during development
   - **Con**: Two TUIs to maintain simultaneously; code drift risk
   - **Con**: console/ has known Termux/input bugs (Fase 8 issues confirm this)
   - **Con**: Duplicates IPC and state-loading logic across both packages
   - **Effort**: Very High (~3,000+ lines due to duplication + sync)

### Recommendation

**Approach 1 — Full replacement.** Rationale:

1. **Textual is already installed** — no dependency risk
2. The console/ package is only **~1,800 lines** — manageable to replace in one phase
3. **Critical reusable code is pure Python** (StateLoader, commands.py, builder_state.py, LogBuffer) — zero migration cost for these
4. The Orchestrator data contract (`logs/*.json`) is **unchanged** — screens consume the same dicts
5. Fase 8's known Termux/input bugs are a strong motivator to leave `console/` behind
6. Screen mapping is 1:1: DashboardScreen ↔ render_dashboard, ScannerScreen ↔ render_scanner, etc.
7. Rich stays for CLI-only mode (`rich.print` in `main.py` cmd_status/cmd_logs) — no conflict

**Architecture for the new `textual/` package:**

```
src/royaltdn/frontend/textual/
├── __init__.py
├── app.py              # TextualApp — main App class + screen registry
├── screens/
│   ├── __init__.py
│   ├── dashboard.py    # DashboardScreen — KPI cards, positions, signals, risk
│   ├── scanner.py      # ScannerScreen — signal table + history
│   ├── estrategias.py  # EstrategiasScreen — strategy management
│   ├── trades.py       # TradesScreen — trade log + metrics
│   ├── logs.py         # LogsScreen — filter bar + Log widget
│   ├── help.py         # HelpScreen — command reference (migrate from Rich)
│   ├── builder.py      # BuilderScreen — NEW visual rule builder (CRITICAL)
│   └── settings.py     # SettingsScreen — config panel
├── widgets/
│   ├── __init__.py
│   ├── status_bar.py   # StatusBar — custom footer widget
│   ├── metrics_grid.py # MetricsGrid — KPI cards widget
│   ├── log_panel.py    # LogPanel — log viewer (wraps LogBuffer)
│   └── builder_canvas.py # BuilderCanvas — rule tree visualization
├── css/
│   ├── app.tcss        # Main app-level styles
│   ├── screens.tcss    # Shared screen styles
│   └── builder.tcss    # Builder-specific styles
└── signals.py          # IPC command helpers (reused from console/commands.py)
```

**What to reuse from `console/`:**
- `commands.py` → import from `console/commands.py` (or copy to `textual/signals.py`)
- `builder_state.py` → import from `console/builder_state.py` (pure data, no Rich dep)
- `state.py` → `StateLoader` class, reuse directly
- `log_handler.py` → `LogBuffer`, reuse directly (or wrap Textual's Log widget)
- `loguru_config.py` → `setup_logging()`, unchanged

**What to remove:**
- `app.py`, `screens/*.py`, `components/widgets.py`, `components/__init__.py`, `screens/__init__.py`, `__init__.py`

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Textual 8.x API changes | Build breaks if pinned version mismatches | Pin `textual>=8.0,<9` in pyproject.toml |
| Async TUI + sync Orchestrator threading | Race conditions on state reads | StateLoader already uses TTL caching; Textual `set_interval` for polling |
| Builder complexity (16 indicators, rule trees) | High dev effort | Reuse builder_state.py defs + strategy/schema.py validation |
| Existing test suite loss | Regression risk | Keep StateLoader/LogBuffer tests, port widget tests to Textual pattern |
| Termux compatibility | Textual may also have Termux issues | Test with `TEXTUAL_COLORS=16` fallback; Textual is more portable than Rich Live |
| Delivery budget | ~1,500-2,000+ new lines | Chain into 2-3 PRs: (1) Foundation + screens, (2) Builder, (3) Tests + polish |

### Ready for Proposal

**Yes** — this exploration clearly maps the current state, the target architecture, and the migration path. The orchestrator should:

1. Create `proposal.md` defining scope and rollback plan
2. Reference the 3-PR delivery chain
3. Confirm Rich stays for CLI-only mode
4. Confirm builder_state.py, commands.py, state.py, log_handler.py are reused, not rewritten
