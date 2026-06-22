## Exploration: FASE 18.4 — Scanner Verbose + Intervalo Dinámico + Validación Dinero Real

### Current State

#### A. Scanner Verbose — `explain()` per strategy

**BaseStrategy** (`strategy/base.py`) defines 3 methods:
- `generate_signal(data, symbol?)` → `Optional[Dict]` (abstract)
- `get_parameters(symbol?)` → `Dict` (concrete, returns timeframe + category by default)
- `validate()` → `bool` (concrete, returns True by default)

**No `explain()` method exists.** The interface is signal-or-nothing.

Each concrete strategy computes indicators inside `generate_signal()` and stuffs a `metadata` dict into the return value. Content varies per strategy:

| Strategy | Metadata fields |
|----------|-----------------|
| ScalpingMomentum | pct_change, momentum_period, min_momentum_pct |
| IntradayTrend | ema_fast, ema_slow, atr_pct, trend_period |
| SwingTrendFollowing | ema_fast, ema_slow, atr_pct, trend_strength |
| FactorRotation | momentum(%), volatility(%), score |

**The gap**: when a strategy returns `None` (no signal), there is ZERO diagnostic info. User sees "0 signals" with no clue whether:
- Data was insufficient (< required periods)
- Individual conditions failed (and by how much)
- Thresholds are too tight

**Scanner.scan()** (`scanner/scanner.py`):
- Gets symbols from `AssetUniverse.get_symbols()`
- Filters through `LiquidityFilter.filter()`
- Batch-downloads 60 daily bars per symbol
- Iterates strategies per symbol, calls `generate_signal()`
- Collects non-None returns into `signals[]`
- Ranks via `_rank_signals()` (FactorRotation score desc → BUY before SELL)
- Writes `scanner_results.json` to `logs/`
- **No verbose/diagnostic mode exists today** — the `scan()` method has no `verbose` parameter

**Scanner UI** (`frontend/menu/app.py` — `_show_scanner()`):
- Reads `scanner_results.json` from file
- Shows: total symbols, passed filter count, signals count, elapsed time, timestamp
- If passed==0 and signals==0 → "no symbols passed filter"
- If passed>0 and signals==0 → "symbols passed but no signals"
- No per-strategy or per-condition drill-down at all
- Supports 's' to force a new scan via IPC signal file

#### B. Dynamic Scan Interval

**Current fixed interval:** `SCANNER_INTERVAL_MINUTES` env var, default 60.
- Set at module level in `orchestrator.py` line 77
- Used in `_run_legacy_loop()` line 1338:
  ```python
  scanner_iterations = int((SCANNER_INTERVAL_MINUTES * 60) / poll_interval)
  ```
- Every `scanner_iterations` poll cycles, auto-scan fires
- **No adaptation to strategy categories** — 60 min regardless of scalping/intraday/swing mix

**Strategy categories** (all predefined strategies set these in `__init__`):
- `scalping` (5 strategies) — timeframes: 1min-5min
- `intraday` (5 strategies) — timeframes: 15min-1H
- `swing` (7 strategies including legacy) — timeframes: 1d

The strategy dict lives on `Scanner.strategies`. The orchestrator accesses it via `self._scanner.strategies`.

#### C. Disable Scalping Outside Crypto

**Current behavior:** strategies are loaded unconditionally from `STRATEGIES_ENABLED` env var. No per-category filtering.

**Universe change flow:**
1. Menu 'U' key → `_cycle_universe()` → rotates `("all", "etfs", "crypto", "sp500")`
2. Calls `_universe_setter(_current_universe)` → wired in `main.py` as `lambda ut: setattr(scanner.universe, 'universe_type', ut)`
3. `AssetUniverse.universe_type` setter validates, sets `_universe_type`, invalidates cache
4. Next scan picks up new universe

**Crypto detection:** `is_crypto_symbol()` checks `"/" in symbol` or membership in `_CRYPTO_SYMBOLS` frozenset (built from `DEFAULT_CRYPTO` and `DEFAULT_CRYPTO_BINANCE`).

**Scalping strategies** (all have `category="scalping"`):
- `scalping_momentum`, `scalping_breakout`, `scalping_reversion`, `scalping_orderflow`, `scalping_spread`

#### D. check-readiness CLI

**Current CLI** (`main.py`):
```
check      — Alpaca Paper connection test
run        — Start bot + interactive console
status     — Show current bot status (one-shot Rich dashboard)
logs       — Show last 50 bot.log lines
pause      — Send pause IPC signal
resume     — Send resume IPC signal
scanner    — Trigger scanner IPC signal
```

CLI dispatcher in `main()` — simple `dict[str, callable]`.

**Available runtime data** (all in `logs/` dir):
- `status.json` — bot_status, paused, mode, uptime, last_signal, last_error
- `equity.json` — initial_equity, current_equity, pnl_day, drawdown, sharpe, equity_curve
- `trades.json` — total_trades, win_rate, profit_factor, total_pnl, trades[]
- `positions.json` — open_positions[]
- `signals.json` — today_count, last_signals[]

**Missing:** Broker connectivity check, kill switch status, slippage metrics, Telegram connectivity — none of these are exposed via CLI.

---

### Affected Areas

| File | Why affected |
|------|-------------|
| `src/royaltdn/strategy/base.py` | Add `explain()` abstract method to `BaseStrategy` |
| `src/royaltdn/strategy/*.py` (15 files) | Implement `explain()` in each concrete strategy |
| `src/royaltdn/scanner/scanner.py` | Add `verbose` param to `scan()`, wire `explain()` calls, write verbose logs |
| `src/royaltdn/orchestrator.py` | Dynamic interval logic, pass verbose mode to scanner |
| `src/royaltdn/main.py` | Add `check-readiness` command |
| `src/royaltdn/frontend/menu/app.py` | New `_show_scanner_verbose()` screen, integrate explain() into scanner display |
| `src/royaltdn/frontend/console/commands.py` | Add `check_readiness()` IPC-like function |
| `src/royaltdn/scanner/universe.py` | Expose `universe_type` for scalping disable check |
| `tests/test_fase18_3_doce_estrategias.py` | Add `explain()` parametrized tests |
| `tests/test_scanner.py` | Add verbose scan tests |
| New: `tests/test_check_readiness.py` | Test readiness command |

---

### Approaches

#### A. Scanner Verbose

**1. Optional `explain()` on BaseStrategy + scanner `verbose` flag**

- Add `explain(data, symbol?) → Dict` to `BaseStrategy` with default returning param info
- Each strategy returns: indicator values, thresholds, gaps to thresholds (how far from triggering), proximity bars, which conditions passed/failed
- `Scanner.scan(verbose=False)` — when True, calls `explain()` on each strategy-symbol pair and accumulates diagnostics
- Two UI levels: compact dashboard (per-symbol, per-strategy with closeness bars) and decision tree (per-condition values, thresholds, gaps)
- Write `scanner_verbose.json` alongside `scanner_results.json`

*Pros*: Clean separation of concerns, backward-compatible (verbose=False by default); testable independently per strategy  
*Cons*: ~15 strategy files need `explain()` implementations; tight coupling between `generate_signal()` and `explain()` indicator computation  
*Effort*: **High** (~15 strategies × 1h each = 15h + 5h scanner wiring + 5h UI)

**2. Centralized debug collector in Scanner**

- Scanner wraps each `generate_signal()` call, captures internal state via inspection
- No changes to BaseStrategy
- Uses `try/except` to catch None returns and attempts to re-run with debug

*Pros*: No per-strategy changes needed  
*Cons*: Can't access internal indicator values without changing strategy code anyway; fragile; high runtime overhead  
*Effort*: Medium (but produces lower-quality diagnostics)

**Recommendation: Approach A.1** — the template viability (see below) shows every strategy has clear indicator values to expose.

#### B. Dynamic Scan Interval

**1. Category-based interval derived from active strategies**

- Scan `self._scanner.strategies` for min category: scalping→2min, intraday→15min, swing→240min
- If any active strategy is scalping → use 2min; if intraday → 15min; else swing → 240min
- Override `SCANNER_INTERVAL_MINUTES` dynamically inside orchestrator before each scan cycle
- Read strategies from scanner instance (already available)

*Pros*: Simple logic, no config changes, responds to strategy toggles  
*Cons*: Requires the orchestrator to read strategy categories from scanner (already does this in `_build_strategies_list()`)  
*Effort*: **Low** (2-3h)

**2. Per-strategy interval override from strategy profile**

- Each strategy declares a `scan_interval_minutes` in `_PROFILES`
- Scanner picks the minimum among active strategies

*Pros*: More granular, strategies self-describe their interval needs  
*Cons*: More invasive, requires changes to every `_PROFILES` dict  
*Effort*: Low-Medium

**Recommendation: Approach B.1** — leverages existing categories, minimal change surface.

#### C. Disable Scalping Outside Crypto

**1. Filter by category in Scanner when universe is non-crypto**

- In `Scanner.__init__` or before scan iteration: if universe is NOT crypto, skip strategies with `category == "scalping"`
- Log a warning listing skipped strategies
- Optionally persist the disabled state to `strategies.json`

*Pros*: Self-contained in scanner, no config changes needed, obvious behavior  
*Cons*: If user toggles universe mid-session while scalping has positions, could orphan them  
*Effort*: **Low** (2-3h)

**2. Per-strategy `is_compatible(universe_type)` method on BaseStrategy**

- BaseStrategy gets `is_compatible(universe) → bool`, default True
- Scalping strategies override to return False for `non-crypto` universes

*Pros*: Clean OCP, strategies own their compatibility  
*Cons*: More files changed, more verbose  
*Effort*: Low

**Recommendation: Approach C.1** — simpler, fewer files touched. The scanner already has access to both `self.universe` and `self.strategies`.

#### D. check-readiness CLI

**1. Single `cmd_check_readiness()` in main.py**

- Read all logs/ JSON files for current state
- Combine with broker connectivity check (existing `cmd_check` code)
- Expose: trades count, win rate, Sharpe (from equity.json or calculated), slippage (from trades), kill switch status, Telegram (try `send_telegram_message`), broker connection (Alpaca + Binance)
- Output: Rich Panel with PASS/FAIL per check, overall recommendation

*Pros*: Reuses existing `StateLoader` and broker clients, single file change  
*Cons*: Sync I/O for broker checks (acceptable for CLI)  
*Effort*: **Low** (3-4h)

**Recommendation: Approach D.1** — maps cleanly to existing CLI pattern.

---

### Risks

- **Strategy `explain()` duplication**: indicator logic is duplicated between `generate_signal()` and `explain()`. Mitigation: extract shared computation into private methods or a `compute_indicators()` that both call.
- **Backward compat**: `verbose` param on `scan()` defaults to False — no behavior change for existing callers.
- **Dynamic interval oscillation**: if user toggles strategies, interval jumps between 2min and 240min. The check should happen at scan-cycle granularity, not mid-scan.
- **Scalping disable + crypto universe toggle**: if user toggles universe to crypto and back, scalping strategies will be re-enabled. Need to ensure positions are handled gracefully (though user would re-scan).
- **Test coverage**: 15 strategy `explain()` implementations need parametrized tests. Pattern already exists in `test_fase18_3_doce_estrategias.py`. Can reuse the `STRATEGIES` catalog.
- **No emoji/24-bit color rules**: verbose UI must follow the project convention of 16-color ANSI only, no emoji.

---

### Template viability: `explain()` per strategy type

Every strategy today computes specific indicators and applies thresholds. Converting to `explain()` is mechanical:

**ScalpingMomentumStrategy** `explain()` output:
```
Indicator: pct_change = +0.32% (threshold: > 1.0% for BUY, < -1.0% for SELL)
  Gap to BUY: -0.68 pp — not triggered
  Gap to SELL: +1.32 pp — not triggered
Result: NO SIGNAL (momentum insufficient)
```

**IntradayTrendStrategy** `explain()` output:
```
Indicator: EMA_fast = 452.10, EMA_slow = 448.30 (gap: +3.80)
Indicator: ATR% = 1.2% (threshold: > 20.0%)
  Condition 1: EMA_fast > EMA_slow → PASS
  Condition 2: ATR% > 20.0% → FAIL (gap: -18.8pp)
Result: NO SIGNAL (ATR trend strength insufficient)
```

**SwingTrendFollowingStrategy** `explain()` output:
```
Indicator: EMA_fast = 450.20, EMA_slow = 445.10 (gap: +5.10)
Indicator: ATR% = 1.5% (threshold: > 0.20%)
  Condition 1: EMA_fast > EMA_slow → PASS
  Condition 2: ATR% > 0.20% → PASS
Result: BUY SIGNAL
```

All strategies follow this pattern: **compute indicators → check conditions → report gaps**. The `explain()` method simply returns the internal state that `generate_signal()` already computes but discards on None.

**Verdict**: Template is **viable** for ALL 15+ strategies. Every strategy has clear indicator values and numeric thresholds.

---

### Ready for Proposal

**Yes.** The codebase is well-structured for this change:

1. `BaseStrategy` is clean and minimal — adding `explain()` as a default no-op won't break anything
2. Every strategy already computes the values `explain()` would return — they're just not exposed
3. The scanner's `scan()` is the single orchestration point — one `verbose` param propagates everywhere
4. The CLI `cmd_*` pattern is trivial to extend
5. Testing patterns (parametrized strategy catalog) already exist and can be reused
6. The interval logic needs only category inspection of `self._scanner.strategies`
7. The scalping disable is a 5-line filter in the scanner loop

**Total estimated effort: Low-Medium** (the bulk is 15 strategy `explain()` implementations, each mechanical).
