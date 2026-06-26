# Tasks: FASE 18.4 — Scanner verbose + intervalo dinámico + validación dinero real

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,760 total (avg ~350/PR) |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes — 5 PRs |
| Chain strategy | feature-branch-chain → `fase-18-4-scanner-verbose` |
| Delivery strategy | auto-chain (force-chained per session preflight) |

**Budget risk per PR**: PR-1 ~380, PR-2 ~350, PR-3a ~350, PR-3b ~300, PR-4 ~380 — each under 400.

---

## 1. Implementation Sequence (5 Chained PRs)

### PR-1: explain() concrete base + 5 existing strategies + scanner verbose base

- **Target branch**: `fase-18-4-scanner-verbose` (tracker)
- **Dependencies**: None (base of chain)
- **Est. lines**: ~380
- **Verification**: `explain()` returns default empty dict on bare strategy; `generate_signal()` output preserved after `_compute_indicators()` refactor for sma_crossover, bollinger_rsi, momentum_atr, swing_trend_following, swing_breakout; `scan(verbose=True)` populates `_last_explanations`; verbose log written.

### PR-2: 5 scalping strategies explain()

- **Target branch**: PR-1
- **Dependencies**: PR-1 (has `explain()` concrete default + `_compute_indicators()` pattern)
- **Est. lines**: ~350
- **Verification**: Each scalping strategy's `explain()` returns correct conditions; `generate_signal()` matches `explain()` signal; `gap_pct` calc correct; exactly-at-threshold edge case.

### PR-3a: 5 intraday strategies explain()

- **Target branch**: PR-2
- **Dependencies**: PR-2
- **Est. lines**: ~350
- **Verification**: All 5 intraday strategies pass parametrized explain() contract test; `_compute_indicators()` + `generate_signal()` consistency per strategy.

### PR-3b: 3 swing strategies + all-17 iteration test

- **Target branch**: PR-3a
- **Dependencies**: PR-3a
- **Est. lines**: ~300
- **Verification**: All 3 swing strategies pass explain() contract; all-17 iteration test passes with no exceptions; `file_change_map.md` updated.

### PR-4: UI verbose + dynamic interval + scalping disable + check-readiness + tests

- **Target branch**: PR-3b
- **Dependencies**: PR-3b (all 17 strategies have explain())
- **Est. lines**: ~380
- **Verification**: Scanner L1/L2 UI renders with closeness bars; 's' triggers scan in verbose mode; Logs "verbose" filter works; interval auto-adjusts; env var override respected; KPI shows interval; scalping auto-disabled on non-crypto universe change; notification shown; Estrategias submenu warning on manual scalping toggle; `check-readiness` renders Rich Panel with 6 checks + verdict; exit codes 0/1/2 correct.

---

## 2. Per-Strategy Backfill Matrix

| # | Strategy Name | File | Category | PR | Has `generate_signal()`? | Needs `_compute_indicators()` extraction? | Needs `explain()`? | Special Considerations | Current Test File |
|---|---------------|------|----------|----|--------------------------|-------------------------------------------|--------------------|----------------------|-------------------|
| 1 | sma_crossover | `sma_strategy.py` | existing | PR-1 | Y | Y — crossover EMA logic, medium complexity | Y | Uses ATR-based filter in generate_signal; needs profile resolution via symbol | `tests/test_strategy.py` |
| 2 | bollinger_rsi | `bollinger_rsi.py` | existing | PR-1 | Y | Y — RSI + BB calc, medium complexity | Y | Dual indicator gates (RSI + Bollinger); symbol not used | `tests/test_strategy.py` |
| 3 | momentum_atr | `momentum_atr.py` | existing | PR-1 | Y | Y — momentum return + ATR%, medium complexity | Y | **Complex**: uses `symbol` for profile resolution (crypto/stocks), has `_PROFILES` dict; 2 signal gates (BUY momentum+volatility, SELL short momentum) | `tests/test_strategy.py` |
| 4 | swing_trend_following | `swing_trend_following.py` | existing | PR-1 | Y | Y — trend indicators, low-medium complexity | Y | Multiple EMA trend filters; may use symbol for profile | — |
| 5 | swing_breakout | `swing_breakout.py` | existing | PR-1 | Y | Y — breakout levels, medium complexity | Y | Range-based breakout detection; needs high/low data | — |
| 6 | factor_rotation | `factor_rotation.py` | existing | PR-3b | Y | Y — factor score calc, **high complexity** | Y | **Complex**: multi-ETF ranking, scores not binary thresholds; `explain()` should show per-factor scores | — |
| 7 | scalping_momentum | `scalping_momentum.py` | scalping | PR-2 | Y | Y — pct_change calc, low complexity | Y | Simple momentum threshold; no symbol dependency | — |
| 8 | scalping_breakout | `scalping_breakout.py` | scalping | PR-2 | Y | Y — high/low break levels, low complexity | Y | Breakout levels from recent range; no symbol dependency | — |
| 9 | scalping_reversion | `scalping_reversion.py` | scalping | PR-2 | Y | Y — RSI/stochastic, medium complexity | Y | Mean reversion indicators; no symbol dependency | — |
| 10 | scalping_orderflow | `scalping_orderflow.py` | scalping | PR-2 | Y | Y — order flow imbalance, medium complexity | Y | Uses bid/ask spread data; may need symbol for data availability | — |
| 11 | scalping_spread | `scalping_spread.py` | scalping | PR-2 | Y | Y — spread metrics, low complexity | Y | Spread-based entry/exit; no symbol dependency | — |
| 12 | intraday_trend | `intraday_trend.py` | intraday | PR-3a | Y | Y — EMA fast/slow + ATR%, medium complexity | Y | Uses `symbol` for profile resolution (like momentum_atr); dual gate | — |
| 13 | intraday_vwap | `intraday_vwap.py` | intraday | PR-3a | Y | Y — VWAP + std bands, medium complexity | Y | VWAP calculation from intraday data; uses `symbol` | — |
| 14 | intraday_volume_breakout | `intraday_volume_breakout.py` | intraday | PR-3a | Y | Y — volume spike metrics, low complexity | Y | Volume spike detection; no symbol dependency | — |
| 15 | intraday_support_resistance | `intraday_support_resistance.py` | intraday | PR-3a | Y | Y — S/R level detection, medium complexity | Y | Swing point detection for S/R; needs high/low data | — |
| 16 | intraday_macd_divergence | `intraday_macd_divergence.py` | intraday | PR-3a | Y | Y — MACD line/signal/histogram, medium complexity | Y | MACD crossover + divergence detection; no symbol dependency | — |
| 17 | swing_reversion | `swing_reversion.py` | swing | PR-3b | Y | Y — overbought/oversold, low complexity | Y | Mean reversion at swing level; no symbol dependency | — |

---

## 3. Detailed Task Breakdown per PR

### PR-1: explain() concrete base + 5 existing + scanner verbose base

| ID | Description | File(s) | What to Do | Risks/Edge Cases | Verification | Status |
|----|-------------|---------|------------|------------------|--------------|--------|
| [x] PR1-T1 | Add `explain()` as CONCRETE method to BaseStrategy with default empty return | `src/royaltdn/strategy/base.py` | Add `def explain(self, data: pd.DataFrame, symbol: Optional[str] = None) -> Dict[str, Any]` returning `{"indicators": {}, "conditions": [], "signal": None}`. Add docstring with full return contract. NOT `@abstractmethod` | If mistakenly made abstract, all strategies break until they implement; scanner guard `hasattr()` needed | Test: mock strategy without override returns empty dict; docstring has 3 keys | ✅ |
| [x] PR1-T2 | Define `_compute_indicators()` pattern + `_calc_gap()` in base.py | `src/royaltdn/strategy/base.py` | Add `_calc_gap(value, threshold, direction)` as module-level helper. Document the `_compute_indicators(data, symbol=None)` uniform signature contract in BaseStrategy docstring | Gap calc division by zero if threshold=0; must use `abs()` | Test: value=100, threshold=110, above → 9.09%; value=110, threshold=100, below → 10% | ✅ |
| [x] PR1-T3 | Refactor sma_crossover: extract `_compute_indicators()`, implement `explain()` | `src/royaltdn/strategy/sma_strategy.py` | Extract indicator calc (SMA fast/slow, current values) into `_compute_indicators()`. Refactor `generate_signal()` to call it. Implement `explain()`: build conditions for crossover, return signal dict | Must preserve existing `generate_signal()` output exactly; ATR filter in crossover must be captured | `generate_signal()` same output on golden cross + no-trigger data | ✅ |
| [x] PR1-T4 | Refactor bollinger_rsi: extract `_compute_indicators()`, implement `explain()` | `src/royaltdn/strategy/bollinger_rsi.py` | Extract RSI + BB bands + close into `_compute_indicators()`. Refactor `generate_signal()`. Implement `explain()` with dual-gate conditions | Dual condition gates (RSI oversold + BB touch); explain must show both | Same `generate_signal()` output; explain conditions reflect both gates | ✅ |
| [x] PR1-T5 | Refactor momentum_atr: extract `_compute_indicators()`, implement `explain()` | `src/royaltdn/strategy/momentum_atr.py` | Extract momentum return + ATR% + close into `_compute_indicators(data, symbol=None)`. Pass `symbol` for profile resolution. Refactor `generate_signal()`. Implement `explain()` with BUY/SELL gate conditions | **Highest risk**: uses `symbol` for profile resolution; 2 separate signal gates (BUY and SELL) with different conditions; `generate_signal()` has complex profile resolution that `explain()` must mirror exactly | Same `generate_signal()` output for crypto + stocks profile; explain conditions match each gate independently | ✅ |
| [x] PR1-T6 | Refactor swing_trend_following: extract `_compute_indicators()`, implement `explain()` | `src/royaltdn/strategy/swing_trend_following.py` | Extract trend indicators into `_compute_indicators()`. Refactor `generate_signal()`. Implement `explain()` | Multiple EMA periods; trend direction gates | Same output; explain shows trend strength indicators | ✅ |
| [x] PR1-T7 | Refactor swing_breakout: extract `_compute_indicators()`, implement `explain()` | `src/royaltdn/strategy/swing_breakout.py` | Extract breakout levels into `_compute_indicators()`. Refactor `generate_signal()`. Implement `explain()` | Breakout levels depend on lookback period; must match between methods | Same output; explain shows break level vs current price | ✅ |
| [x] PR1-T8 | Add `scan(verbose=False)` param + `_last_explanations` dict + verbose log writer | `src/royaltdn/scanner/scanner.py` | Add `verbose: bool = False` to `scan()`. New `self._last_explanations: Dict[str, Dict[str, dict]]`. When verbose=True: after `generate_signal()` per (strategy, symbol), call `strategy.explain(data)` if `hasattr(strategy, 'explain')`. New `_write_verbose_log()` appends ISO-8601 lines to `logs/scanner_verbose.log` | **Guard**: `hasattr(strategy, 'explain')` before calling; strategies without explain() skip silently; log file append-only, no rotation | `scan(verbose=True)` stores 2 strategies × 2 symbols = 4 entries; `scan(verbose=False)` doesn't populate; log file has timestamps | ✅ |
| [x] PR1-T9 | Create PR-1 test file | `tests/test_fase18_4_pr1.py` | Test default explain() returns empty template; test refactored generate_signal() output preserved for sma_crossover; test scan(verbose=True) stores explanations; test scan(verbose=False) does not; test hasattr guard | Mock data must be realistic; avoid depending on real Alpaca data | All tests pass; no regressions on existing test suite | ✅ |

### PR-2: 5 scalping strategies explain()

| ID | Description | File(s) | What to Do | Risks/Edge Cases | Verification |
|----|-------------|---------|------------|------------------|--------------|
| PR2-T1 | Refactor scalping_momentum + explain() | `src/royaltdn/strategy/scalping_momentum.py` | Extract pct_change + close into `_compute_indicators()`. Refactor `generate_signal()`. Implement `explain()`: condition `pct_change > min_momentum_pct` (BUY) or `< -min_momentum_pct` (SELL) | Exactly-at-threshold → met=True, gap=0.0 | Same output; explain conditions match signal |
| PR2-T2 | Refactor scalping_breakout + explain() | `src/royaltdn/strategy/scalping_breakout.py` | Extract high/low break levels into `_compute_indicators()`. Refactor + explain() | Lookback window consistency | Same output; explain shows break distance |
| PR2-T3 | Refactor scalping_reversion + explain() | `src/royaltdn/strategy/scalping_reversion.py` | Extract RSI/stochastic into `_compute_indicators()`. Refactor + explain() | Dual overbought/oversold zones | Same output; explain shows zone + distance |
| PR2-T4 | Refactor scalping_orderflow + explain() | `src/royaltdn/strategy/scalping_orderflow.py` | Extract order flow imbalance metrics into `_compute_indicators()`. Refactor + explain() | Bid/ask data availability; explain shows imbalance ratio | Same output; explain shows imbalance vs threshold |
| PR2-T5 | Refactor scalping_spread + explain() | `src/royaltdn/strategy/scalping_spread.py` | Extract spread metrics into `_compute_indicators()`. Refactor + explain() | Spread widening vs tightening logic | Same output; explain shows spread vs threshold |
| PR2-T6 | Create PR-2 test file | `tests/test_fase18_4_pr2.py` | Parametrized test: each scalping strategy's `explain()` conditions match `generate_signal()` signal. Test `gap_pct` calc. Test exactly-at-threshold → met=True, gap=0.0 | Must cover BUY, SELL, and NO SIGNAL scenarios per strategy | All parametrized tests pass |

### PR-3a: 5 intraday strategies explain()

| ID | Description | File(s) | What to Do | Risks/Edge Cases | Verification |
|----|-------------|---------|------------|------------------|--------------|
| PR3a-T1 | Refactor intraday_trend + explain() | `src/royaltdn/strategy/intraday_trend.py` | Extract EMA fast/slow + ATR% — uses `symbol` for profile. Refactor + explain() | Profile resolution via symbol; similar to momentum_atr pattern | Same output; explain shows EMA crossover + ATR gate |
| PR3a-T2 | Refactor intraday_vwap + explain() | `src/royaltdn/strategy/intraday_vwap.py` | Extract VWAP, std, bands — uses `symbol` for profile. Refactor + explain() | VWAP formula; symbol for profile | Same output; explain shows VWAP distance |
| PR3a-T3 | Refactor intraday_volume_breakout + explain() | `src/royaltdn/strategy/intraday_volume_breakout.py` | Extract volume spike metrics. Refactor + explain() | Volume baseline period consistency | Same output; explain shows volume ratio |
| PR3a-T4 | Refactor intraday_support_resistance + explain() | `src/royaltdn/strategy/intraday_support_resistance.py` | Extract S/R levels from swing points. Refactor + explain() | Swing detection sensitivity; multiple S/R levels | Same output; explain shows nearest S/R distance |
| PR3a-T5 | Refactor intraday_macd_divergence + explain() | `src/royaltdn/strategy/intraday_macd_divergence.py` | Extract MACD line, signal, histogram. Refactor + explain() | Divergence detection logic (price vs MACD); explain must show both | Same output; explain shows MACD cross + divergence |
| PR3a-T6 | Create PR-3a test file | `tests/test_fase18_4_pr3a.py` | Parametrized test across all 5 intraday strategies for explain() contract compliance. Test `_compute_indicators()` + `generate_signal()` consistency | Each strategy needs both-trigger and no-trigger data | All parametrized tests pass |

### PR-3b: 3 swing strategies + all-17 iteration test

| ID | Description | File(s) | What to Do | Risks/Edge Cases | Verification |
|----|-------------|---------|------------|------------------|--------------|
| PR3b-T1 | Refactor swing_reversion + explain() | `src/royaltdn/strategy/swing_reversion.py` | Extract overbought/oversold metrics. Refactor + explain() | Multiple indicator thresholds for reversion | Same output; explain shows oversold/overbought distance |
| PR3b-T2 | Refactor factor_rotation + explain() | `src/royaltdn/strategy/factor_rotation.py` | Extract factor scores into `_compute_indicators()`. Refactor `generate_signal()`. Implement `explain()` showing per-factor scores and ranking | **Highest complexity**: factor_rotation doesn't produce BUY/SELL — produces RANK with score. `explain()` should list each factor's score and the total composite score | Same ranking output; explain shows per-factor breakdown |
| PR3b-T3 | Verify all 17 strategies are registered in __init__ if applicable | `src/royaltdn/strategy/__init__.py` | Check if `__init__.py` exports or registers strategies; add missing ones if needed | May be empty or already complete; verify only | All 17 strategy modules importable |
| PR3b-T4 | Create PR-3b test file + all-17 iteration test | `tests/test_fase18_4_pr3b.py` | Parametrized test across 3 swing strategies. **All-17 iteration test**: iterate all registered strategies, call `explain()` on each with test data, assert no exceptions and valid return structure (indicators, conditions, signal keys present) | Test data must satisfy minimum bar requirements for all strategies; factor_rotation may need multi-symbol data | All 17 strategies pass without exception; valid return structure |
| PR3b-T5 | Update file_change_map.md with actual PR data | `openspec/changes/fase-18-4-scanner-verbose/design/file_change_map.md` | Update line counts after PR-1, PR-2, PR-3a completion; verify PR chain diagram | — | File reflects actual state |

### PR-4: UI verbose + dynamic interval + scalping disable + check-readiness + tests

| ID | Description | File(s) | What to Do | Risks/Edge Cases | Verification |
|----|-------------|---------|------------|------------------|--------------|
| PR4-T1 | Add `_disable_scalping_in_strategies_json()` helper | `src/royaltdn/frontend/menu/app.py` | New helper: read `logs/strategies.json`, iterate strategies, set `active=False` for `category="scalping"` when universe != "crypto". Atomic write via `.tmp` + `os.replace()`. Log warning via `logger.warning()` | File may not exist or be malformed → graceful skip; race condition with orchestrator writing same file → unlikely due to atomic write | Mock strategies.json → scalping disabled; unchanged on crypto universe |
| PR4-T2 | Hook scalping auto-disable into `_cycle_universe()` | `src/royaltdn/frontend/menu/app.py` | After rotating universe and setting, call `_disable_scalping_in_strategies_json()` if `new_uni != "crypto"`. Crypto: no auto-reactivate | Must NOT auto-reactivate when returning to crypto; user manually toggles | Universe change to sp500 → scalping disabled; change to crypto → unchanged |
| PR4-T3 | Add scalping notification in main menu | `src/royaltdn/frontend/menu/app.py` | In `_print_menu()` or `_check_notifications()`, if universe != "crypto" and any scalping strategy exists in `strategies.json`, show `"Scalping desactivado: no compatible con el mercado actual."` in bold red | Check must read from strategies.json, not scanner state | Notification shown on non-crypto; hidden on crypto |
| PR4-T4 | Add Estrategias submenu warning for manual scalping toggle | `src/royaltdn/frontend/menu/app.py` | Before toggling strategy to active, check if `category="scalping"` AND `universe != "crypto"` → show confirmation: `"Scalping no recomendado en {universe}. ¿Activar de todas formas? (s/n):"` | Must not show warning on crypto universe; persists after warning 's' | Warning on non-crypto; immediate toggle on crypto; cancelled toggle restores inactive |
| PR4-T5 | Replace module-level SCANNER_INTERVAL_MINUTES with `_get_scan_interval_override()` | `src/royaltdn/orchestrator.py` | Delete line 77. Add `_get_scan_interval_override()` module function: reads env var dynamically, returns `int` or `None`. Validate positive integer; log warning on invalid | Env var read each cycle — no stale value; backward compatible | Env var set → returns int; unset → None; invalid → logs warning + returns None |
| PR4-T6 | Add `_calc_scan_interval()` to Orchestrator | `src/royaltdn/orchestrator.py` | New method: call `_get_scan_interval_override()` first; if None, build categories from `_build_strategies_list()` active strategies. Mapping: scalping→2, intraday→15, swing→240, none→60. Use minimum across active categories | Empty strategies list → 60; multiple categories → minimum wins | scalping+intraday → 2; swing only → 240; no active → 60; env var override respected |
| PR4-T7 | Update `_run_legacy_loop()` for dynamic interval + publish to status.json | `src/royaltdn/orchestrator.py` | Replace fixed `scanner_iterations` with `_recalc_scanner_iterations(poll_interval)` per cycle. Store `self._current_scan_interval`. Publish `scanner_interval_minutes` in `_publish_status()` with source info `{"interval": X, "source": "env"|"auto"}` | Per-cycle recalculation keeps interval in sync with strategy changes | status.json has scanner_interval_minutes; interval changes when strategies change |
| PR4-T8 | Add scanner verbose L1/L2 UI in `_show_scanner()` | `src/royaltdn/frontend/menu/app.py` | Detect verbose mode. New `_render_verbose_dashboard()`: per-symbol Panels with Rich Table (strategy name, indicator value, closeness bar `█` x/10, color indicator). Navigation: `↑`/`↓` cursor between symbols, `E` → L2 decision tree, `0` → back. `_render_decision_tree()`: per-strategy condition tables with ✅/❌, gap%, signal line | 16-color ANSI only — no hex colors; closeness bar = 10 segments max; L2 exit must return to L1 | L1 shows per-symbol panels with bars; L2 shows condition tables; ↑/↓/E/0 navigation works |
| PR4-T9 | Wire 's' key for manual scan in verbose mode | `src/royaltdn/frontend/menu/app.py` | In `_show_scanner()`, after initial render, accept 's' key → call `trigger_scanner()` then re-render with updated explanations. In verbose mode, `scan(verbose=True)` called | Must not block UI; re-render must preserve cursor position | 's' triggers scan; verbose mode populates explanations; screen re-renders |
| PR4-T10 | Add "verbose" filter option in `_show_logs()` | `src/royaltdn/frontend/menu/app.py` | Add filter option "6" for "Verbose" → read `logs/scanner_verbose.log` lines instead of main log buffer | File may not exist yet → show empty; handle gracefully | Filter option appears; verbose log lines displayed |
| PR4-T11 | Add dynamic interval display in Scanner + KPI | `src/royaltdn/frontend/menu/app.py` | `_show_scanner()`: read `status.json["scanner_interval_minutes"]`, display "Intervalo: X min". `_build_kpis()`: add Scan interval KPI line showing "Scan: cada Xmin" or "Scan: cada Xmin (env)" when override active | JSON may be stale; show latest value; "(env)" suffix logic | Scanner shows interval; KPI shows interval + "(env)" when applicable |
| PR4-T12 | Add `--verbose` CLI flag parsing | `src/royaltdn/main.py` | Parse `--verbose` from `sys.argv[2:]` in `cmd_run()`. Set `scanner.verbose = True`. Pass to scanner | Must not break existing `--seed-trades` flag | `--verbose` flag activates verbose mode; without flag, normal mode |
| PR4-T13 | Implement `cmd_check_readiness()` | `src/royaltdn/main.py` | 7 checks: (1) trades≥50 from `logs/trades.json`, (2) Sharpe>0.5 from `logs/equity.json`, (3) avg slippage<0.5% from trades.json, (4) kill switch tested from bot.log grep, (5) Telegram OK from bot.log last 24h, (6) broker connectivity (Alpaca + Binance ping). Rich Panel with ✅/❌ per check. Verdict: READY / CASI LISTO / NO RECOMENDADO. Exit code 0/1/2 | File read errors → gracefully report check as failed; broker ping exceptions → caught and reported; exit codes per spec | All 6 checks rendered; panel correctly colored; verdict matches scenario |
| PR4-T14 | Register CLI commands | `src/royaltdn/main.py` | Add `"check-readiness": cmd_check_readiness` to commands dict. Ensure `--verbose` flag works with `run` command | Must not break existing commands | `python -m royaltdn check-readiness` runs and exits |
| PR4-T15 | Create PR-4 test file | `tests/test_fase18_4_pr4.py` | Test `_get_scan_interval_override()` (env set/unset/invalid). Test `_calc_scan_interval()` (category mixes). Test scalping disable in app.py (mock strategies.json, cycle to non-crypto). Test notification rendering logic. Test Estrategias submenu warning. Test check-readiness 3 verdict variants and exit codes | Mock all file I/O and broker pings; no real API calls | All tests pass; verdict test covers all 3 paths |

---

## 4. Review Workload Forecast

| Metric | Value |
|--------|-------|
| **Total estimated changed lines** | ~1,760 (additions + deletions across all 5 PRs) |
| **Per-PR estimate** | PR-1: ~380, PR-2: ~350, PR-3a: ~350, PR-3b: ~300, PR-4: ~380 |
| **Risk of exceeding 400-line budget** | **Medium** — all PRs are under 400 as planned, but PR-4 (the largest at ~380) is tight. If scalping disable notification logic or L2 decision tree generation inflates, PR-4 could exceed 400 |
| **Recommended decision** | Approve as-is — each PR stays under 400. Monitor PR-4 during apply; if L1/L2 UI logic exceeds 380, split UI rendering (`_render_verbose_dashboard` + `_render_decision_tree`) into a separate helper file to reduce app.py line count |
| **Split further if needed** | PR-4 is the only risk: split UIRenderer into `src/royaltdn/frontend/menu/verbose_renderer.py` (~80 lines of rendering helpers) if app.py changes exceed 400 |
