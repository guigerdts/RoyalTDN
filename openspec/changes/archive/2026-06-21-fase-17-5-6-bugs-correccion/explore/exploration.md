# Exploration: FASE 17.5 — Corrección de 6 bugs detectados en pruebas con Binance Testnet

## Current State

The bot has been tested with Binance Testnet (crypto universe) and 6 bugs were
discovered spanning the scanner UI, liquidity filter configuration, backtest
defaults, strategy validation, data source routing, and menu header updates.

## Affected Areas

### Bug 1 — Scanner muestra datos mock cuando top_signals está vacío
- `src/royaltdn/frontend/menu/app.py` — `_show_scanner()` (lines 1280-1468)
- `src/royaltdn/frontend/console/components/state.py` — default scanner result structure

**Root Cause**: `_show_scanner()` at line 1404 renders `_render_signals_table(top_signals)` via
`elif top_signals:` — a truthy check on the list. If `top_signals` contains entries with
`strategy == "mock"` (from test infrastructure or fallback data), these are rendered as
real signals with no filtering. There is no guard that filters out mock entries or
validates signal source before display.

**Approach**:
1. Filter `top_signals` to exclude entries where `strategy == "mock"` or `source == "mock"`
2. After filtering, if the resulting list is empty, show a contextual message instead
   of the signal table (re-use the existing `passed_sym > 0 and sig_count == 0` branch)
3. Add the filter in both rendering paths: initial display (line 1404) and force-scan
   reload (line 1461)

**Effort**: Low — ~10 lines, localized to `_show_scanner()`.

---

### Bug 2 — Filtro de liquidez rechaza todos los pares crypto (0/10)
- `src/royaltdn/main.py` — LiquidityFilter construction (lines 269-282)
- `src/royaltdn/scanner/filters.py` — LiquidityFilter.filter() crypto path (lines 144-164)

**Root Cause**: The conditional crypto defaults ARE present in `main.py` (the
`_crypto_mode` check sets min_volume=1000, min_price=1.0, max_spread_pct=999), BUT
the LiquidityFilter's crypto data path via `brokers.get("crypto")` may fail or return
empty DataFrames when the Binance Testnet connection has no data. When the DataFrame
is empty, `df["volume"].mean()` raises KeyError or returns NaN, which fails the
`avg_volume >= self.min_volume` check. A second issue: if the Alpaca
`crypto_data_client` is also unavailable (Binance-only setup), the `else` branch at
line 162 logs "no crypto broker/client — skipping" and continues, effectively
rejecting ALL crypto symbols.

**Approach**:
1. Verify that `_crypto_mode` param defaults are actually reaching LiquidityFilter
   (no env var override set to stricter values)
2. Add better error handling in the crypto broker path of `filter()` — when the
   broker throws or returns empty, try the data_client fallback
3. Add logging at `main.py` level showing what params the LiquidityFilter was
   initialized with

**Effort**: Medium — requires tracing through the broker chain and adding fallback
paths.

---

### Bug 3 — Backtest rápido: default debe ser BTC/USD en universo crypto
- `src/royaltdn/frontend/menu/app.py` — `_quick_backtest()` (lines 1664-1673)

**Root Cause**: At line 1673, `default_symbol = "SPY"` is hardcoded when no symbol
can be inferred from the config. There is zero awareness of `SCANNER_UNIVERSE`.
When the universe is "crypto", the backtest prompt should default to "BTC/USD"
(or another crypto pair) instead of "SPY".

**Approach**:
1. Before the default assignment, check `os.getenv("SCANNER_UNIVERSE", "all")`
2. If universe is "crypto", fall back to `"BTC/USD"` instead of `"SPY"`
3. Keep the existing inference from config["symbol"]/config["symbols"] as priority

**Effort**: Low — ~5 lines, single function.

---

### Bug 4 — Backtest con estrategia predefinida falla: "version must be 1 (int)"
- `src/royaltdn/orchestrator.py` — `_build_strategies_list()` (lines 474-501)
- `src/royaltdn/strategy/schema.py` — `validate_config()` (line 58)
- `src/royaltdn/frontend/menu/app.py` — `_quick_backtest()` (line 1693)

**Root Cause**: Predefined strategies in `_build_strategies_list()` are written to
`strategies.json` WITHOUT a `"version"` field. When the user selects a predefined
strategy and runs a quick backtest, `_quick_backtest()` passes the config dict
directly to `validate_config(config)`, which at schema.py line 58 checks
`config.get("version") != 1` and returns `"version must be 1 (int)"`.

**Approach** (two options):
- **Option A** (preferred): In `_quick_backtest()`, add `config.setdefault("version", 1)`
  before calling `validate_config()`. This is defensive — protects against any caller
  that passes a config without version.
- **Option B**: Add `"version": 1` to the predefined strategy dicts in
  `_build_strategies_list()`. More targeted but less defensive.

**Effort**: Low — 1 line with Option A.

---

### Bug 5 — Backtest con crypto usa Yahoo Finance en lugar de Binance
- `src/royaltdn/strategy/backtesting.py` — `_download_data()` (lines 43-72) and
  `run_backtest()` (line 210)

**Root Cause**: `run_backtest()` unconditionally calls `_download_data()` which uses
`yfinance`. For crypto symbols containing `/` (e.g., `"BTC/USD"`), yfinance either
fails or returns incorrect data. The code should route crypto symbols to
`BinanceBroker.get_bars()` which is already implemented and working.

**Approach**:
1. In `run_backtest()`, check if `"/" in symbol`
2. If yes, import and use `BinanceBroker.get_bars()` to download OHLCV data instead
   of `_download_data()`
3. Normalize the returned DataFrame to match the expected column format (lowercase
   `open/high/low/close/volume`)
4. The BinanceBroker is already instantiated in `main.py` and passed to the
   orchestrator, but `run_backtest()` is called from the menu (different context)
   — so it needs to either accept a broker parameter or create a BinanceBroker on
   the fly using env vars

**Effort**: Medium — requires wiring broker into the backtest call chain or adding
env-var-based instantiation.

---

### Bug 6 — Header del menú no se actualiza al reanudar el bot
- `src/royaltdn/frontend/menu/app.py` — `_print_header()` (lines 96-112) and
  `_is_bot_paused()` (lines 182-197)

**Root Cause**: Two issues:

1. **Hardcoded path**: `_is_bot_paused()` defaults to `logs_dir="logs"` but
   `_print_header(console)` does NOT accept or pass `logs_dir`. The main menu's
   `logs_dir` parameter (from `run_menu()`) is not threaded through. If the menu
   runs with a non-default logs directory, `_is_bot_paused()` reads the wrong file.

2. **Async timing gap**: When the user resumes via `_show_control`, `resume_bot()`
   writes `pause_signal.json`. The orchestrator reads this in `_check_signals()`
   during its next loop iteration, sets `self.paused = False`, and calls
   `_publish_status()` to write the updated `status.json`. But there's a delay
   (poll_interval seconds) before the orchestrator processes the signal. During
   this gap, the header still shows "PAUSADO".

**Approach**:
1. Fix `_print_header` to accept and forward `logs_dir` parameter
2. In `_show_control`, after calling `resume_bot()`, instead of just waiting for
   Enter and returning, directly check if `pause_signal.json` exists and wait
   briefly for the orchestrator to process it (or add a mechanism to force the
   orchestrator's next iteration)
3. Alternative: in `_show_control`, immediately rewrite `status.json` in addition
   to writing the signal file, so the menu reflects the change instantly

**Effort**: Medium — involves cross-process coordination or a pragmatic workaround.

## Recommendation

All 6 bugs are well-defined, localized, and relatively low-risk. The recommended
priority order is:

1. **BUG 4** (1 line fix) — highest impact because it blocks ALL predefined strategy
   backtests
2. **BUG 3** (5 line fix) — wrong default but low impact since user can type the
   symbol manually
3. **BUG 1** (10 line fix) — cosmetic but confusing when data is stale/mock
4. **BUG 6** (multi-line, medium effort) — UX issue with status feedback
5. **BUG 5** (medium effort) — functional issue for crypto backtests
6. **BUG 2** (medium effort, hardest to diagnose) — depends on exact testnet
   failure mode

All fixes can be applied independently with no shared dependencies.

## Risks

- **BUG 2 risk**: The LiquidityFilter crypto path involves external API calls to
  Binance Testnet. If the testnet is unstable, fixing the code may not fully resolve
  the issue. Need to add robust logging first to confirm the exact failure point.
- **BUG 5 risk**: Instantiating a BinanceBroker inside `run_backtest()` requires env
  vars (BINANCE_API_KEY, BINANCE_SECRET_KEY). If these are not configured, the
  backtest should fail gracefully with a clear error message.
- **BUG 6 risk**: The async timing issue is inherent to the IPC architecture.
  Solving it "perfectly" would require IPC changes. The pragmatic workaround
  (immediate status.json rewrite) is simpler and matches user expectations.

## Ready for Proposal

**Yes**. All 6 bugs have clear root causes and well-understood fix approaches.
The orchestration can proceed to the Proposal phase.
