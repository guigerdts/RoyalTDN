# Design: Optuna-Based Strategy Optimization

## Technical Approach

Single-file `scripts/optimize.py` with internal section functions. Each trial: fresh Cell + Portfolio + RiskManager, feed OHLCV bars as pseudo-tick events, collect trades, return metrics via `compute_metrics()`. Results optionally written to YAML with `.bak`. Hot-reload polls mtime every 60s, atomic `engine.cells = new_list` swap.

## Architecture Decisions

| Option | Tradeoffs | Decision |
|--------|-----------|----------|
| Single script vs package | Package cleaner for ~800 LoE; single-file matches backtest.py (466 LOC) | **Single file** `scripts/optimize.py` |
| Full EventEngine vs simplified sim | Full engine adds broker round-trips, bus, journal — 10x overhead | **Simplified**: Cell + Portfolio + RiskManager |
| ccxt vs REST fallback | ccxt adds dep; REST already works in HistoricalDataLoader | **REST fallback** only |
| Watchdog vs polling | watchdog cleaner but extra dep | **Polling 60s** via `asyncio.sleep` |
| Subprocess vs in-thread scheduler | Subprocess isolates crashes | **In-process** via `asyncio.to_thread()` |
| ruamel.yaml vs yaml.dump | ruamel preserves comments | **yaml.dump** + `.bak` |

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `scripts/optimize.py` | **Create** | CLI entry, search space mapper, simulator, objective fn, study loop, YAML updater, result logger |
| `core/hot_reload.py` | **Create** | `HotReloader` — polls YAML mtime, rebuilds cells, atomic `engine.cells = new_list` swap |
| `cells/base.py` | **Modify** | Add `reset_state()` — clear bars, state=IDLE, entry_price=0 |
| `data/historical.py` | **Modify** | Add parquet cache read/write + paginated download for 2y range |
| `run.py` | **Modify** | `--optimize` flag + periodic scheduler async task |
| `config.yaml` | **Modify** | Add `optimization:` block (interval_days, metric) |
| `pyproject.toml` | **Modify** | Add `optuna>=4.0`, `pyarrow>=14.0` |

## Core Simulation Algorithm

```python
async def simulate(config, ohlcv, capital):
    cell = Cell(config, inference_engine=InferenceEngine())
    portfolio = Portfolio(initial_capital=capital)
    risk = RiskManager(portfolio)
    trades = []
    for _, bar in ohlcv.iterrows():
        signal = await cell.handle(dict(type="tick", symbol=config["symbol"],
            price=float(bar["close"]),
            data=dict(open=bar["open"], high=bar["high"],
                      low=bar["low"], close=bar["close"], volume=bar["volume"])))
        if signal is None: continue
        if signal["action"] == "BUY":
            approved = risk.approve(signal)
            if approved: portfolio.update(approved)
        elif signal["action"] == "SELL":
            pnl = (signal["price"] - signal.get("entry_price",0)) * portfolio.positions.get(config["symbol"],0)
            portfolio.update(signal)
            trades.append(dict(pnl=pnl, capital=portfolio.capital))
    return trades  # → compute_metrics() → Sharpe (or -999 if 0 trades)
```

**Internal routing**: `main()` → `parse_args()` → for each strategy: `get_data()` → `optuna.create_study(TPESampler(seed=42), direction="maximize")` → `study.optimize(objective, n_trials, callbacks=[rich_progress])` → update YAML (unless `--no-save`) → `save_results()` → Rich summary.

## Parameter Mapping

Walk YAML tree recursively. Key format: `entry.{idx}.{param_name}`, `exit.{idx}.{type}.{name}`, `risk.{name}`. Operator thresholds extracted from strings like `"< 40"` via regex → `entry.{idx}.{indicator}.operator_threshold`. Range lookup by param name:

| Param Pattern | Optuna | Range | Step |
|---|---|---|---|
| `period` | `suggest_int` | 2–50 | — |
| `factor`, `atr_multiplier` | `suggest_float` | 0.5–6.0 | 0.1 |
| `pct`, `max_pct` | `suggest_float` | 0.1–10.0 | 0.1 |
| `max_spread_pct` | `suggest_float` | 0.01–1.0 | 0.01 |
| `sizing` | `suggest_float` | 0.005–0.1 | 0.005 |
| `threshold` (exit) | `suggest_float` | 0.1–2.0 | 0.1 |
| `lookback` | `suggest_int` | 20–200 | — |
| `touch_count`, `max_positions` | `suggest_int` | 1–5 | — |
| `fast`, `slow`, `signal`, `tenkan`, `kijun`, `senkou_b` | `suggest_int` | var | — |
| `*_threshold` (operator) | `suggest_int` | 10–40 | — |

## Data Caching

`cache/{SYMBOL}_{TF}.parquet` with `.meta.json` sidecar for `download_timestamp`. TTL: mtime < 24h → load; else re-download with `startTime` pagination (1000/req, 50ms throttle). 1m data: ~1051 reqs, ~52s.

## Error Handling

| Failure | Handling |
|---|---|
| Binance API timeout/429 | Retry 3x (1s, 2s, 4s backoff) |
| 0 trades in trial | Objective returns `-999.0` |
| KeyboardInterrupt | Catch in study loop, save partial, show summary |
| Corrupted parquet | Delete + re-download |
| YAML write failure | Log error, keep `.bak` |
| Hot-reload while IN_POSITION | Old cell completes in old list; new list has fresh cell |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | `suggest_params()` mapping | Mock trial, verify correct `suggest_*` calls |
| Unit | `simulate()` | 500 synthetic OHLCV bars, assert trade collection |
| Unit | Metrics parity | Same `compute_metrics()` as backtest.py |
| Unit | YAML update + .bak | Temp dir, verify backup + content |
| Integration | 10-trial Optuna study | Real study, verify JSON + Rich table |
| Integration | Hot-reload | Touch YAML, assert engine.cells replaced |

## Open Questions

- [ ] Validation hold-out: post-optimization step via `--validate`? Assumption: yes.
- [ ] `--symbols` filter: filter strategies by symbol? Assumption: yes.
- [ ] `--strategy all` progress bar: per-strategy nested? Assumption: yes.
