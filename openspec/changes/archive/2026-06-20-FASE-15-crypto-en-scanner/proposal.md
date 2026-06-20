# Proposal: FASE 15 — Crypto en el Scanner

## Intent

Add Alpaca Crypto API to the scanner for 24/7 crypto pair scanning. Fix `int(b.volume)` crash on crypto Decimal volumes.

## Scope

### In Scope
- Universe `crypto` in AssetUniverse (10 hardcoded pairs: BTC/USD, ETH/USD, LTC/USD, BCH/USD, LINK/USD, UNI/USD, AAVE/USD, MATIC/USD, DOGE/USD, SHIB/USD)
- LiquidityFilter branches: `get_stock_bars()` vs `get_crypto_bars()` by `/` in symbol
- Scanner `_batch_get_symbol_data()` branches by asset type + fixes `int(b.volume)` → `float(b.volume)`
- UI: `"crypto"` added to universe_label map in `_show_scanner()`
- Env: `SCANNER_UNIVERSE=crypto` valid; `SCANNER_CRYPTO_MIN_VOLUME` (default 100_000 USD)

### Out of Scope
- Merging `crypto` into `all` — separate only
- Dynamic crypto discovery via API — hardcoded list
- Crypto-specific strategies — OHLCV strategies work unchanged
- Trading crypto signals — scanner only, execution deferred

## Capabilities

### New Capabilities
- `crypto-scanner`: Crypto asset universe, liquidity filter, data download with Decimal volume fix.

### Modified Capabilities
- `scanner-universe`: Accept `SCANNER_UNIVERSE=crypto` as valid (was invalid-fallback scenario).
- `scanner-display`: Include `"crypto" → "Crypto (10 pairs)"` in universe label map.

## Approach

1. **AssetUniverse**: Add `"crypto"` to `VALID_UNIVERSE_TYPES`, `DEFAULT_CRYPTO` list (10 pairs), `_get_default_crypto()` method.
2. **LiquidityFilter** (`filters.py`): Detect `/` in symbol → use `CryptoHistoricalDataClient.get_crypto_bars()` with `CryptoBarsRequest`. Import: `from alpaca.data.historical import CryptoHistoricalDataClient`. Share the same `TokenBucket` for rate limiting (not a separate one).
3. **Scanner** (`scanner.py`): Add `CryptoHistoricalDataClient` parameter to `__init__()`. In `_batch_get_symbol_data()`, detect asset type by symbol content (`/` in name = crypto); split batches by type; use the correct client per batch. Fix `int(b.volume)` → `float(b.volume)` universally. Import: `from alpaca.data.historical import CryptoHistoricalDataClient`.
4. **main.py**: Create both `StockHistoricalDataClient(api_key, secret_key)` and `CryptoHistoricalDataClient(api_key, secret_key)` and pass both to `Scanner.__init__()`.
5. **UI** (`app.py`): Add `"crypto": "Crypto (10 pairs)"` to `universe_label` dict.

### API verification
`get_crypto_bars()` signature (confirmed 2026-06-20):
- Takes `request_params: CryptoBarsRequest` (same pattern as `get_stock_bars`)
- Optional `feed: CryptoFeed = CryptoFeed.US`
- `CryptoBarsRequest` fields: `symbol_or_symbols`, `timeframe`, `start`, `end`, `limit`, `sort` (same as `StockBarsRequest`)
- `CryptoHistoricalDataClient(api_key, secret_key)` — same constructor pattern
- No new packages needed

## Affected Areas

| Area | Impact | Change |
|------|--------|--------|
| `src/royaltdn/scanner/universe.py` | Modified | Crypto universe type + symbol list |
| `src/royaltdn/scanner/filters.py` | Modified | Import + branch on `/` → crypto bars; shared TokenBucket |
| `src/royaltdn/scanner/scanner.py` | Modified | Add crypto client param; batch split by type; Decimal fix; import |
| `src/royaltdn/main.py` | Modified | Both data clients, pass both to Scanner |
| `src/royaltdn/frontend/menu/app.py` | Modified | Add crypto to universe_label |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Crypto bars use Decimal volume — int() crashes | High | Fix to float() universally |
| Crypto bars have different MultiIndex schema | Med | Inspect and adapt parser per endpoint (verified: same pandas DataFrame pattern) |
| Mixed stock+crypto batch | Low | Split batches by type |
| Crypto API key vs free tier | Low | Same paper keys work; `CryptoHistoricalDataClient` accepts None for free |

## Rollback

- Revert `SCANNER_UNIVERSE` to pre-crypto values (no code revert needed for config)
- Revert changes: `universe.py`, `filters.py`, `scanner.py`, `main.py`, `app.py`
- Restore `int(b.volume)` and `get_stock_bars()`-only flow

## Dependencies

- `alpaca-py` installed — `CryptoHistoricalDataClient` available. No new packages.

## Success Criteria

- [ ] `SCANNER_UNIVERSE=crypto` returns 10 pairs, no crash
- [ ] LiquidityFilter uses `get_crypto_bars()` for crypto, `get_stock_bars()` for stocks
- [ ] Scanner generates crypto signals without Decimal crash
- [ ] UI shows `"Universo: Crypto (10 pairs)"` for `SCANNER_UNIVERSE=crypto`
- [ ] All existing stock scanner tests pass unchanged
