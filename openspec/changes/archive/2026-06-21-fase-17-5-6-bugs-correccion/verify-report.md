## Verification Report

**Change**: FASE 17.5 — Corrección de 6 bugs detectados en pruebas con Binance Testnet
**Version**: N/A (no spec version)
**Mode**: Standard

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 18 |
| Tasks complete | 18 |
| Tasks incomplete | 0 |

### Build & Tests Execution

**Tests — test_menu.py**: ✅ 12 passed / 5 skipped (numpy C extension limitation — pre-existing)
```text
tests/test_menu.py::test_mock_filter_all_mock PASSED              ← Bug 1
tests/test_menu.py::test_mock_filter_mixed PASSED                  ← Bug 1
tests/test_menu.py::test_mock_filter_none_mock PASSED             ← Bug 1
tests/test_menu.py::test_crypto_default_symbol_btc PASSED          ← Bug 3
tests/test_menu.py::test_stocks_default_symbol_spy PASSED          ← Bug 3
tests/test_menu.py::test_crypto_default_config_symbol_wins PASSED ← Bug 3
tests/test_menu.py::test_resume_writes_status_json_sync PASSED    ← Bug 6
tests/test_menu.py::test_resume_status_json_written_to_correct_path PASSED ← Bug 6
tests/test_menu.py::test_import_menu PASSED
tests/test_menu.py::test_dashboard_empty_data PASSED
tests/test_menu.py::test_ctrl_c_menu_exit PASSED
tests/test_menu.py::test_dashboard_with_data PASSED
```

**Tests — test_scanner.py**: ⚠️ Environment limitation — numpy C extensions not loadable on Android/Termux (pre-existing). See WARNING below.

**Tests — test_backtesting.py**: ⚠️ Same limitation as test_scanner.py.

### Test Environment Note
numpy C extensions are incompatible with this Android/Termux platform (aarch64-linux-android vs aarch64-linux-gnu ABI). This is a pre-existing project limitation — documented in `test_menu.py`'s `_numpy_ok` guard. The project uses `pandas` and `numpy` at module level in `test_scanner.py` and `test_backtesting.py`, preventing import on this platform.

**Standalone logic verification**: ✅ All 6 bug fixes confirmed via Python snippet execution and source code inspection.

### Source-Level Implementation Verification

| Bug | File | Lines | What to Check | Status |
|-----|------|-------|---------------|--------|
| B1 | `app.py:_show_scanner()` | 1405-1410 | `real_signals = [s for s in top_signals if s.get("strategy") != "mock"]` filter before table render | ✅ Implemented |
| B2 | `filters.py:LiquidityFilter.filter()` | 175-180 | `if df.empty or df["volume"].isna().all():` guard before `df["volume"].mean()` | ✅ Implemented |
| B3 | `app.py:_quick_backtest()` | 1683-1687 | `os.getenv("SCANNER_UNIVERSE") == "crypto"` → `"BTC/USDT"`, else `"SPY"` | ✅ Implemented |
| B4 | `app.py:_quick_backtest()` | 1707 | `config.setdefault("version", 1)` before `validate_config(config)` | ✅ Implemented |
| B5 | `backtesting.py:_download_data()` | 54-69 | `"/" in symbol and broker is not None` → `broker.get_bars()`, normalize columns | ✅ Implemented |
| B6 | `app.py:_show_control()` | 3355-3373 | Sync `status.json` write after `resume_bot(logs_dir)` with ONLINE status | ✅ Implemented |

### Spec Compliance Matrix

| Spec | Requirement | Scenario | Test Evidence | Result |
|------|-------------|----------|---------------|--------|
| scanner-display | REQ-DISPLAY-FIX | All mock entries → empty state | `test_mock_filter_all_mock` | ✅ COMPLIANT (PASSED) |
| scanner-display | REQ-DISPLAY-FIX | Mixed real+mock → only real | `test_mock_filter_mixed` | ✅ COMPLIANT (PASSED) |
| scanner-display | REQ-DISPLAY-FIX | No mock entries → unchanged | `test_mock_filter_none_mock` | ✅ COMPLIANT (PASSED) |
| backtesting-engine | RQ-BT-DEFAULT-SYMBOL | Crypto → BTC/USDT | `test_crypto_default_symbol_btc` | ✅ COMPLIANT (PASSED) |
| backtesting-engine | RQ-BT-DEFAULT-SYMBOL | Stocks → SPY | `test_stocks_default_symbol_spy` | ✅ COMPLIANT (PASSED) |
| backtesting-engine | RQ-BT-VERSION-DEFAULT | Missing version → 1 | Source: line 1707 `config.setdefault("version", 1)` | ✅ COMPLIANT (verified by source) |
| backtesting-engine | RQ-BT-VERSION-DEFAULT | Explicit version 2 fails | Source: `validate_config` rejects `version != 1` | ✅ COMPLIANT (verified by source) |
| backtesting-engine | Crypto symbol → broker | `/` symbol routes to broker | Source: `backtesting.py` lines 54-69 | ✅ COMPLIANT (verified by source) |
| backtesting-engine | Stock symbol → yfinance | No `/` uses yfinance | Source: `backtesting.py` lines 76-101 | ✅ COMPLIANT (verified by source) |
| backtesting-engine | Empty DataFrame from broker | Returns None gracefully | Source: `backtesting.py` line 69 `return None` | ✅ COMPLIANT (verified by source) |
| bot-lifecycle | REQ-CRYPTO-LIQUIDITY | Empty/NaN DataFrame skip | Source: `filters.py` lines 175-180 | ✅ COMPLIANT (verified by source) |
| bot-lifecycle | REQ-CRYPTO-LIQUIDITY | Symbol with / uses broker.get_bars | Source: `filters.py` lines 144-164 | ✅ COMPLIANT (verified by source) |
| bot-lifecycle | PAUSADO Status | Resume writes status.json sync | `test_resume_writes_status_json_sync` | ✅ COMPLIANT (PASSED) |
| bot-lifecycle | PAUSADO Status | logs_dir threaded correctly | `test_resume_status_json_written_to_correct_path` | ✅ COMPLIANT (PASSED) |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| `_download_data()` accepts optional `broker` param | ✅ Yes | Line 48: `broker: Optional["BaseBroker"] = None` |
| Broker wired at call site (`_quick_backtest`/`_builder_flow`) | ✅ Yes | Lines 1714-1720 and 2235-2242 |
| `config.setdefault("version", 1)` in `_quick_backtest()` | ✅ Yes | Line 1707 |
| Sync status.json rewrite after resume | ✅ Yes | Lines 3359-3372, synchronous write, no deferral |
| NaN guard before volume mean in LiquidityFilter | ✅ Yes | Lines 175-180: `if df.empty or df["volume"].isna().all(): continue` |
| `_print_header()` threads `logs_dir` param | ✅ Yes | Line 96: `def _print_header(console, logs_dir: str = "logs") -> None:` |
| `run_backtest()` forwards `broker` to `_download_data()` | ✅ Yes | Line 214: `broker: Optional["BaseBroker"] = None`, line 241: `broker=broker` |
| `_quick_backtest()` wires BinanceBroker from env | ✅ Yes | Lines 1714-1720 |

### Deviations from Design (from apply-progress)

1. **`get_bars()` interface**: Used actual `BaseBroker.get_bars(symbol, timeframe, start, end)` with computed dates from `PERIOD_DAYS_MAP` instead of `limit=500` — correct decision, matches existing broker contract.
2. **Crypto without broker**: Added explicit `if "/" in symbol: return None` guard before yfinance block (yfinance can't handle `/` symbols) — reasonable guard, not a design violation.
3. **Function-level imports**: Used `import os as _os` in `_builder_flow()` to match lazy-import convention — respects project conventions.

### Issues Found

**CRITICAL**: None
**WARNING**: 
- 2 environment-limited test files (`test_scanner.py`, `test_backtesting.py`) could not be executed due to numpy C extension incompatibility with Android. All 5 skipped tests are numpy-dependent validation tests (schema validation). The 12 runnable tests all passed.
**SUGGESTION**: 
- Consider adding `_numpy_ok` guard to `test_scanner.py` and `test_backtesting.py` (like `test_menu.py`) so they can at least collect tests that don't need numpy. Currently the entire file fails at import time.

### Verdict
**PASS WITH WARNINGS**
18/18 tasks complete, 12/12 runnable tests passed, all 6 bugs verified via source code and logic. 5 tests skipped due to pre-existing numpy environment limitation — these are schema/protected tests that match project conventions (the `_numpy_ok` guard exists in `test_menu.py`). No code-level defects found.
