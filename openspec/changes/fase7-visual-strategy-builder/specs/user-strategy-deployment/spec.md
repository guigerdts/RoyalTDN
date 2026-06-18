# User Strategy Deployment Specification

## Purpose

JSON schema v1 for user strategies, `user_strategies/*.json` store, `.active` symlink, and 30s polling watcher in Orchestrator. NEW domain — full spec.

## Requirements

### Requirement: Strategy JSON Schema v1

Each user strategy file SHALL conform to this schema.

| Field | Type | Req? | Default | Constraints |
|-------|------|------|---------|-------------|
| `version` | int | Y | 1 | Must be 1 |
| `name` | string | Y | — | 1-64 chars, alphanumeric + spaces/underscores |
| `description` | string | N | `""` | Max 256 chars |
| `created_at` | string (ISO 8601) | Y | — | Valid datetime |
| `updated_at` | string (ISO 8601) | Y | — | >= created_at |
| `symbols` | string[] | Y | — | Min 1, uppercase tickers |
| `timeframe` | string | Y | — | Enum: `1min\|5min\|15min\|1H\|1D` |
| `indicators` | object[] | Y | `[]` | Each: `{name, params, source}` |
| `entry_rules` | object | Y | AND/empty | Rule tree, max depth 2 |
| `exit_rules` | object | Y | AND/empty | Rule tree, max depth 2 |
| `risk_management` | object | Y | — | See below |

**`risk_management` fields:** `stop_loss_pct` (0-100), `take_profit_pct` (0-100), `max_position_size` (>0), `max_daily_loss` (>0).

**Indicator `name` enum:** SMA, EMA, RSI, MACD, BollingerBands, ATR, Volume, Ichimoku, SuperTrend, VWAP, ZScore, ADX, OBV, Stochastic, ParabolicSAR, SmartMoneyFlowCloud.

**Condition object:** `{indicator, params, operator, value}` where `value` is number OR nested indicator ref `{indicator, params}`.

#### Scenario: Valid JSON passes

- GIVEN file with all required fields, valid indicator, depth-1 rules
- WHEN validated
- THEN return `True`

#### Scenario: Missing name fails

- GIVEN file missing `name`
- WHEN validated
- THEN return `False` with error "Missing required field: name"

#### Scenario: Unknown indicator fails

- GIVEN file with `"indicator": "BadInd"`
- WHEN validated
- THEN return `False` with error "Unknown indicator: BadInd"

### Requirement: Watcher — 30s Polling

Orchestrator SHALL poll `user_strategies/*.json` every 30 iterations of `_run_legacy_loop()` (after `_publish_status()`).

| Event | Action |
|-------|--------|
| New `.json` file | Validate, create DynamicStrategy, replace old |
| Modified file (mtime) | Re-read, re-validate, replace |
| File deleted | Remove strategy, log info |
| Malformed JSON | Log warning, skip |
| Invalid schema | Log warning "Strategy X failed validation", skip |
| Unknown indicator | Log warning, skip |
| Permission/read error | Log warning, retry next cycle |

#### Scenario: Watcher loads new strategy within 60s

- GIVEN Orchestrator running legacy loop
- WHEN valid JSON written to `user_strategies/`
- THEN within 2 cycles (~60s), DynamicStrategy SHALL be loaded and producing signals

#### Scenario: Corrupt JSON gracefully skipped

- GIVEN `user_strategies/bad.json` contains `{invalid`
- WHEN watcher scans
- THEN log warning, skip file, Orchestrator continues with previous strategy

#### Scenario: .tmp file ignored

- GIVEN `user_strategies/strategy.json.tmp` exists (mid-write)
- WHEN watcher scans
- THEN `.tmp` files SHALL be ignored (only `*.json` processed)

### Requirement: .active Symlink

`user_strategies/.active` SHALL be a symlink to the deployed strategy file. Watcher SHALL use this as authoritative source.

#### Scenario: Missing .active = no user strategy

- GIVEN `.active` does not exist
- WHEN watcher polls
- THEN log debug "No .active symlink found"
- AND continue with predefined strategies only

### Requirement: Atomic File Write

Save/Deploy SHALL use `os.replace` via `.tmp` file to prevent partial reads by the watcher.

#### Scenario: Atomic write prevents partial read

- GIVEN Builder saving a file during watcher scan
- WHEN watcher reads during the write
- THEN it SHALL see old or new complete file, never truncated
