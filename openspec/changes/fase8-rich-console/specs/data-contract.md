# Data Contract — JSON File Contracts (Preserved from Fase 6)

## Purpose

The console is a read-only consumer of JSON status files published by Orchestrator. Every file is written atomically via `_atomic_write()` (tmp + os.replace). Console never writes to these files — it only reads them at each refresh cycle.

## JSON File Contracts

### `logs/status.json`

| Field | Type | Description |
|-------|------|-------------|
| `bot_status` | string | `"ONLINE"`, `"OFFLINE"`, `"KILLED"` |
| `mode` | string | `"modular"` or `"legacy"` |
| `timestamp` | ISO-8601 | Last status publish time |
| `last_signal` | object\|null | Last signal summary: `{action, price, symbol, strategy, timestamp, metadata}` |
| `last_error` | string\|null | Last error message |
| `uptime_seconds` | int | Bot uptime in seconds |
| `symbols` | string[] | Active symbols |
| `scanner_enabled` | bool | Whether scanner is active |
| `version` | string | Bot version |

### `logs/equity.json`

| Field | Type | Description |
|-------|------|-------------|
| `initial_equity` | float | Starting capital |
| `current_equity` | float | Current account equity |
| `pnl_day` | float | Day P&L in USD |
| `pnl_day_pct` | float | Day P&L as % |
| `drawdown` | float | Max drawdown in USD |
| `drawdown_pct` | float | Max drawdown as % |
| `sharpe` | float\|null | Sharpe ratio |
| `equity_curve` | array | Last 1000 `[{timestamp, equity}]` points |
| `updated_at` | ISO-8601 | Last update |
| `stale` | bool | Equity data freshness |

### `logs/positions.json`

| Field | Type | Description |
|-------|------|-------------|
| `open_positions` | array | `[{symbol, side, qty, entry_price, current_price, pnl_unrealized, entry_at, strategy}]` |
| `total_open` | int | Count of open positions |
| `updated_at` | ISO-8601 | Last update |

### `logs/scanner_results.json`

| Field | Type | Description |
|-------|------|-------------|
| `last_scan` | object | `{timestamp, total_signals, top_signals: [{time, symbol, action, price, score, strategy}]}` |
| `scan_history` | array | Last 5 scan records: `[{timestamp, total_symbols, passed_symbols, signals_count, top_signals}]` |
| `updated_at` | ISO-8601 | Last update |

### `logs/strategies.json`

| Field | Type | Description |
|-------|------|-------------|
| `strategies` | array | Predefined: `[{name, active, params, validation, last_signal, signal_count, symbol, timeframe}]` |
| `updated_at` | ISO-8601 | Last update |

### `logs/trades.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_trades` | int | Trade count |
| `win_rate` | float | Win rate % |
| `profit_factor` | float\|null | Gross profit / gross loss |
| `total_pnl` | float | Sum of all trade P&L |
| `trades` | array | Last 50: `[{symbol, side, entry_price, exit_price, qty, pnl, entry_at, exit_at, strategy, slippage_bps, execution_method}]` |
| `updated_at` | ISO-8601 | Last update |

## Contract Rules

1. **Read-only**: Console SHALL NOT write to any `logs/*.json` file
2. **Missing file**: Console SHALL render "No data" / empty state for each panel whose file is missing
3. **Corrupt JSON**: Console SHALL catch `json.JSONDecodeError`, log warning, render empty state
4. **Stale data**: `status.json` is authoritative — if it's missing, console SHALL show "Bot OFFLINE — no status published"
5. **Refresh**: Console MUST re-read all files at each `Live` refresh cycle (4 FPS)

## Acceptance Criteria

1. [CRITICAL] Console MUST render all 5 screens from JSON files without ever writing to `logs/`
2. [CRITICAL] Missing or corrupt JSON MUST produce empty state, never a crash
3. [MAJOR] Each KPI on dashboard MUST map to a field in the JSON contract above
4. [MAJOR] `status.json` absence MUST show "Bot OFFLINE"
5. [MINOR] Equity curve data SHALL display most recent 100 points when available
