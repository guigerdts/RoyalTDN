# Proposal: Optuna-Based Automatic Strategy Optimization

## Intent

Manual parameter tuning across 15 strategies (~65 params) is slow, subjective, and non-reproducible. We need systematic hyperparameter optimization (HPO) to find optimal indicator params, exit thresholds, and risk sizing per strategy against historical data, then surface the best combinations for live deployment.

## Scope

### In Scope
- `scripts/optimize.py` — CLI entry point (argparse) for single-strategy optimization
- Historical data download + parquet caching with 24h TTL expiry
- Optuna search space mapping — each YAML strategy param → `suggest_int`/`suggest_float`
- Bar-by-bar Cell simulation replay (`Cell.handle()` in a tight loop over OHLCV)
- Metrics computation (reuse `scripts/backtest.py`'s `compute_metrics()`)
- YAML auto-update with `.bak` backup on best-trial found
- Result logging to structured JSON (`logs/optimization/`)
- Polling-based hot-reload watcher (`core/hot_reload.py`) for auto-loading optimized YAMLs
- Periodic scheduler integration in `run.py` (optional CLI flag)

### Out of Scope
- Multi-strategy / portfolio-level optimization (one strategy at a time)
- Walk-forward analysis or cross-validation (single train/validation split)
- Live parameter updates while cells are trading (hot-reload triggers fresh load)
- SQL storage for Optuna study history (in-memory only, pruners reset per run)
- GPU or distributed optimization
- `watchdog`-based filesystem events (polling only — zero extra deps)

## Capabilities

### New Capabilities
- `strategy-optimization`: CLI-based hyperparameter search over indicator params, exit config, and risk sizing using Optuna TPESampler + MedianPruner. Reads YAML strategy, downloads OHLCV, runs historical simulation, logs best params.

### Modified Capabilities
- None (no existing spec changes at the behavior level)

## Approach

Build `scripts/optimize.py` as a standalone CLI script (not a framework). Flow per invocation:

1. **Data**: `HistoricalDataLoader` fetches 2y OHLCV for the strategy's symbol+timeframe. Cached as parquet in `data/parquet/` with 24h TTL.
2. **Search space**: Read the strategy YAML, map every numeric param (entry conditions, exit rules, risk sizing) to `suggest_*` calls. Use param name + path as the Optuna distribution name.
3. **Objective function**: Create a fresh `Cell(params, inference_engine)`, feed it bars one-by-one, collect trade signals, simulate P&L via a simplified portfolio tracker, return the objective value (Sharpe ratio, Profit Factor, or Sortino — configurable via CLI).
4. **Pruning**: `MedianPruner` prunes unpromising trials early (e.g., after 25% of bars if net P&L is negative).
5. **Output**: Best params logged to JSON. Optionally write them back to the YAML (with `.bak` backup). Best/worst trial comparison printed via Rich.
6. **Hot reload**: `core/hot_reload.py` — asyncio task that polls `mtime` of YAML files every 30s. On change, re-runs `load_cells()` and hot-swaps the `EventEngine.cells` list.
7. **Scheduler**: `run.py` grows a `--optimize` flag + cron-like interval in config for unattended periodic optimization.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `scripts/optimize.py` | **New** | CLI entry point, objective function, Optuna study loop |
| `data/historical.py` | Modified | Add parquet caching methods (read_cache, write_cache, ttl_check) |
| `core/hot_reload.py` | **New** | Polling file watcher, hot-swap cell registry |
| `run.py` | Modified | `--optimize` flag, scheduler async task |
| `cells/base.py` | Modified | Expose `reset_state()` method for Cell reuse between trials |
| `config.yaml` | Modified | Add optional `optimization` block (interval, metric) |
| `pyproject.toml` | Modified | Add `optuna>=4.0` dependency |
| `logs/optimization/` | **New** | Per-run JSON result files |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| **Overfitting** to 2y of historical data | Med | Always test best params on a hold-out period (last 20% of data as validation set — reported but not optimized on) |
| **Data API rate limits** (Binance REST) | High | Parquet cache with 24h TTL; limit to 1 strategy per run; add `--force-download` flag |
| **Slow backtest** for 1m strategies (~350k bars/yr) | Med | Vectorized indicators run fast; Cell simulation is the bottleneck — use simplified P&L (no broker latency) |
| **Optuna not installed** | — | Add to `pyproject.toml` deps; `pip install` happens before first run |
| **ccxt unavailable** | Low | Fallback to REST (already implemented in `HistoricalDataLoader`) |

## Rollback Plan

- YAML auto-update always creates `.bak` before overwriting — restore by renaming
- Commit the old YAML before running optimization to allow `git checkout` revert
- Hot-reload watcher disabled = no behavior change (cells run with original params)
- Optuna study is in-memory only — no persistent state to clean up

## Dependencies

- `optuna>=4.0` (add to `pyproject.toml`)
- Parquet via `pandas` + `pyarrow` (or `fastparquet`) — `pandas` already installed
- `httpx>=0.28` (already installed, REST fallback)

## Success Criteria

- [ ] `scripts/optimize.py --strategy scalping_momentum --trials 100` produces better Sharpe than default params on validation data
- [ ] Parquet cache hit avoids redundant downloads (2nd run loads from disk)
- [ ] YAML auto-update creates `.bak` and preserves original on modification
- [ ] Hot-reload detects YAML change within 30s and re-registers cells without restart
- [ ] All 15 strategies can be optimized end-to-end without errors
- [ ] `compute_metrics()` reuse produces identical results between `backtest.py` and `optimize.py` for the same trade list
