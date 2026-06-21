## Exploration: FASE 17.5 (CIERRE) — Corrección de 2 bugs restantes

### Bug 2 — Parámetros crypto no se aplican en el LiquidityFilter

**Symptom**: `LiquidityFilter: 0/10 symbols passed` when SCANNER_UNIVERSE=crypto.

#### Current State

The LiquidityFilter has a **single creation site** in `src/royaltdn/main.py:271-282` inside `cmd_run()`. The orchestrator (`src/royaltdn/orchestrator.py`) does NOT create a LiquidityFilter — it receives a pre-built Scanner via its constructor.

The creation code in `main.py`:
```python
_crypto_mode = os.getenv("SCANNER_UNIVERSE", "all") == "crypto"
liquidity_filter = LiquidityFilter(
    min_volume=int(os.getenv("SCANNER_MIN_VOLUME", "1000" if _crypto_mode else "100000")),
    min_price=float(os.getenv("SCANNER_MIN_PRICE", "1.0" if _crypto_mode else "5.0")),
    max_spread_pct=float(os.getenv("SCANNER_MAX_SPREAD_PCT", "999" if _crypto_mode else "1.0")),
    brokers=brokers,
)
```

The code **appears correct** — `_crypto_mode` is computed before use, and the os.getenv defaults use the conditional expression properly.

**The AssetUniverse** (`src/royaltdn/scanner/universe.py`) correctly handles `"crypto"` mode via `_get_default_crypto()`, returning 10 crypto symbols (DEFAULT_CRYPTO list).

**The LiquidityFilter.filter()** (`src/royaltdn/scanner/filters.py:106-193`) processes crypto symbols through the crypto broker path:
1. Checks if `"/"` in symbol (all crypto pairs contain `/`)
2. Uses `self.brokers.get("crypto")` — BinanceBroker — to call `get_bars()`
3. Falls back to `crypto_data_client` (Alpaca CryptoHistoricalDataClient) only if no crypto broker
4. Checks `df.empty` and then `avg_volume >= min_volume and last_close >= min_price`

**BinanceBroker** (`src/royaltdn/brokers/binance.py:98-141`) returns a DataFrame with columns: timestamp (index), open, high, low, close, volume. Format is compatible with what LiquidityFilter expects.

#### Root Cause Analysis

Despite the parameter passing logic being syntactically correct, `0/10 symbols passed` happens because:

1. **Primary root cause**: The `LiquidityFilter.filter()` prioritizes `crypto_broker` (Binance testnet) over `crypto_data_client` (Alpaca). If `BinanceBroker.get_bars()` returns an **empty DataFrame** (likely because Binance testnet has no recent klines for these pairs), the `df.empty` check on line 175 skips ALL crypto symbols silently.

2. **No fallback when broker returns empty data**: There is no retry with `crypto_data_client` (Alpaca) when the broker returns empty data. The code only falls back to Alpaca if `crypto_broker is None`, not if `get_bars()` returns empty data.

3. **DEBUG-level logging hides failures**: Errors in data retrieval are logged at DEBUG level (`logger.debug(...)`), so they don't appear in default WARNING/INFO logging. The operator sees `0/10 symbols passed` with no explanation.

**Contributing factor**: The `.env` file has THREE duplicate `SCANNER_UNIVERSE` lines (lines 24-26: `etfs`, `crypto`, `crypto`). While `python-dotenv` uses the last value (`crypto`), the duplicates are a maintenance smell and may cause confusion.

#### Data Flow Trace

```
main.py:265-267 → AssetUniverse(universe_type="crypto") → 10 symbols (DEFAULT_CRYPTO)
         :270     → _crypto_mode = True
         :271-282 → LiquidityFilter(min_volume=1000, min_price=1.0, max_spread_pct=999, brokers=brokers)
         :296-300 → Scanner(universe, liquidity_filter, strategies, data_client, crypto_client, brokers)

scanner.py:90    → liquidity_filter.filter(10 crypto symbols, data_client, crypto_client)
filters.py:144   → "/" in symbol → True → crypto_broker.get_bars(...)
                   → BinanceBroker.get_bars("BTC/USD", "1d", start, end)
                   → Returns empty DataFrame (testnet has no klines)
                   → df.empty → True → skip ← HERE IS THE PROBLEM
```

#### Approach Recommendation

**Option A — Fallback from broker to Alpaca crypto client when data is empty** (Recommended)

Modify `filters.py:LiquidityFilter.filter()` to add a fallback: when `crypto_broker.get_bars()` returns an empty DataFrame, try `crypto_data_client` (Alpaca) before skipping.

- Pros: Uses BinanceBroker when available, falls back gracefully; minimal change scope
- Cons: Adds one extra API call per symbol in the worst case
- Effort: Low (3-5 lines changed, only in filters.py)

**Option B — Reorder priority: Alpaca first, Binance broker as fallback**

Swap the if/elif priority in the crypto data path so Alpaca crypto client is tried first, then Binance broker.

- Pros: Alpaca data is more reliable and always available with the API keys
- Cons: Changes the design intent (Binance broker data should be preferred for crypto pairs on Binance)
- Effort: Low

**Option C — Add logging at INFO level when all crypto symbols are skipped**

Add a log line at INFO level when `df.empty` and the symbol contains `/`, so operators can diagnose the issue.

- Pros: Helps debugging
- Cons: Doesn't fix the underlying data availability problem
- Effort: Very low (1-2 lines)

**Recommended**: Option A + Option C. Fix the silent empty-DataFrame skip and add logging.

#### Risks
- Option A could slow down the scan slightly (extra API call per crypto symbol when Binance fails)
- If both Binance and Alpaca fail, the result is still 0/10 — add logging so this is visible

---

### Bug 7 — Cambios de código no se reflejan hasta limpiar caché .pyc

**Symptom**: Python caches bytecode in `__pycache__/*.pyc`, and source changes don't take effect until cache is cleared.

#### Current State

- `src/royaltdn/__init__.py` exists (5 lines, just a comment header)
- `src/royaltdn/__main__.py` exists (imports `main()` from `royaltdn.main`)
- `sys.dont_write_bytecode` is NOT set anywhere in the codebase
- Entry point: `python -m royaltdn <command>` → `__main__.py` → imports `royaltdn.main` → calls `main()`

#### Root Cause Analysis

When `python -m royaltdn` runs:
1. Python imports `royaltdn` → executes `__init__.py`
2. `__main__.py` imports `royaltdn.main` → executes `main.py`
3. `main.py` imports submodules → each writes `.pyc` to `__pycache__/`

Without `sys.dont_write_bytecode = True`, Python writes a `.pyc` file for each imported module. On subsequent runs, if the `.pyc` is newer than the `.py` source, Python uses the cached bytecode instead — stale code runs.

#### Approach Recommendation

**Single option**: Add `import sys; sys.dont_write_bytecode = True` at the top of `__init__.py`.

**Why `__init__.py` instead of `main.py`?**
- `__init__.py` runs FIRST when any module in the `royaltdn` package is imported
- `main.py` runs later (in the `__main__.py` flow), meaning modules imported BEFORE `main.py` would still have their bytecode cached
- With `__init__.py`, the setting takes effect before any submodule import

**Module load order when `python -m royaltdn <command>`:**
```
1. royaltdn/__init__.py ← HERE: set sys.dont_write_bytecode = True (already compiled, but all subsequent modules protected)
2. royaltdn/__main__.py
3. royaltdn/main.py
4. royaltdn/orchestrator.py
5. royaltdn/scanner/*.py
... all subsequent imports
```

#### Side Effects
- **Startup**: Slightly slower (bytecode recompiled every run) — negligible for this codebase
- **Disk**: No `.pyc` files created — saves disk space
- **Correctness**: ZERO side effects — execution is identical, only caching behavior changes
- **Production**: Safe; many Python projects run with `-B` flag or `PYTHONDONTWRITEBYTECODE=1` in production

#### Risks
- None. This is a standard development practice.

---

### Affected Areas

| File | Bug | Why |
|------|-----|-----|
| `src/royaltdn/scanner/filters.py` | Bug 2 | LiquidityFilter.filter() — add empty-DataFrame fallback + logging |
| `src/royaltdn/main.py` | Bug 2 | Verify creation params; no changes needed if fix is in filters.py |
| `src/royaltdn/brokers/binance.py` | Bug 2 | Only if get_bars() needs fixing for testnet klines |
| `src/royaltdn/__init__.py` | Bug 7 | Add `sys.dont_write_bytecode = True` |
| `.env` | Bug 2 (minor) | Clean up duplicate SCANNER_UNIVERSE lines |

### Approaches Summary

#### Bug 2
1. **Fallback on empty DataFrame** (filters.py) — try crypto_data_client when crypto_broker.get_bars() returns empty — **RECOMMENDED**
2. **Swap priority** — Alpaca crypto data first, Binance broker second — alternative
3. **INFO-level logging** — add visibility when crypto symbols are skipped — complementary

#### Bug 7
1. **`sys.dont_write_bytecode = True` in `__init__.py`** — only option, straightforward

### Ready for Proposal
Yes — both bugs have clear root causes and well-defined fix approaches.
