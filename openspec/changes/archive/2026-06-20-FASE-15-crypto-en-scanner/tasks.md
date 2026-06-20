# Tasks: FASE 15 — Crypto en el Scanner

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~75-100 |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (backend) → PR 2 (UI+verify) |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend: universe + filters + scanner + main.py + test fix | PR 1 | base=`feature/FASE-15-crypto`; all core logic |
| 2 | UI label + run tests + manual verify | PR 2 | base=PR#1 branch; app.py + pytest |

## Phase 1: Fix previo

- [x] T-1: `tests/test_scanner.py:87` — change `universe_type="crypto"` to `universe_type="invalid_xyz"` in `test_asset_universe_invalid_type()`

## Phase 2: Universe

- [x] T-2: `src/royaltdn/scanner/universe.py:41` — add `"crypto"` to `VALID_UNIVERSE_TYPES`
- [x] T-3: same file — add `DEFAULT_CRYPTO` class attribute with 10 pairs (BTC/USD, ETH/USD, LTC/USD, BCH/USD, LINK/USD, UNI/USD, AAVE/USD, MATIC/USD, DOGE/USD, SHIB/USD)
- [x] T-4: same file — add `_get_default_crypto()` method returning `DEFAULT_CRYPTO.copy()`
- [x] T-5: same file — in `get_symbols()`, add `elif self._universe_type == "crypto": result = self._get_default_crypto()`

## Phase 3: LiquidityFilter

- [x] T-6: `src/royaltdn/scanner/filters.py` — add `from alpaca.data.historical import CryptoHistoricalDataClient` + `from alpaca.data.requests import CryptoBarsRequest`
- [x] T-7: same file — in `filter()` loop, branch on `"/" in symbol`: crypto → `CryptoBarsRequest` + `data_client.get_crypto_bars()`, stock → `StockBarsRequest` + `data_client.get_stock_bars()`
- [x] T-8: same file — shared `self.token_bucket` across both paths (no new bucket)

## Phase 4: Scanner

- [x] T-9: `src/royaltdn/scanner/scanner.py` — add `crypto_data_client: Optional[Any] = None` param to `__init__()`, store as `self.crypto_data_client`
- [x] T-10: same file — in `_batch_get_symbol_data()`, split symbols into crypto (contains `/`) and stock batches
- [x] T-11: same file — build `CryptoBarsRequest` for crypto batches → `self.crypto_data_client.get_crypto_bars()`; `StockBarsRequest` for stocks → `self.data_client.get_stock_bars()`
- [x] T-12: same file line 248 — change `int(b.volume)` → `float(b.volume)`

## Phase 5: main.py wiring

- [x] T-13: `src/royaltdn/main.py` — add `from alpaca.data.historical import CryptoHistoricalDataClient`, create `crypto_data_client = CryptoHistoricalDataClient(API_KEY, API_SECRET)`
- [x] T-14: same file line 268 — pass `crypto_data_client=crypto_client` to `Scanner()`

## Phase 6: UI

- [x] T-15: `src/royaltdn/frontend/menu/app.py:1329-1333` — add `"crypto": "Crypto (10 pairs)"` to `universe_label` dict

## Phase 7: Verificación

- [x] T-16: Run `pytest` — confirm all existing tests pass (no regressions)
- [x] T-17: Manual: set `SCANNER_UNIVERSE=crypto`, run scan, verify signals without crashes
