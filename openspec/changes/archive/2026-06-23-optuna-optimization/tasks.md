# Tasks: Optuna-Based Strategy Optimization

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 600–750 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Base branch |
|------|------|-----------|-------------|
| 1 | Foundation + Core Engine | PR 1 | feature/optuna-optimization |
| 2 | Output & Persistence | PR 2 | PR 1 branch |
| 3 | Integration + Wiring | PR 3 | PR 2 branch |

## Phase A: Foundation

- [x] 1.1 Add optuna>=4.0, pyarrow>=14.0 to pyproject.toml; install; verify
- [x] 1.2 Add Cell.reset_state() to cells/base.py — clear bars, state=IDLE, entry_price=0, _trailing_high=0
- [x] 1.3 Implement parquet cache in data/historical.py — download_2y_ohlcv() with Binance pagination, save/load parquet, 24h TTL check, corrupted-file → re-download
- [x] 1.4 Create cache/ and logs/optimization/ directories

## Phase B: Core Engine (scripts/optimize.py)

- [x] 2.1 CLI arg parser — --strategy (required/"all"), --trials (100), --no-save, --symbols, --force-download, --metric (sharpe/profit_factor/sortino), --validate
- [x] 2.2 Parameter mapping — walk YAML entry.conditions, exit.rules, risk; emit suggest_int/suggest_float/suggest_categorical per param name; ranges from spec table §R3
- [x] 2.3 Historical simulation — fresh Cell per trial, feed OHLCV bars via cell.handle(), collect BUY/SELL signals, simulate P&L via Portfolio.update(), return trade list
- [x] 2.4 Metrics integration — call backtest.py compute_metrics(trades); extract scalar objective (sharpe/sortino/profit_factor); 0-trade → -999.0; wrap async cell.handle() in asyncio.run()
- [x] 2.5 Optuna study loop — TPESampler(seed=42), InMemoryStorage, MedianPruner(n_startup=5, n_warmup=10), direction="maximize", Rich progress bar, KeyboardInterrupt → partial save + summary

## Phase C: Output & Persistence

- [x] 3.1 Multi-doc YAML update — yaml.safe_load, find strategy dict by name in list, mutate params, yaml.dump + .bak backup; skip if --no-save
- [x] 3.2 JSON results logging — append-mode to logs/optimization_results.json (full schema: timestamp, strategy, symbol, timeframe, trials, best_params, best_metrics, worst_metrics, duration_seconds); Rich summary table with color-coded best/worst

## Phase D: Integration

- [x] 4.1 HotReloader in core/hot_reload.py — asyncio polling loop (60s), detect mtime change, rebuild cells via load_cells(), atomic engine.cells = new_cells swap; zero extra deps
- [x] 4.2 Add optimization: { interval_days: 30, metric: sharpe } block to config.yaml
- [x] 4.3 Add --optimize flag to run.py; spawn periodic scheduler asyncio task; non-blocking via asyncio.create_task
- [x] 4.4 End-to-end verification — 10-trial optimize → YAML updated → hot reload picks new params
