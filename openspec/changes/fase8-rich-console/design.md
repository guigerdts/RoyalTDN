# Design: Fase 8 — Rich Interactive Console

## Technical Approach

Replace Streamlit web UI with a Rich TUI that polls `logs/*.json` at 4 FPS. Migrate all `logging` → Loguru in one pass. Add 6 CLI subcommands and filesystem IPC signals for pause/resume/scan. The console is read-only w.r.t. orchestrator data — it reads the same JSON files Streamlit did, no orchestrator data contract changes.

Specs: console.md (screens, keybindings, StateLoader), loguru-migration.md (16 modules), cli-commands.md (6 subcommands, IPC signals), data-contract.md (JSON contracts unchanged).

## Architecture Decisions

| Option | Tradeoffs | Decision |
|--------|-----------|----------|
| Rich `Live` vs Textual | Textual async-only, heavier dep. Rich sync, sufficient for polling-based dashboard | **Rich Live** |
| `logging` → Loguru | Zero boilerplate, built-in rotation, easy sink to LogBuffer | **Loguru** |
| Signal files vs Redis/pubsub | No infra needed. Simple JSON read/unlink. <5ms cost | **Signal files** |
| Delete builder_state.py | Contains Streamlit `st.session_state` imports throughout | **Refactor only** — keep INDICATOR_DEFS/OPERATOR_GROUPS/config builders; extract `st` dependency |

## Data Flow

```
            ┌────────────────────────────────────────────────┐
            │             Orchestrator (thread)               │
            │  Main loop → _publish_status() → _atomic_write │
            └────┬─────────────────────────────────────┬──────┘
                 │ publishes 7 JSON files               │ checks signal files
                 ▼ each cycle                           ▼
         ┌───────────────┐                     ┌───────────────┐
         │  logs/*.json  │                     │ pause_signal  │
         │  - status     │                     │ scanner_trigger│
         │  - equity     │◄──── reads ────┐    └───────┬───────┘
         │  - positions  │                │            │
         │  - signals    │                │      orchestrator polls
         │  - strategies │                │      → pause/resume/scan
         │  - trades     │                │
         │  - scanner_rs │                │
         └───────────────┘                │
                                          ▼
         ┌────────────────────────────────────────────────┐
         │              Console (main thread)              │
         │  StateLoader (TTL cache) → Widgets → Live loop │
         │  LogBuffer (loguru sink, 200 lines) ← loguru   │
         │  get_key() → handle_key() → switch screen/signal│
         └────────────────────────────────────────────────┘
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/royaltdn/console/__init__.py` | Create | Package init |
| `src/royaltdn/console/log_handler.py` | Create | `LogBuffer` class + `setup_console_log_handler()` |
| `src/royaltdn/console/components/state.py` | Create | `StateLoader` with TTL cache |
| `src/royaltdn/console/components/widgets.py` | Create | 12 Rich renderable functions |
| `src/royaltdn/console/components/__init__.py` | Create | Package init |
| `src/royaltdn/console/screens/__init__.py` | Create | Screen dispatch + 5 screen modules |
| `src/royaltdn/console/screens/dashboard.py` | Create | Dashboard layout |
| `src/royaltdn/console/screens/scanner.py` | Create | Scanner layout |
| `src/royaltdn/console/screens/estrategias.py` | Create | Estrategias layout |
| `src/royaltdn/console/screens/trades.py` | Create | Trades layout |
| `src/royaltdn/console/screens/logs.py` | Create | Logs layout with filters |
| `src/royaltdn/console/commands.py` | Create | `pause_bot()`, `resume_bot()`, `trigger_scanner()` |
| `src/royaltdn/console/app.py` | Create | `run_console()`, `get_key()`, `handle_key()`, `render_screen()` |
| `src/royaltdn/console/loguru_config.py` | Create | `setup_logging()` with 3 sinks |
| `src/royaltdn/main.py` | Modify | Add 6 subcommands, replace logging with Loguru |
| `src/royaltdn/orchestrator.py` | Modify | Add IPC signal polling at top of loop |
| `src/royaltdn/ingestion/data_ingestor.py` | Modify | `logging` → Loguru, remove `basicConfig` |
| `src/royaltdn/strategy/sma_strategy.py` | Modify | `logging` → Loguru, remove `basicConfig` |
| `src/royaltdn/strategy/bollinger_rsi.py` | Modify | `logging` → Loguru |
| `src/royaltdn/strategy/momentum_atr.py` | Modify | `logging` → Loguru |
| `src/royaltdn/strategy/factor_rotation.py` | Modify | `logging` → Loguru |
| `src/royaltdn/execution/twap.py` | Modify | `logging` → Loguru |
| `src/royaltdn/storage/db.py` | Modify | `logging` → Loguru |
| `src/royaltdn/monitoring/tca.py` | Modify | `logging` → Loguru |
| `src/royaltdn/scanner/scanner.py` | Modify | `logging` → Loguru |
| `src/royaltdn/scanner/filters.py` | Modify | `logging` → Loguru |
| `src/royaltdn/scanner/universe.py` | Modify | `logging` → Loguru |
| `src/royaltdn/risk_manager.py` | Modify | `logging` → Loguru |
| `src/royaltdn/alerts.py` | Modify | `logging` → Loguru |
| `src/royaltdn/legacy_polling.py` | Modify | `logging` → Loguru, remove `basicConfig` |
| `src/royaltdn/frontend/app.py` | Delete | Streamlit entry — replaced by console |
| `src/royaltdn/frontend/pages/` | Delete | 6 Streamlit page modules |
| `src/royaltdn/frontend/components/charts.py` | Delete | Plotly charts |
| `src/royaltdn/frontend/components/loaders.py` | Delete | Streamlit loaders |
| `src/royaltdn/frontend/components/backtest_charts.py` | Delete | Plotly backtest charts |
| `src/royaltdn/frontend/components/builder_state.py` | Refactor | Extract INDICATOR_DEFS/config builders; remove `st.session_state` |
| `requirements/fase6.txt` | Delete | streamlit, plotly |
| `requirements/fase8_console.txt` | Create | rich, loguru, tqdm, colorama |

## Interfaces / Contracts

### LogBuffer (log_handler.py)

```python
class LogBuffer:
    def __init__(self, max_lines: int = 200): ...
    def add(self, record: str) -> None: ...           # Loguru sink callable
    def get_lines(self, level_filter: str | None = None,
                  module_filter: str | None = None,
                  text_filter: str | None = None,
                  last_n: int | None = None) -> list[str]: ...
    def get_recent(self, n: int = 5) -> list[str]: ...
```

### StateLoader (components/state.py)

```python
class StateLoader:
    def __init__(self, logs_dir: str = "logs", cache_ttl: float = 1.0): ...
    def load_status(self) -> dict: ...
    def load_equity(self) -> list: ...
    def load_positions(self) -> list: ...
    def load_scanner_results(self) -> dict: ...
    def load_strategies(self) -> dict: ...
    def load_trades(self) -> list: ...
    def load_all(self) -> dict: ...
```

### Widgets (components/widgets.py)

Each returns a Rich renderable — `Panel`, `Table`, or `Layout`. Signatures:

```python
create_header(state: dict) -> Panel
create_kpi_cards(state: dict) -> Table
create_positions_table(state: dict) -> Table
create_signals_table(signals: list) -> Table
create_risk_panel(state: dict) -> Panel
create_scanner_table(scanner_data: dict) -> Table
create_strategies_table(strategies_data: dict, user_strategies: list) -> Table
create_trades_table(trades: list) -> Table
create_trade_metrics(trades: list) -> Panel
create_log_panel(log_buffer, level_filter, module_filter, text_filter) -> Panel
create_footer() -> Panel
create_empty_state(message: str) -> Panel
```

### Screens (screens/\_\_init\_\_.py)

```python
def render_dashboard(state: dict, log_buffer: LogBuffer, **kw) -> Layout: ...
def render_scanner(state: dict, log_buffer: LogBuffer, **kw) -> Layout: ...
def render_estrategias(state: dict, log_buffer: LogBuffer, **kw) -> Layout: ...
def render_trades(state: dict, log_buffer: LogBuffer, **kw) -> Layout: ...
def render_logs(state: dict, log_buffer: LogBuffer, level_filter=None,
               module_filter=None, text_filter=None) -> Layout: ...
```

### Loguru Config (loguru_config.py)

```python
def setup_logging(log_buffer: LogBuffer | None = None) -> None:
    """Remove default handler. Add file sink (rotation 10MB, 7d retention),
    stderr sink (colorize, DEBUG), and optional LogBuffer sink."""
```

### IPC Signal Files

| Signal File | Format | Consumer | Effect |
|---|---|---|---|
| `logs/pause_signal.json` | `{"action": "pause"\|"resume", "timestamp": "..."}` | Orchestrator | Sets `self.paused` |
| `logs/scanner_trigger.json` | `{"action": "scan_now", "timestamp": "..."}` | Orchestrator | Calls `self._scanner.scan()` |

### CLI Dispatch (main.py)

```
royaltdn {run|status|logs|pause|resume|scanner}
  run      → threading.Thread(orchestrator) + run_console() in main thread
  status   → one-shot Rich dashboard render → stdout
  logs     → tail -50 logs/bot.log with Rich syntax
  pause    → write pause_signal.json {action: pause}
  resume   → write pause_signal.json {action: resume}
  scanner  → write scanner_trigger.json {action: scan_now}
```

## Loguru Migration

16 modules, all mechanical: `import logging` + `getLogger()` → `from loguru import logger`. `.info()`, `.warning()`, `.error()` calls are compatible across both APIs.

4 modules with `basicConfig()` (main.py, orchestrator.py, data_ingestor.py, sma_strategy.py, legacy_polling.py): remove `basicConfig` — single `setup_logging()` in main.py handles all sinks.

Tests using `self.assertLogs()` need migration to `loguru` test sink (`logger.add(capturer, ...)`).

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | StateLoader TTL cache, missing file, corrupt JSON | pytest parametrize temp dirs |
| Unit | LogBuffer add/filter/trim/thread-safety | pytest threading + deque |
| Unit | Widget render functions with mock state | Return type checks (Panel/Table/Layout) |
| Integration | Screen layouts with sample data | Layout[str] contains expected sections |
| E2E | `royaltdn status` / `logs` / `pause` exit codes | subprocess.run + stdout checks |
| E2E | Console keyboard navigation | stdin pipe simulation |

## Implementation Sequence

| Hito | Tasks | Deps |
|------|-------|------|
| **H1**: Foundation + Loguru | T1 (delete frontend), T2 (deps), T3 (Loguru 16 modules) | None |
| **H2**: Data layer + Widgets | T4 (StateLoader), T5 (LogBuffer), T6 (widgets) | H1 |
| **H3**: Screens + Commands | T7 (5 screens), T8 (commands.py), T9 (app.py) | H2 |
| **H4**: CLI + IPC | T10 (main.py 6 subcommands), T11 (orchestrator IPC) | H3 |
| **H5**: Cleanup + Tests | T12 (cleanup), T13 (tests) | H4 |

No circular dependencies — each milestone builds on the previous.

## Open Questions

- [ ] builder_state.py: confirm whether to keep (extract logic) or delete entirely. Currently has `import streamlit as st` inside every function.
- [ ] Terminal size detection: do existing tests cover Rich terminal mocking, or do we need a `CONSOLE_WIDTH` env var for CI?
- [ ] pynput vs stdin polling: confirm stdin polling is sufficient (no edge case in tmux/VSCode terminal)
