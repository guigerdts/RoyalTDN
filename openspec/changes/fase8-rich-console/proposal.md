# Proposal: Fase 8 — Rich Interactive Console

## Intent

Eliminate Streamlit entirely, replace with a Rich keyboard-navigable TUI dashboard, migrate all stdlib logging to Loguru across 17 modules, and add CLI subcommands to main.py. The `logs/*.json` contract remains unchanged — the console reads the same files the orchestrator already publishes.

## Scope

### In Scope
- Delete `src/royaltdn/frontend/` (app.py, 5 pages, builder page, 2 components)
- Uninstall streamlit, plotly from `requirements/fase6.txt`
- Install rich, loguru, tqdm, colorama
- Migrate `import logging` + `getLogger()` → `from loguru import logger` in 17 modules
- Create `src/royaltdn/console/` with LogBuffer, StateLoader, widgets, 5 screens
- `app.py`: Rich `Live` loop + keyboard navigation
- CLI subcommands: `run`, `status`, `logs`, `pause`, `resume`, `scanner`
- Orchestrator support for pause/resume signal files
- Tests for console screens, loaders, and commands

### Out of Scope
- Web UI (console replaces browser — web may return later)
- Grafana/Prometheus integration
- Theme toggles (Rich default theme only)
- Textual migration (deferred — Rich Live covers this phase)

## Capabilities

### New
- `rich-console`: Rich TUI with 5 keyboard-navigable screens reading `logs/*.json`
- `loguru-logging`: Loguru sinks (file rotation, LogBuffer) replacing stdlib logging across all modules
- `cli-subcommands`: CLI with 6 subcommands via main.py, each with formatted output

### Modified
- `fase6-frontend-streamlit`: Replaced — spec archived, no delta required

## Architecture

```
main.py ──→ CLI dispatch
  ├── run ────→ app.py (Rich Live)
  │               ├── screens/  (5 Rich Layout screens)
  │               ├── widgets/  (cards, tables, panels, badges)
  │               ├── stateloader/ (reads logs/*.json)
  │               ├── LogBuffer (loguru sink, last 1000 lines)
  │               └── key bindings → signal files
  ├── status ──→ formatted table from logs/status.json
  ├── logs  ────→ tail -f logs/bot.log
  ├── pause ────→ touch logs/pause.signal
  ├── resume ───→ rm -f logs/pause.signal
  └── scanner ──→ touch logs/scan.signal

orchestrator.py: polls pause.signal each cycle, Loguru sinks configured once
```

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Rich over Textual | Textual is async-only, heavier dep. Rich `Live` is sync, sufficient for polling-based dashboard |
| Loguru over stdlib | Zero boilerplate, built-in rotation, easy to sink into LogBuffer for console |
| Keep logs/*.json | No orchestrator changes — console reads same files Streamlit did |
| Signal files for IPC | Filesystem as IPC for pause/resume/scan — simple, no Redis/pubsub needed |

## Affected Areas

| Area | Impact | Files |
|------|--------|-------|
| `src/royaltdn/frontend/` | REMOVED | app.py, 6 pages, 2 components |
| `src/royaltdn/console/` | CREATED | ~10 files (screens, widgets, stateloader, logbuffer, app) |
| `src/royaltdn/main.py` | MODIFIED | CLI dispatching, Loguru init |
| `src/royaltdn/orchestrator.py` | MODIFIED | Loguru, pause/resume polling |
| 17 `*.py` modules | MODIFIED | `import logging` → `from loguru import logger` |
| `requirements/fase6.txt` | REMOVED | streamlit, plotly |
| `requirements/fase8.txt` | CREATED | rich, loguru, tqdm, colorama |

## Migration: Logging

Per-file mechanical change: remove `import logging`, replace `logging.getLogger(...)` with `from loguru import logger`. Single config point in entry point:

```python
logger.add("logs/bot.log", rotation="10 MB", retention="30 days")
logger.add(LogBuffer, level="INFO")
```

LogBuffer retains last 1000 lines for the log screen. Format string stays consistent.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Loguru output format differs | Low | Match existing format in `logger.add()` config |
| Console blocks on I/O | Low | JSON reads <5ms, Rich renders async via `Live` |
| No web dashboard access | Medium | Intentional — console replaces browser UI |
| Key capture conflicts with terminal | Low | stdin polling fallback if pynput unavailable |

## Rollback

1. `git checkout HEAD -- src/royaltdn/frontend/ src/royaltdn/main.py src/royaltdn/orchestrator.py`
2. Uninstall rich, loguru, tqdm, colorama; reinstall streamlit, plotly
3. Revert requirements files

`logs/*.json` contract unchanged — rollback is strictly UI + logging layer.

## Dependencies

- `rich>=13.0`, `loguru>=0.7`, `tqdm>=4.65`
- `colorama>=0.4` (Rich includes it, explicit for CLI output)

## Success Criteria

- [ ] Zero `import streamlit` or `import plotly` remain
- [ ] `python -m royaltdn run` opens Rich console with live data from orchestrator
- [ ] All 5 screens keyboard-navigable without errors
- [ ] `python -m royaltdn pause` stops bot; `resume` restarts it
- [ ] `python -m royaltdn status` prints formatted status table
- [ ] `python -m royaltdn logs` tails bot.log to stdout
- [ ] Zero `logging.getLogger()` calls remain across all 17 modules
- [ ] `python -m royaltdn` prints help listing all 6 subcommands
- [ ] Console tests pass for screen rendering, state loading, and commands
