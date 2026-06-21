# Tasks: FASE 17.5 — Corrección de 6 bugs detectados en pruebas con Binance Testnet

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~85 |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR #1 (Bugs 1,3,4) → PR #2 (Bug 6) → PR #3 (Bugs 2,5) |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Base Branch |
|------|------|-----------|-------------|
| 1 | Mock filter + crypto default + version setdefault | PR #1 | feature/tracker |
| 2 | Header sync status.json on resume | PR #2 | PR #1 branch |
| 3 | NaN guard + crypto broker routing | PR #3 | PR #2 branch |

## Phase 1: PR #1 — Mock filter, crypto default, version setdefault (Bugs 1, 3, 4)

- [x] 1.1 `app.py` `_show_scanner()`: filter out entries where `strategy == "mock"` from `top_signals` before table render; use filtered list for empty check
- [x] 1.2 `app.py` `_quick_backtest()`: set `default_symbol = "BTC/USDT"` when `os.getenv("SCANNER_UNIVERSE") == "crypto"`, else `"SPY"`
- [x] 1.3 `app.py` `_quick_backtest()`: add `config.setdefault("version", 1)` one line before `validate_config(config)`
- [x] 1.4 Test: scanner with all mock entries shows empty state; mixed entries show only real signals
- [x] 1.5 Test: crypto universe defaults to BTC/USDT; stocks universe defaults to SPY
- [x] 1.6 Test: config missing version passes validation; explicit version != 1 still raises error

## Phase 2: PR #2 — Header timing fix (Bug 6)

- [x] 2.1 `app.py` `_print_header()`: add `logs_dir: str = "logs"` parameter; pass to `_is_bot_paused()`
- [x] 2.2 `app.py` `_show_control()`: after `resume_bot(logs_dir)` returns, write `{logs_dir}/status.json` with `bot_status: ONLINE, paused: false, timestamp` using `_atomic_write`
- [x] 2.3 `app.py`: thread `logs_dir` through all `_print_header()` and `_is_bot_paused()` call sites
- [x] 2.4 Test: resume writes status.json synchronously; header reflects ONLINE on next render
- [x] 2.5 Test: `logs_dir` threaded correctly — status.json written to correct path

## Phase 3: PR #3 — NaN guard + crypto broker routing (Bugs 2, 5)

- [ ] 3.1 `filters.py` `LiquidityFilter.filter()`: guard `df.empty or df["volume"].isna().all()` before `df["volume"].mean()`; log debug and `continue` on skip
- [ ] 3.2 `backtesting.py` `_download_data()`: add `broker: Optional[BaseBroker] = None` param; when `"/" in symbol and broker`, call `broker.get_bars()` and normalize columns to lowercase OHLCV
- [ ] 3.3 `backtesting.py` `run_backtest()`: accept optional `broker` param; forward to `_download_data()`
- [ ] 3.4 `app.py` `_quick_backtest()` / `_builder_flow()`: wire BinanceBroker from env when symbol contains `/`; pass to `run_backtest()`
- [ ] 3.5 Test: LiquidityFilter skips empty/NaN DataFrame without crash; logs debug message
- [ ] 3.6 Test: `/` symbol routes to `broker.get_bars()`; stock symbol uses yfinance
- [ ] 3.7 Test: no broker configured with `/` symbol raises clear error
