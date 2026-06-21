# Tasks: FASE 17.5 (CIERRE) — Corrección definitiva de los 2 bugs restantes

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~80 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR, 2 commits (1 per bug) |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Bug 7 + Bug 2 + tests | Single PR | 2 commits, ~80 lines total |

## Phase 1: Bug 7 — .pyc cache (1 file, trivial)

- [x] 1.1 Add `import sys; sys.dont_write_bytecode = True` as first executable lines in `src/royaltdn/__init__.py`

## Phase 2: Bug 2 — Crypto symbol format (6 files)

- [x] 2.1 Add `DEFAULT_CRYPTO_BINANCE` constant, `_CRYPTO_SYMBOLS` frozenset, and `is_crypto_symbol()` helper in `src/royaltdn/scanner/universe.py`
- [x] 2.2 Add `broker_type="alpaca"` param to `AssetUniverse.__init__()`; update `_get_default_crypto()` to return `DEFAULT_CRYPTO_BINANCE` when `broker_type="binance"`
- [x] 2.3 Detect `BINANCE_API_KEY` in `src/royaltdn/main.py` and pass `broker_type` to `AssetUniverse()`
- [x] 2.4 In `src/royaltdn/scanner/filters.py`: replace `"/" in symbol` → `is_crypto_symbol(symbol)`, add `logger.warning()` when `broker.get_bars()` returns empty DataFrame
- [x] 2.5 In `src/royaltdn/scanner/scanner.py`, `src/royaltdn/orchestrator.py`, `src/royaltdn/risk/risk_manager.py`: replace each `"/" in symbol` → `is_crypto_symbol(symbol)`

## Phase 3: Tests

- [x] 3.1 Parametrized test for `is_crypto_symbol()`: BTC/USD, BTCUSDT → True; SPY, AAPL → False
- [x] 3.2 Test `_get_default_crypto()` with `broker_type="alpaca"` (slash symbols) and `"binance"` (clean symbols)
- [x] 3.3 Test `LiquidityFilter.filter()` with empty broker DataFrame: verify `logger.warning()` logged and symbol skipped
