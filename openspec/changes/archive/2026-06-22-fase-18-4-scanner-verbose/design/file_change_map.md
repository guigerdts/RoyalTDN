# File Change Map: FASE 18.4 — Scanner verbose + intervalo dinámico + validación dinero real

## PR Chain Strategy

Feature-branch-chain targeting `fase-18-4-scanner-verbose` as the integration branch.
Each PR targets the previous PR's branch. Review budget: 400 lines per PR.

```
main ─┬→ PR-1 (explain concrete base + 5 existing + scanner scan verbose)
      │      └→ PR-2 (explain scalping 5)
      │             └→ PR-3a (explain intraday 5)
      │                    └→ PR-3b (explain swing 3 + all-17 test)
      │                           └→ PR-4 (UI + interval + scalping disable + readiness)
      └─→ fase-18-4-scanner-verbose (target merged)
```

---

## PR 1 — explain() concrete base + 5 existing strategies + scanner scan(verbose) base

**Est. lines**: ~380 | **Target branch**: `fase-18-4-scanner-verbose`

### src/royaltdn/strategy/base.py — Modify

- **Change**: Add `explain()` as CONCRETE method (NOT `@abstractmethod`) with default return `{"indicators": {}, "conditions": [], "signal": None}`
- **Why**: `@abstractmethod` prevents instantiation in chained PRs. A concrete default is backward compatible — strategies without `explain()` return empty dict, scanner checks `hasattr()` before calling.
- **Signature**: `def explain(self, data: pd.DataFrame, symbol: Optional[str] = None) -> Dict[str, Any]`
- **Docstring**: Full return contract (indicators, conditions, signal keys)

### src/royaltdn/strategy/sma_strategy.py — Modify (~80 lines)

- Extract `_compute_indicators(data, symbol=None) -> dict` returning `{"sma_fast": X, "sma_slow": Y, "curr_fast": X, "curr_slow": Y}`
- Refactor `generate_signal()`: call `self._compute_indicators()` then logic gates
- Implement `explain()`: call `_compute_indicators()`, build conditions for crossover, return dict
- Signature includes `symbol` for profile resolution (crypto/stocks)

### src/royaltdn/strategy/bollinger_rsi.py — Modify (~70 lines)

- Extract `_compute_indicators()` returning `{"rsi": X, "bb_mid": X, "bb_upper": X, "bb_lower": X, "close": X}`
- Refactor `generate_signal()`, implement `explain()`

### src/royaltdn/strategy/momentum_atr.py — Modify (~80 lines)

- Extract `_compute_indicators(data, symbol=None)` returning `{"momentum": X, "atr": X}` — uses `symbol` for profile resolution
- Refactor `generate_signal()`, implement `explain()`

### src/royaltdn/strategy/swing_trend_following.py — Modify (~60 lines)

- Extract `_compute_indicators()` returning trend indicators
- Refactor `generate_signal()`, implement `explain()`

### src/royaltdn/strategy/swing_breakout.py — Modify (~60 lines)

- Extract `_compute_indicators()` returning breakout levels
- Refactor `generate_signal()`, implement `explain()`

### src/royaltdn/scanner/scanner.py — Modify (~30 lines)

- `scan(verbose=False)` param: when True, call `strategy.explain(data)` per (strategy, symbol) pair
- Guard: `if hasattr(strategy, 'explain')` before calling
- New attribute `self._last_explanations: Dict[str, Dict[str, dict]]`
- `_write_verbose_log()`: append ISO-8601 line per (strategy, symbol) to `logs/scanner_verbose.log`

### tests/test_fase18_4_pr1.py — Create (~40 lines)

- Test `explain()` concrete default returns empty template on a mock strategy
- Test `generate_signal()` still produces same output after `_compute_indicators()` refactor (sma_strategy: golden cross and no-trigger data)
- Test `scan(verbose=True)` stores 1 strategy × 2 symbols → 2 entries
- Test `scan(verbose=False)` does not populate explanations
- Test scanner guards against strategies without `explain()` (duck typing)

---

## PR 2 — explain() scalping (5 strategies)

**Est. lines**: ~350 | **Target branch**: `PR-1`

### src/royaltdn/strategy/scalping_momentum.py — Modify (~70 lines)

- `_compute_indicators(data, symbol=None)` → `{"pct_change": X, "close": X}`
- `generate_signal()` → delegate to `_compute_indicators()`
- `explain()` → condition: `pct_change > min_momentum_pct` (BUY) or `< -min_momentum_pct` (SELL)

### src/royaltdn/strategy/scalping_breakout.py — Modify (~70 lines)

- `_compute_indicators()` → `{"high_break": X, "low_break": X, "close": X}`
- Same refactor + explain()

### src/royaltdn/strategy/scalping_reversion.py — Modify (~70 lines)

- `_compute_indicators()` → RSI/stochastic values
- Same refactor + explain()

### src/royaltdn/strategy/scalping_orderflow.py — Modify (~70 lines)

- `_compute_indicators()` → order flow imbalance metrics
- Same refactor + explain()

### src/royaltdn/strategy/scalping_spread.py — Modify (~70 lines)

- `_compute_indicators()` → spread/bid-ask metrics
- Same refactor + explain()

### tests/test_fase18_4_pr2.py — Create (~40 lines)

- Parametrized test: each scalping strategy's `explain()` conditions match `generate_signal()` signal
- Test `gap_pct` calculation per spec
- Test edge case: exactly at threshold → met=True, gap=0.0

---

## PR 3a — explain() intraday (5 strategies)

**Est. lines**: ~350 | **Target branch**: `PR-2`

### src/royaltdn/strategy/intraday_trend.py — Modify (~70 lines)

- `_compute_indicators(data, symbol=None)` → EMA fast/slow + ATR% — uses `symbol` for profile
- `generate_signal()` → delegate
- `explain()` → condition per gate (EMA crossover + ATR threshold)

### src/royaltdn/strategy/intraday_vwap.py — Modify (~70 lines)

- `_compute_indicators(data, symbol=None)` → VWAP, std, lower/upper bands — uses `symbol` for profile
- Same refactor + explain()

### src/royaltdn/strategy/intraday_volume_breakout.py — Modify (~70 lines)

- `_compute_indicators()` → volume spike metrics
- Same refactor + explain()

### src/royaltdn/strategy/intraday_support_resistance.py — Modify (~70 lines)

- `_compute_indicators()` → S/R levels
- Same refactor + explain()

### src/royaltdn/strategy/intraday_macd_divergence.py — Modify (~70 lines)

- `_compute_indicators()` → MACD line, signal, histogram
- Same refactor + explain()

### tests/test_fase18_4_pr3a.py — Create (~40 lines)

- Parametrized test across all 5 intraday strategies for explain() contract compliance
- Test `_compute_indicators()` + `generate_signal()` consistency for each
- Test explain() conditions reflect gate logic correctly

---

## PR 3b — explain() swing (3) + all-17 iteration test + design docs

**Est. lines**: ~300 | **Target branch**: `PR-3a`

### src/royaltdn/strategy/factor_rotation.py — Modify (~70 lines)

- `_compute_indicators()` → factor scores
- Refactor + explain()

### src/royaltdn/strategy/swing_reversion.py — Modify (~60 lines)

- `_compute_indicators()` → overbought/oversold metrics
- Refactor + explain()

### src/royaltdn/strategy/__init__.py — Modify (~10 lines)

- If it exports strategy registry, ensure all 17 strategies are listed

### tests/test_fase18_4_pr3b.py — Create (~70 lines)

- Parametrized test across all 3 swing strategies for explain() contract compliance
- **All-17 iteration test**: iterate all registered strategies, call `explain()` on each with test data, assert no exceptions and valid return structure
- Test `_compute_indicators()` + `generate_signal()` consistency

### openspec/changes/fase-18-4-scanner-verbose/design/file_change_map.md — Modify (~50 lines)

- Update PR chain diagram and line counts after earlier PRs are complete

---

## PR 4 — UI verbose + dynamic interval + scalping disable + check-readiness + tests

**Est. lines**: ~380 | **Target branch**: `PR-3b`

### src/royaltdn/frontend/menu/app.py — Modify (~120 lines)

**Scalping disable in _cycle_universe() (CRITICAL):**
- **Change**: Add `_disable_scalping_in_strategies_json()` helper in app.py
  - Read `logs/strategies.json`, iterate strategies, set `active=false` for `category="scalping"` when universe is not `"crypto"`
  - Atomic write via `.tmp` + `os.replace()`
  - Log warning via `logger.warning("Scalping desactivado por cambio de universo a {universe}")`
- In `_cycle_universe()`: after rotating universe and calling `_universe_setter`, call `_disable_scalping_in_strategies_json()` if `new_uni != "crypto"`
- `new_uni == "crypto"`: do NOT auto-reactivate — let user toggle manually
- **Cross-thread note**: app.py writes directly to `strategies.json`. The orchestrator reads whatever is there — no race because writes are atomic and the orchestrator's `_build_strategies_list()` just references `strategies.json` indirectly via scanner state.

**Scalping notification in main menu:**
- `_print_menu()` or separate check: if universe != "crypto" and any strategy has category="scalping" in `strategies.json`, show `"Scalping desactivado: no compatible con el mercado actual."` in bold red

**Estrategias submenu warning:**
- Before toggling a strategy to active, check if it's scalping AND universe != "crypto" → show confirmation prompt with warning text per spec

**Scanner verbose UI:**
- `_show_scanner()`: detect verbose mode, new `_render_verbose_dashboard()` for L1 (per-symbol Panels, closeness bars)
- Navigation: `↑`/`↓` cursor, `E` expands to L2 decision tree
- `_render_decision_tree()`: per-strategy condition tables with ✅/❌
- '0' key → exit L2 back to L1, or L1 back to menu
- 's' key → trigger_scanner() then re-render

**Log filter:**
- `_show_logs()`: add option "6" for "Verbose" filter → read `logs/scanner_verbose.log`

**Dynamic interval display:**
- `_show_scanner()`: read `status.json["scanner_interval_minutes"]`, display "Intervalo: X min"
- `_build_kpis()`: add Scan interval KPI from status.json, show "(env)" when override active

**New attributes:**
- `_scanner_verbose_mode: bool`, `_scanner_cursor_index: int`, `_scanner_explanations: dict`

### src/royaltdn/orchestrator.py — Modify (~40 lines)

**Remove module-level zombie constant:**
- **Delete** line 77: `SCANNER_INTERVAL_MINUTES = int(os.getenv("SCANNER_INTERVAL_MINUTES", "60"))`
- **Delete** line 78: `SCANNER_TOP_N = int(os.getenv("SCANNER_TOP_N", "3"))` — unchanged, no issue

**Add _get_scan_interval_override():**
- New module-level function: `def _get_scan_interval_override() -> int | None:`
  - Read `SCANNER_INTERVAL_MINUTES` env var dynamically
  - Return `int` if valid positive integer
  - Return `None` if not set or invalid (log warning on invalid)

**Add _calc_scan_interval() method:**
- Call `_get_scan_interval_override()` first → return if set
- Else: build categories from `_build_strategies_list()` active strategies
- Mapping: scalping→2, intraday→15, swing→240, none→60

**Update _run_legacy_loop():**
- Replace `scanner_iterations` with per-cycle recalculation:
  ```python
  def _recalc_scanner_iterations(self, poll_interval: int) -> int:
      interval = self._calc_scan_interval()
      return int((interval * 60) / poll_interval) if interval > 0 else 0
  ```
- Store `self._current_scan_interval: int` from `_calc_scan_interval()`
- Write `scanner_interval_minutes` to `status.json` in `_publish_status()`
- Include source info: `{"interval": X, "source": "env"|"auto"}`

**Scalping disable: REMOVED from orchestrator**
- The old design placed scalping disable in `_build_strategies_list()` — this is REMOVED
- No `_universe` attribute on Orchestrator for scalping purposes
- The orchestrator simply publishes whatever `strategies.json` has

### src/royaltdn/main.py — Modify (~40 lines)

**--verbose flag:**
- Parse `--verbose` from `sys.argv[2:]` in `cmd_run()`
- Set `scanner.verbose = True`

**cmd_check_readiness():**
- Read `logs/trades.json` → check trades ≥ 50
- Read `logs/equity.json` → extract Sharpe > 0.5 (from equity_curve)
- Read `logs/trades.json` → avg slippage < 50 bps
- Check bot.log for kill switch entries and "Telegram enviado" within last 24h
- Broker check: AlpacaBroker.get_account() + _testnet_client / Binance ping
- Build Rich Panel with 6 checks + verdict READY / CASI LISTO / NO RECOMENDADO
- Exit code: 0 (READY), 1 (CASI LISTO), 2 (NO RECOMENDADO)

**CLI registration:**
- Add `"check-readiness": cmd_check_readiness` to commands dict

### tests/test_fase18_4_pr4.py — Create (~80 lines)

- Test `_get_scan_interval_override()`: set env var → returns int, unset → returns None, invalid → logs warning + returns None
- Test `_calc_scan_interval()`: scalping→2, intraday→15, swing→240, empty→60
- Test env var override: set `SCANNER_INTERVAL_MINUTES=30` with scalping → 30
- Test scalping disable in app.py: mock strategies.json with scalping, call _cycle_universe() to sp500 → assert active=false written; call to crypto → assert unchanged
- Test notification: universe=sp500 with scalping → notification rendered; crypto → no notification
- Test estrategias submenu warning: non-crypto + scalping toggle → confirmation prompt
- Test check-readiness: mock StateLoader return values, assert 3 verdict variants
- Test `cmd_check_readiness()` exit codes: 0, 1, 2
