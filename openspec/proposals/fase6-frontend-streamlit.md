# Proposal: Fase 6 — Frontend Streamlit

## 1. Title and Metadata

| Field | Value |
|-------|-------|
| **Change Name** | Fase 6 — Frontend Streamlit |
| **Author** | SDD Proposal Agent |
| **Date** | 2026-06-16 |
| **Status** | Draft |
| **Version** | 1.0 |
| **Roadmap Phase** | Fase 6 |
| **Artifact Store** | openspec |

## 2. Executive Summary

RoyalTDN currently operates as a console-only algorithmic trading bot with no visual feedback — the trader runs it blind, relying on log scraping and Telegram alerts. This change introduces a professional Streamlit frontend that reads status from JSON files published by the orchestrator, providing real-time dashboards for bot status, equity curves, trades, scanner signals, strategy configuration, and log viewing. The frontend communicates via `logs/*.json` files with atomic writes, making it fully compatible with both the legacy REST-polling mode and the future Redis-based architecture. Five navigation pages (Dashboard, Scanner, Estrategias, Trades, Logs) give the trader complete operational visibility without requiring a database or backend server.

## 3. Business Problem & Motivation

**The problem**: The bot runs silently. The trader has no way to see:
- Current capital, P&L, or drawdown without checking Alpaca's web UI
- Which signals the scanner generated and why
- Open positions at a glance
- Trade history and win rate without parsing logs
- Whether the bot is running or stopped

**Who benefits**: The trader operating the bot. This frontend turns a headless terminal process into a monitorable system with at-a-glance status, historical context, and drill-down into each module's state. It reduces operational risk by surfacing problems (bot offline, kill switch, drawdown limits) visually instead of relying on Telegram alerts the trader might miss.

**Why now**: The bot has 4 strategies, a scanner module, risk management, and a growing codebase. Without a frontend, debugging and monitoring scale linearly with complexity. This is the minimum visibility layer needed before adding more strategies or running the bot unattended.

## 4. Scope

### In Scope

1. **Status JSON publishing** from the orchestrator — `_publish_status()` method writes 7 JSON files to `logs/` on every legacy loop cycle, on trade entry/exit, and on scanner run
2. **Streamlit app** with 5 pages via `st.navigation`:
   - 📊 Dashboard — metric cards, equity curve, drawdown chart, open positions, bot status
   - 🔍 Scanner — signals table with colored rows, distribution chart, scan history
   - ⚙️ Estrategias — strategy list with activate/pause, expander per strategy
   - 📈 Trades — full trade history with filters, summary metrics, P&L chart, CSV export
   - 📋 Logs — real-time log viewer with level/module filter, search, auto-scroll
3. **File-based communication** — frontend reads `logs/*.json`, no Redis dependency
4. **Graceful degradation** — missing files, corrupt JSON, or empty state handled on every page
5. **Atomic writes** — temp file + rename to prevent partial reads
6. **CSV export** for trades table

### Out of Scope

- WebSocket or real-time push updates (file polling at 2-3s is sufficient for a local bot)
- Authentication, user management, or security (local-only, single-user)
- Mobile or responsive design (desktop-only Streamlit)
- Backtesting UI or historical backtest visualization
- Strategy parameter editing via UI (view-only; changes through config/env vars only)
- Redis integration for the frontend (file-based is the bridge; Redis integration belongs to a later phase)
- Alert/notification configuration from the UI
- Dark mode / theme customization beyond Streamlit defaults

## 5. Architecture

### Component Diagram

```
┌──────────────────────┐         writes          ┌──────────────────────┐
│                      │ ───────────────────────> │                      │
│   Orchestrator       │    logs/status.json      │   Streamlit          │
│   (legacy loop)      │    logs/equity.json      │   Frontend           │
│                      │    logs/positions.json   │   (app.py)           │
│  ┌────────────────┐  │    logs/signals.json     │                      │
│  │ _publish_status│  │    logs/scanner_results  │  polls every 2-3s    │
│  │ _get_equity    │  │    logs/strategies.json  │  via st.rerun        │
│  │ _append_trade  │  │    logs/trades.json      │                      │
│  └────────────────┘  │                          │  5 pages:            │
│                      │                          │  ├─ Dashboard        │
│  Scanner            │  │                          │  ├─ Scanner          │
│  (publishes after   │  │                          │  ├─ Estrategias     │
│   each scan cycle)  │  │                          │  ├─ Trades           │
│                      │                          │  └─ Logs             │
└──────────────────────┘                          └──────────────────────┘
         │                                                   │
         │   reads account                                   │   reads files
         ▼                                                   ▼
  ┌──────────────┐                                  ┌──────────────┐
  │ Alpaca API   │                                  │ logs/*.json  │
  │ (Paper)      │                                  │ (file system)│
  └──────────────┘                                  └──────────────┘
```

### Data Flow

1. Orchestrator legacy loop runs every 60s
2. On each cycle, orchestrator calls `_publish_status()`:
   - Reads account equity from Alpaca
   - Gathers current positions, signals, scanner results
   - Writes 7 JSON files atomically to `logs/`
3. Scanner publishes to `logs/scanner_results.json` after each scan
4. Trade execution appends to `logs/trades.json` on entry and exit
5. Streamlit frontend polls these files every 2-3 seconds
6. Each page parses the relevant JSON and renders charts/tables

### File Format Specifications

#### `logs/status.json`
```json
{
  "bot_status": "ONLINE" | "OFFLINE" | "KILLED",
  "mode": "legacy" | "modular",
  "timestamp": "2026-06-16T10:30:00Z",
  "last_signal": {"action": "BUY", "price": 450.20, "timestamp": "..."},
  "last_error": null,
  "uptime_seconds": 3600,
  "symbols": ["SPY", "QQQ"],
  "scanner_enabled": true,
  "version": "1.0.0"
}
```

#### `logs/equity.json`
```json
{
  "initial_equity": 100000.00,
  "current_equity": 101234.50,
  "pnl_day": 1234.50,
  "pnl_day_pct": 1.23,
  "drawdown": -0.5,
  "drawdown_pct": -0.05,
  "sharpe": 1.45,
  "equity_curve": [
    {"timestamp": "2026-06-16T09:30:00Z", "equity": 100500.00},
    {"timestamp": "2026-06-16T10:00:00Z", "equity": 100800.00}
  ],
  "updated_at": "2026-06-16T10:30:00Z"
}
```

#### `logs/positions.json`
```json
{
  "open_positions": [
    {
      "symbol": "SPY",
      "side": "long",
      "qty": 100,
      "entry_price": 445.00,
      "current_price": 450.20,
      "pnl_unrealized": 520.00,
      "entry_at": "2026-06-16T09:30:00Z"
    }
  ],
  "total_open": 1,
  "updated_at": "2026-06-16T10:30:00Z"
}
```

#### `logs/signals.json`
```json
{
  "today_count": 3,
  "last_signals": [
    {
      "action": "BUY",
      "symbol": "SPY",
      "price": 450.20,
      "strategy": "sma_crossover",
      "timestamp": "2026-06-16T10:00:00Z",
      "metadata": {"fast_sma": 448.5, "slow_sma": 447.2}
    }
  ],
  "updated_at": "2026-06-16T10:30:00Z"
}
```

#### `logs/scanner_results.json`
```json
{
  "scan_timestamp": "2026-06-16T10:00:00Z",
  "symbols_scanned": 100,
  "symbols_passed": 45,
  "total_signals": 12,
  "top_signals": [
    {
      "symbol": "XLK",
      "strategy": "factor_rotation",
      "action": "RANK",
      "price": 180.50,
      "score": 2.34,
      "metadata": {"momentum": 15.2, "volatility": 6.5}
    }
  ],
  "history": [ ... ]
}
```

#### `logs/strategies.json`
```json
{
  "strategies": [
    {
      "name": "sma_crossover",
      "active": true,
      "params": {"fast_period": 5, "slow_period": 20},
      "validation": true,
      "last_signal": "BUY",
      "signal_count": 15,
      "symbol": "SPY"
    }
  ],
  "updated_at": "2026-06-16T10:30:00Z"
}
```

#### `logs/trades.json`
```json
{
  "total_trades": 42,
  "win_rate": 64.3,
  "profit_factor": 2.1,
  "total_pnl": 1234.50,
  "trades": [
    {
      "symbol": "SPY",
      "side": "long",
      "entry_price": 445.00,
      "exit_price": 450.20,
      "qty": 100,
      "pnl": 520.00,
      "entry_at": "2026-06-16T09:30:00Z",
      "exit_at": "2026-06-16T10:00:00Z",
      "strategy": "sma_crossover",
      "slippage_bps": 0.5,
      "execution_method": "market"
    }
  ],
  "updated_at": "2026-06-16T10:30:00Z"
}
```

### Update Frequency & Lifecycle

| File | Written By | Frequency | Append/Overwrite |
|------|-----------|-----------|-----------------|
| `status.json` | Orchestrator | Every legacy cycle (60s) | Overwrite |
| `equity.json` | Orchestrator | Every legacy cycle (60s) | Overwrite |
| `positions.json` | Orchestrator | Every legacy cycle (60s) | Overwrite |
| `signals.json` | Orchestrator | Every legacy cycle (60s) | Overwrite |
| `scanner_results.json` | Scanner | On each scan (~60min) | Overwrite |
| `strategies.json` | Orchestrator | Every legacy cycle (60s) | Overwrite |
| `trades.json` | Orchestrator | On trade entry/exit | Append |

### Error Handling

| Scenario | Behavior |
|----------|----------|
| File doesn't exist | Page shows "Waiting for data..." with a subtle loading indicator |
| File is empty/malformed JSON | Page logs warning, shows "No data available" for that section |
| Partial/corrupt file (mid-write) | Atomic write prevents this (temp + rename); if still corrupt, fallback to last valid read |
| All files missing | Frontend shows "Bot offline — no status files found in logs/" |
| No trades yet | Trades page shows empty table with "No trades executed this session" |
| Scanner never ran | Scanner page shows "Scanner not initialized or no scan completed yet" |
| Permission error reading file | Show error message with path; suggest checking file permissions |
| File too large (trades.json) | Limit in-memory to last 1000 entries; pagination planned for future |

## 6. Dependencies

| Package | Version | Justification |
|---------|---------|---------------|
| `streamlit` | >=1.28 | Core framework. `st.navigation` for multipage support (stable since 1.28). |
| `plotly` | >=5.18 | Interactive charts (equity curve, drawdown, distribution). Streamlit native `st.plotly_chart` support. |
| `pandas` | >=2.1 | Already in `fase0.txt`. Used for data manipulation in frontend. |
| `numpy` | >=1.26 | Already in `fase0.txt`. Used for chart calculations. |

Streamlit >=1.28 is specifically chosen because `st.navigation` replaces the deprecated `st.Page` / `st.nav` experimental API. Plotly >=5.18 ensures compatibility with Streamlit's native chart event handling.

No new runtime dependencies beyond these — the frontend uses standard library (`json`, `pathlib`, `datetime`) for file I/O.

## 7. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| File corruption from concurrent writes | Medium | Low | Atomic writes: write to `.tmp` then `os.rename()` (atomic on Linux) |
| Frontend reads partial JSON | Medium | Low | Atomic writes guarantee full file or old file; validation on read with `try/except json.JSONDecodeError` |
| Polling overhead (2-3s read of 7 small files) | Low | Low | Files are < 100KB each; `st.rerun` is cheap; Streamlit's caching avoids re-read on unchanged files |
| Streamlit memory with large trade log | Low | Low | Cap displayed trades at last 1000; use pagination pattern; file is append-only so it grows linearly with trades/day |
| Bot not running → stale files | Medium | Low | Show "last updated" timestamp on every page; flag files older than 5 minutes as stale |
| Multiple bot instances writing to same `logs/` | Low | Low | Single-instance design; no action needed |
| Streamlit port conflict | Low | Low | Configurable via `--server.port`; document in README |
| Logs growing unbounded | Low | Medium | Rotate `trades.json` and `logs/` in future phase; for now, keep last 1000 trades in memory |

## 8. Acceptance Criteria

### Dashboard (📊)
- [ ] Metric cards display: capital ($), P&L day ($ and %), drawdown (%), open positions count, signals today, Sharpe ratio
- [ ] Equity curve renders as Plotly line chart with hover tooltip
- [ ] Drawdown chart renders as Plotly filled area chart below equity curve
- [ ] Open positions table shows symbol, side, qty, entry price, current P&L
- [ ] Bot status indicator shows green "ONLINE" or red "OFFLINE"/"KILLED" badge
- [ ] Status badge includes mode (legacy/modular), last signal time, last error
- [ ] All cards gracefully handle missing/empty data (show "—" or "Waiting...")
- [ ] Page refreshes automatically every 3 seconds

### Scanner (🔍)
- [ ] Scanner config selector shows universe, min volume, min price, max spread from env
- [ ] Signals table renders with colored rows: green background for BUY, red for SELL, blue for RANK
- [ ] Distribution bar chart by strategy (Plotly) shows signal count per strategy
- [ ] Last 10 scans history is displayed in reverse chronological order
- [ ] Empty state shown when scanner hasn't run yet
- [ ] Preserves column alignment and readability on 1920x1080

### Estrategias (⚙️)
- [ ] All loaded strategies listed with name, active/inactive badge
- [ ] Each strategy has an activate/pause toggle (visual only — affects display, not bot)
- [ ] Expander per strategy shows: params table, validation status (✅/❌), last signal, signal count
- [ ] Strategy-to-symbol assignment displayed (symbol field from params)
- [ ] Graceful handling if `strategies.json` missing

### Trades (📈)
- [ ] Full trade history table with columns: symbol, side, entry/exit price, qty, P&L, dates, strategy
- [ ] Filters: date range, symbol, strategy dropdown, side (buy/sell)
- [ ] Summary metrics row: total trades, win rate %, profit factor, P&L total
- [ ] P&L per trade bar chart (green for positive, red for negative)
- [ ] Return distribution histogram (Plotly)
- [ ] CSV export button downloads `trades_export_YYYYMMDD.csv`
- [ ] Default sort by exit date descending
- [ ] Empty state: "No trades executed yet"

### Logs (📋)
- [ ] Real-time log viewer with auto-scroll to bottom
- [ ] Filter by level: checkboxes for INFO, WARNING, ERROR, DEBUG (all enabled by default)
- [ ] Filter by module: text input filtering log source names
- [ ] Text search input with case-insensitive matching
- [ ] Clear button clears the displayed log buffer (visual only, doesn't delete files)
- [ ] Shows last 1000 lines max
- [ ] Auto-refresh every 2 seconds

### JSON Publishing
- [ ] All 7 JSON files written atomically (`.tmp` → rename)
- [ ] Files are valid JSON and parse correctly
- [ ] `trades.json` appends new trades (not overwrites)
- [ ] All other files overwrite (not append)
- [ ] Publishing does NOT block the main loop (async task or fast sync write)
- [ ] Error during publish is logged but does not crash the orchestrator

### Error Handling
- [ ] Frontend starts and displays pages even when no JSON files exist
- [ ] Corrupt JSON file shows warning, doesn't crash the page
- [ ] Missing individual file doesn't crash other pages
- [ ] Bot stopped → status indicator goes red within 2-3 cycles

## 9. Implementation Plan

### Step 1 — Install dependencies
```bash
pip install streamlit>=1.28 plotly>=5.18
```

### Step 2 — Create `requirements/fase6.txt`
- `streamlit>=1.28`
- `plotly>=5.18`

### Step 3 — Add `_publish_status()` to orchestrator
- New method writes all 7 JSON files to `logs/`
- Atomic write pattern: `_atomic_write(path, data)` -> `path.tmp` then `os.rename()`
- Reads account equity, positions, strategy state from orchestrator fields
- Logs errors without raising

### Step 4 — Add `_get_current_equity()` to orchestrator
- Returns current equity from Alpaca account
- Cached per cycle to avoid rate limits

### Step 5 — Modify legacy loop to call `_publish_status()`
- Call at end of each legacy cycle iteration (after signal processing)
- Call on startup (initial status) and shutdown (final status)

### Step 6 — Modify scanner to publish results
- After `scan()` completes, write `logs/scanner_results.json`
- Include top signals, scan metadata, history array

### Step 7 — Modify trade close to append to `logs/trades.json`
- On `_execute_signal()` SELL path, after trade recorded, append to trades file
- Read existing, append, write atomically
- Include P&L, slippage, execution method

### Step 8 — Create frontend package structure
```
src/royaltdn/frontend/
├── __init__.py
├── app.py                 # Entry point with st.navigation
├── pages/
│   ├── __init__.py
│   ├── dashboard.py       # 📊 Dashboard page
│   ├── scanner.py         # 🔍 Scanner page
│   ├── estrategias.py     # ⚙️ Estrategias page
│   ├── trades.py          # 📈 Trades page
│   └── logs.py            # 📋 Logs page
└── components/
    ├── __init__.py
    ├── loaders.py          # JSON file readers with error handling
    └── charts.py           # Plotly chart builders
```

### Step 9 — Implement each page
1. `components/loaders.py` — atomic JSON loader functions
2. `components/charts.py` — equity curve, drawdown, P&L, distribution chart builders
3. `pages/dashboard.py` — metric cards, charts, positions table, status indicator
4. `pages/scanner.py` — signals table, distribution chart, scan history
5. `pages/estrategias.py` — strategy list, expanders, toggles
6. `pages/trades.py` — trade table, filters, metrics, chart, CSV export
7. `pages/logs.py` — log viewer with filters and search
8. `app.py` — `st.navigation` with 5 pages

### Step 10 — Add tests
- Unit tests for `_publish_status()` and `_atomic_write()` in orchestrator
- Unit tests for JSON loaders (missing file, corrupt JSON, empty file)
- Unit tests for chart builders (returns valid Plotly figure with empty data)
- Integration test: write sample JSON files, verify frontend loads without errors

### Step 11 — Integration testing
- Run bot in legacy mode for 5-10 cycles
- Verify all JSON files appear in `logs/`
- Run frontend with `streamlit run src/royaltdn/frontend/app.py --server.port 8501`
- Manually verify each page renders with live data

### Step 12 — Documentation
- Add "Frontend" section to README
- Document how to run the frontend, port config, and troubleshooting
- Document JSON file format for future developers

## 10. Effort Estimate

| Metric | Value |
|--------|-------|
| **New files** | ~12 (1 requirements, 1 `__init__.py`, 1 `app.py`, 5 pages, 2 components, ~2 tests) |
| **Modified files** | 2 (`orchestrator.py`, `scanner.py`) |
| **Total changed lines** | ~800–1000 (JSON publishing: ~150 lines, frontend: ~600 lines, tests: ~150 lines) |
| **Estimated effort** | 1 developer × 3–4 days |
| **Risk level** | Low — file I/O patterns are well-understood, Streamlit APIs are mature, no new infra |
