# Strategy Optimization Specification

## Purpose

Define the system for automatic hyperparameter optimization of trading strategies using Optuna. The system MUST replace manual parameter tuning across 15 strategies (~65 params) with systematic Bayesian optimization (TPE), find optimal indicator parameters, exit thresholds, and risk sizing per strategy against 2 years of Binance historical data, and auto-deploy best params via YAML update + hot reload.

---

## Requirements

---

### R1: CLI Interface

The system SHALL provide a CLI entry point at `scripts/optimize.py` that accepts command-line arguments via `argparse`.

**Acceptance criteria:**
- `python scripts/optimize.py --strategy scalping_momentum --trials 50` runs 50 trials
- `python scripts/optimize.py --strategy all --trials 20` optimizes every strategy sequentially
- `--no-save` flag prevents YAML file modification
- `--symbols BTCUSDT,ETHUSDT` restricts data to specific symbols
- Rich progress bar shows during trial execution
- Rich summary table prints at end with best params and metrics

#### Scenario: Single strategy optimization with progress bar

- GIVEN the strategy `scalping_momentum` exists in `cells/templates/scalping.yaml`
- AND cached OHLCV data for `BTCUSDT_1m` is available in `cache/`
- WHEN the user runs `python scripts/optimize.py --strategy scalping_momentum --trials 20`
- THEN Optuna executes exactly 20 trials for `scalping_momentum`
- AND a Rich progress bar with trial counter is displayed during execution
- AND best parameters are saved to `logs/optimization/optimization_results.json`
- AND the YAML file is updated with best params (unless `--no-save`)

#### Scenario: KeyboardInterrupt during optimization

- GIVEN a `scalping_momentum` optimization is running with 100 trials
- WHEN the user presses Ctrl+C at trial 37
- THEN the study stops gracefully
- AND partial results (37 trials) are saved to JSON
- AND the summary table shows results from completed trials only

#### Scenario: All strategies optimization

- GIVEN the user has 3 YAML strategy files with 15 total strategies
- WHEN running `python scripts/optimize.py --strategy all --trials 10`
- THEN each strategy is optimized for 10 trials sequentially
- AND total trials executed = 150 (15 strategies x 10 trials)
- AND results are written per strategy

---

### R2: Historical Data Download + Cache

The system SHALL download OHLCV klines from Binance (REST API at `api.binance.com`) and cache them as parquet files with a 24-hour TTL.

**Acceptance criteria:**
- 2 years of 1m/15m/1d OHLCV data downloads for each symbol+timeframe
- Parquet cache at `cache/{SYMBOL}_{TIMEFRAME}.parquet`
- Cache hit loads in < 1s; cache miss downloads with pagination
- 24h TTL: data older than 24 hours is re-downloaded
- Binance REST pagination for 1m data (~1M candles) via `startTime` parameter

#### Scenario: Cache hit avoids redundant download

- GIVEN `cache/BTCUSDT_1m.parquet` exists and is < 24h old
- WHEN optimization starts for `scalping_momentum`
- THEN the parquet file is loaded instead of calling Binance API
- AND optimization proceeds with cached data

#### Scenario: Stale cache triggers re-download

- GIVEN `cache/BTCUSDT_1m.parquet` exists but is > 24h old
- WHEN optimization starts for `scalping_momentum`
- THEN the file is discarded
- AND fresh data is downloaded from Binance with pagination
- AND the new data is written to `cache/BTCUSDT_1m.parquet`

#### Scenario: 1m data requires pagination

- GIVEN the user requests 2 years of 1m data for `BTCUSDT`
- WHEN `_download_historical()` executes
- THEN requests are paginated using Binance's `startTime` parameter (max 1000 candles per request)
- AND the complete dataset (~1,051,200 candles) is assembled
- AND API requests are throttled to respect rate limits (1200 req/min)

---

### R3: Search Space Generation

The system SHALL read the strategy YAML, identify all numeric params in entry conditions, exit rules, and risk sizing, and map them to Optuna `suggest_int`/`suggest_float`/`suggest_categorical` distributions with sensible default ranges.

**Acceptance criteria:**
- Every numeric param in entry conditions is included in the search space
- Exit rule params (`atr_multiplier`, `pct`, `threshold`) are included
- Risk sizing is included (`sizing`, `max_positions`)
- Boolean conditions become `suggest_categorical([True, False])`
- Param ranges reflect realistic trading ranges (not arbitrary)

#### Mapped Parameter Ranges

| YAML Parameter Type | Optuna Type | Min | Max | Step |
|---|---|---|---|---|
| `period` | `suggest_int` | 2 | 50 | — |
| `factor` | `suggest_float` | 0.5 | 5.0 | 0.1 |
| `multiplier` | `suggest_float` | 0.5 | 5.0 | 0.1 |
| `pct` | `suggest_float` | 0.1 | 10.0 | 0.1 |
| `atr_multiplier` (exit) | `suggest_float` | 0.5 | 6.0 | 0.1 |
| `threshold` (zscore exit) | `suggest_float` | 0.1 | 2.0 | 0.1 |
| `max_spread_pct` | `suggest_float` | 0.01 | 1.0 | 0.01 |
| `max_pct` (atr) | `suggest_float` | 0.1 | 10.0 | 0.1 |
| `sizing` | `suggest_float` | 0.005 | 0.1 | 0.005 |
| `max_positions` | `suggest_int` | 1 | 5 | — |
| `touch_count` | `suggest_int` | 1 | 5 | — |
| `lookback` | `suggest_int` | 10 | 200 | — |
| `fast` (MACD) | `suggest_int` | 5 | 30 | — |
| `slow` (MACD) | `suggest_int` | 15 | 50 | — |
| `signal` (MACD) | `suggest_int` | 5 | 15 | — |
| RSI operator threshold | `suggest_int` | 10 | 40 | — |
| ADX operator threshold | `suggest_int` | 10 | 40 | — |
| `tenkan` (ichimoku) | `suggest_int` | 5 | 20 | — |
| `kijun` (ichimoku) | `suggest_int` | 10 | 50 | — |
| `senkou_b` (ichimoku) | `suggest_int` | 20 | 70 | — |

#### Scenario: Known params map correctly

- GIVEN `scalping_momentum` entry has `{period: 3}`, `{period: 20, factor: 2.0}`, `{period: 7}`
- WHEN search space is generated
- THEN `period` params map to `suggest_int("entry_conditions_0_params_period", 2, 50)`, `suggest_int("entry_conditions_2_params_period", 2, 50)`, etc.
- AND `factor` maps to `suggest_float("entry_conditions_1_params_factor", 0.5, 5.0, step=0.1)`

#### Scenario: Exit params are included

- GIVEN `scalping_momentum` has exit rules with `atr_multiplier: 1.5` and `atr_multiplier: 3.0`
- WHEN search space is generated
- THEN each `atr_multiplier` maps to `suggest_float("exit_0_params_atr_multiplier", 0.5, 6.0, step=0.1)`

#### Scenario: Risk sizing is included

- GIVEN a strategy has `sizing: 0.01` and `max_positions: 3`
- WHEN search space is generated
- THEN `sizing` maps to `suggest_float("risk_sizing", 0.005, 0.1, step=0.005)`
- AND `max_positions` maps to `suggest_int("risk_max_positions", 1, 5)`

---

### R4: Bar-by-Bar Cell Simulation

The system SHALL create a fresh Cell instance per trial with the suggested params, feed OHLCV bars as pseudo-tick events sequentially, and collect the resulting trades for metrics computation.

**Acceptance criteria:**
- Each trial creates a new `Cell(params, inference_engine)` with suggested params
- Bars are fed one-by-one via `cell.handle({"type": "tick", "symbol": ..., "price": ..., "data": ...})`
- Cell state transitions (IDLE → IN_POSITION → IDLE) accumulate naturally
- All trades (BUY and SELL events) are collected per trial
- Each trial starts with a fresh Cell (no state leakage between trials)

#### Scenario: Bars are fed sequentially

- GIVEN a Cell for `scalping_momentum` with 1000 OHLCV bars
- WHEN the simulation feeds each bar to `cell.handle()`
- THEN bars are appended to `cell.bars` in chronological order
- AND `cell._build_data()` returns at least 20 bars before evaluating entry
- AND signals are generated when entry conditions are met

#### Scenario: Fresh state per trial

- GIVEN Trial 1 completed with 3 trades and cell state = IDLE
- WHEN Trial 2 creates a new `Cell(params, inference_engine)`
- THEN `cell.bars` is empty (not carried over from Trial 1)
- AND `cell.state` is `"IDLE"`
- AND no trades from Trial 1 influence Trial 2

#### Scenario: Trailing stop state is per-instance

- GIVEN a cell with trailing stop exit rule
- WHEN the simulation feeds bars with a price run-up and pullback
- THEN `cell._trailing_high` tracks the running maximum within a single position
- AND a fresh cell in the next trial has `_trailing_high = None`

---

### R5: Metrics Computation

The system SHALL compute trading metrics from collected trades using the same `compute_metrics()` function from `scripts/backtest.py`, and return a single objective value for Optuna.

**Acceptance criteria:**
- Sharpe ratio (annualized) is the primary optimization metric
- If zero trades in a trial, objective returns -999
- Trial trades are passed directly to `compute_metrics(trades)`
- Objective = Sharpe ratio (maximized) or -999 if no trades

#### Scenario: Positive Sharpe from profitable trial

- GIVEN a trial produced 15 trades with 10 wins and 5 losses
- WHEN `compute_metrics()` is called
- THEN `metrics["sharpe_ratio"][0]` is a positive float
- AND objective function returns the Sharpe value

#### Scenario: Zero trades trial returns -999

- GIVEN a trial with suggested params that produce zero signals
- WHEN the objective function evaluates
- THEN `n_trades == 0`
- AND the objective returns `-999.0`

---

### R6: Optuna Study Execution

The system SHALL create an Optuna study per strategy using `TPESampler(seed=42)` with `direction="maximize"` on Sharpe ratio, and show a Rich progress bar during execution.

**Acceptance criteria:**
- `TPESampler(seed=42)` for reproducibility
- `direction="maximize"` (objective = Sharpe ratio)
- In-memory `InMemoryStorage` (no SQL dependency)
- Rich progress bar updates per trial
- KeyboardInterrupt handled gracefully
- Study results include trial number, params, and objective value per trial

#### Scenario: Study runs requested trials

- GIVEN strategy `scalping_momentum` with `--trials 50`
- WHEN Optuna study executes
- THEN 50 trials are completed
- AND each trial evaluates a unique param combination
- AND best_trial returns the highest Sharpe trial

#### Scenario: Reproducibility with fixed seed

- GIVEN TPE sampler with `seed=42`
- WHEN the same strategy is optimized twice with same trial count
- THEN both runs produce the same sequence of suggested params

#### Scenario: Graceful interrupt saves partial progress

- GIVEN a study running 100 trials and interrupted at trial 42
- WHEN KeyboardInterrupt is caught
- THEN completed 42 trials are saved to `logs/optimization/optimization_results.json`
- AND the summary table shows best params from those 42 trials

---

### R7: YAML Auto-Update

When `--no-save` is NOT set, the system SHALL write the best discovered parameters back to the strategy's YAML file, creating a `.bak` backup of the original.

**Acceptance criteria:**
- Original YAML is backed up as `{strategy_file}.bak`
- Best params are written back using `yaml.dump(default_flow_style=False)`
- Only the optimized strategy's params are updated (others in the same multi-doc file are preserved)
- YAML structure (indentation, comments) is maintained

#### Scenario: Backup before overwrite

- GIVEN `cells/templates/scalping.yaml` exists with original params
- WHEN optimization completes with better params found
- THEN `cells/templates/scalping.yaml.bak` is created with original content
- AND `cells/templates/scalping.yaml` now contains the best params

#### Scenario: No-save flag prevents YAML modification

- GIVEN optimization completes with `--no-save` flag
- WHEN results are logged to JSON
- THEN `cells/templates/scalping.yaml` is NOT modified
- AND no `.bak` file is created

---

### R8: Result Logging

The system SHALL save optimization results to structured JSON at `logs/optimization/optimization_results.json` and display a Rich summary table at the end of optimization.

**Acceptance criteria:**
- JSON file contains timestamp, strategy, best params, and metrics per run
- Results are appended (not overwritten) — each run adds a JSON entry
- Rich summary table shows best params, best Sharpe, profit factor, win rate, max drawdown, and trials completed

#### Scenario: Results saved to JSON

- GIVEN optimization of `scalping_momentum` completed with best Sharpe = 1.85
- WHEN results are saved
- THEN `logs/optimization/optimization_results.json` contains an entry with `strategy: "scalping_momentum"`, `best_sharpe: 1.85`, and all best params
- AND the Rich table shows these values with color-coding (green/red)

---

### R9: Hot Reload Watcher

The system SHALL implement a polling hot-reload watcher in `core/hot_reload.py` that monitors YAML file modification times and reloads cells when changes are detected, without restarting the bot.

**Acceptance criteria:**
- Polling interval: 60 seconds (configurable)
- Detects mtime changes on YAML strategy files
- On change: re-runs `load_cells()` and atomically swaps `EventEngine.cells`
- Thread-safe: cells list swap is a single assignment
- Does NOT require `watchdog` or any extra dependency

#### Scenario: Hot reload detects YAML change

- GIVEN the bot is running with `scalping_momentum` params
- WHEN `cells/templates/scalping.yaml` is modified (mtime changes)
- THEN within 60s, the watcher detects the change
- AND `load_cells()` creates new Cell instances with updated params
- AND `EventEngine.cells` is atomically swapped
- AND the new params are used for subsequent trades

#### Scenario: No change, no reload

- GIVEN the bot is running
- WHEN no YAML files have been modified
- THEN the watcher polls mtime and finds no changes
- AND no reload is triggered

#### Scenario: Thread-safe cells swap

- GIVEN a YAML change is detected
- WHEN the watcher builds a new cells list
- THEN the new list is assigned in a single operation: `engine.cells = new_cells`
- AND the engine's `_process_event` loop sees either the old list or the new list, never a partially modified one

---

### R10: Periodic Scheduler

The system SHALL add a configurable periodic scheduler to `run.py` that triggers optimization at a configurable interval (15-30 days) without blocking the main trading loop.

**Acceptance criteria:**
- Configurable via `config.yaml` `optimization.interval_days` (default: 30)
- Optimization runs in a separate asyncio task (non-blocking)
- CLI flag `--optimize` enables periodic scheduling
- Results are logged and hot-reloaded automatically

#### Scenario: Periodic optimization triggers on schedule

- GIVEN `config.yaml` has `optimization.interval_days: 30`
- AND the bot is started with `--optimize`
- WHEN 30 days have elapsed since the last optimization
- THEN a new optimization task is spawned
- AND trading continues uninterrupted during optimization

#### Scenario: No scheduler without --optimize flag

- GIVEN the bot is started without `--optimize`
- WHEN time passes
- THEN no optimization task is scheduled
- AND the bot runs with existing params indefinitely

---

## Appendix A: JSON Schema — `logs/optimization/optimization_results.json`

The file SHALL contain a JSON array at the top level. Each entry represents one optimization run.

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "required": [
      "timestamp", "strategy", "symbol", "timeframe",
      "trials_completed", "best_params", "best_metrics"
    ],
    "properties": {
      "timestamp": {
        "type": "string",
        "format": "date-time",
        "description": "ISO-8601 UTC timestamp of the optimization run"
      },
      "strategy": {
        "type": "string",
        "description": "Strategy name as it appears in YAML (e.g. scalping_momentum)"
      },
      "symbol": {
        "type": "string",
        "description": "Trading symbol (e.g. BTCUSDT)"
      },
      "timeframe": {
        "type": "string",
        "description": "Kline interval (e.g. 1m, 15m, 1d)"
      },
      "trials_completed": {
        "type": "integer",
        "minimum": 0
      },
      "best_trial_number": {
        "type": "integer",
        "description": "The trial index (0-based) that produced the best objective"
      },
      "best_params": {
        "type": "object",
        "additionalProperties": {
          "type": ["number", "boolean", "string", "null"]
        },
        "description": "Flat dict of param_name → value for the best trial"
      },
      "best_metrics": {
        "type": "object",
        "required": ["sharpe_ratio", "profit_factor", "win_rate", "max_drawdown", "total_pnl", "n_trades"],
        "properties": {
          "sharpe_ratio": {"type": "number"},
          "profit_factor": {"type": "number"},
          "win_rate": {"type": "number", "description": "Percentage 0-100"},
          "max_drawdown": {"type": "number", "description": "Percentage 0-100"},
          "total_pnl": {"type": "number"},
          "n_trades": {"type": "integer"}
        }
      },
      "worst_metrics": {
        "type": "object",
        "description": "Metrics from the worst trial (same schema as best_metrics)",
        "properties": {
          "sharpe_ratio": {"type": "number"},
          "profit_factor": {"type": "number"},
          "win_rate": {"type": "number"},
          "max_drawdown": {"type": "number"},
          "total_pnl": {"type": "number"},
          "n_trades": {"type": "integer"}
        }
      },
      "duration_seconds": {
        "type": "number",
        "description": "Wall-clock time for the optimization run"
      },
      "validation_sharpe": {
        "type": "number",
        "description": "Sharpe ratio on the hold-out validation set (last 20% of data) — **Future: not yet implemented.** The `--validate` flag is parsed but is a no-op."
      }
    }
  }
}
```

### Parquet Cache File Naming

```
cache/{SYMBOL}_{TIMEFRAME}.parquet
```

- `{SYMBOL}`: uppercase without separator (e.g. `BTCUSDT`, `ETHUSDT`)
- `{TIMEFRAME}`: kline interval (e.g. `1m`, `15m`, `1d`)
- Examples: `cache/BTCUSDT_1m.parquet`, `cache/ETHUSDT_1d.parquet`

---

## Appendix B: CLI Specification Table

| Flag | Type | Default | Description |
|---|---|---|---|
| `--strategy` | `str` | `None` | Strategy name from YAML (e.g. `scalping_momentum`). Omit or use `"all"` to optimize every strategy sequentially |
| `--trials` | `int` | `100` | Number of Optuna trials per strategy |
| `--no-save` | `bool` (flag) | `False` | Skip YAML file update and `.bak` creation |
| `--symbols` | `str` | `None` | Comma-separated list of symbols (e.g. `BTCUSDT,ETHUSDT`). If omitted, uses the strategy's configured symbol |
| `--force-download` | `bool` (flag) | `False` | Ignore cache and re-download historical data |
| `--metric` | `str` | `sharpe` | Optimization objective: `sharpe`, `profit_factor`, `sortino` |
| `--validate` | `bool` (flag) | `False` | **No-op (deferred — future).** Parsed but not yet implemented. A warning is printed when used. |

---

## Appendix C: Constraints

### Binance API Rate Limits

- REST endpoint limit: 1200 requests per minute per IP
- Each klines request = 1 weight (up to 1000 candles)
- For 1m data (~1M candles over 2 years): ~1052 requests needed per symbol
- **Mitigation**: Add `time.sleep(0.05)` between requests (20 req/s), cache after download
- For 1d data: only 2 requests needed (730 days ÷ 1000 limit = 1 request + overflow)

### Data Volume

| Timeframe | Candles/year | 2-year candles | REST requests |
|---|---|---|---|
| 1m | ~525,600 | ~1,051,200 | ~1052 |
| 15m | ~35,040 | ~70,080 | ~71 |
| 1d | ~365 | ~730 | ~1 |

### Cell Simulation Constraints

- Cell requires minimum 20 bars before evaluating entry conditions (`cell._build_data()` returns `{}` if `len(self.bars) < 20`)
- First 20 bars of each trial are warm-up (no signals possible)
- Bar history is capped at 500 bars (`cell.max_bars = 500`)
- Trailing stop state (`_trailing_high`) is per-instance — fresh Cell per trial is mandatory
- ATR calculation requires `period + 1` bars minimum (default period = 14, so minimum 15 bars)

### Optuna Constraints

- In-memory storage only (`optuna.storages.InMemoryStorage`)
- No multi-objective optimization (single objective: Sharpe ratio)
- `TPESampler(seed=42)` for reproducibility
- `MedianPruner(n_startup_trials=5, n_warmup_steps=10, interval_steps=5)` for early pruning

### Dependencies

- `optuna>=4.0` MUST be installed (add to `pyproject.toml`)
- `pandas` + `pyarrow` for parquet (pandas already installed)
- `httpx>=0.28` for REST fallback (already installed)
- No `ccxt`, no `watchdog`, no `plotly` required

---

## Deferred Items (Future)

The following items are specified but deferred to a future change:

| Item | Status | Notes |
|------|--------|-------|
| `--validate` flag | Parsed, no-op | Prints a warning when used; hold-out validation set logic not implemented |
| `validation_sharpe` in JSON output | Schema field defined, not written | Requires `--validate` implementation |
| Dedicated test suite | Not implemented | All 25 spec scenarios lack covering tests. Implementation verified by source evidence only. |
