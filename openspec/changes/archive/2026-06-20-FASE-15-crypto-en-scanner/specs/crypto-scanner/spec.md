# Crypto Scanner Specification

## Purpose

Add Alpaca Crypto API support for 24/7 crypto pair scanning. Fix `int(b.volume)` crash on crypto Decimal volumes. Ten hardcoded pairs, no dynamic discovery.

## Requirements

### REQ-CRYPTO-UNIVERSE — Crypto asset universe

`AssetUniverse` MUST accept `"crypto"` as a valid universe type (via `VALID_UNIVERSE_TYPES`) and SHALL return exactly 10 hardcoded pairs from `DEFAULT_CRYPTO`.

**`DEFAULT_CRYPTO`:** `BTC/USD, ETH/USD, LTC/USD, BCH/USD, LINK/USD, UNI/USD, AAVE/USD, MATIC/USD, DOGE/USD, SHIB/USD`

#### Scenario: crypto returns 10 pairs from DEFAULT_CRYPTO

- GIVEN `SCANNER_UNIVERSE=crypto`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN exactly the 10 `DEFAULT_CRYPTO` pairs are returned
- AND no API call is made (hardcoded list)

### REQ-CRYPTO-LIQUIDITY — Liquidity filter branches by `/` in symbol

`LiquidityFilter` MUST detect `/` in the symbol to choose the correct historical client:
- `/` present → `CryptoHistoricalDataClient.get_crypto_bars()`
- No `/` → `StockHistoricalDataClient.get_stock_bars()` (unchanged)
- SHALL share the same `TokenBucket` for rate limiting with stock calls
- SHALL use `SCANNER_CRYPTO_MIN_VOLUME` env var (default `100_000` USD) as minimum volume threshold
- SHALL import `CryptoHistoricalDataClient` and `CryptoBarsRequest` from `alpaca.data.historical`

#### Scenario: Symbol with / uses get_crypto_bars

- GIVEN a symbol containing `/` (e.g. `"BTC/USD"`)
- WHEN `LiquidityFilter.filter()` processes it
- THEN `get_crypto_bars()` is called with a `CryptoBarsRequest`
- AND the shared `TokenBucket` is consumed

#### Scenario: Stock symbol still uses get_stock_bars

- GIVEN a symbol without `/` (e.g. `"SPY"`)
- WHEN `LiquidityFilter.filter()` processes it
- THEN `get_stock_bars()` is called (unchanged behavior)

### REQ-CRYPTO-SCANNER — Scanner batch split and Decimal fix

`Scanner` MUST accept a `CryptoHistoricalDataClient` parameter in `__init__()` and split `_batch_get_symbol_data()` by asset type. MUST use `float(b.volume)` universally (replacing `int(b.volume)`).

#### Scenario: Mixed batch split by type

- GIVEN `_batch_get_symbol_data()` receives stock and crypto symbols
- WHEN batches are formed
- THEN stock symbols use `StockHistoricalDataClient`
- AND crypto symbols use `CryptoHistoricalDataClient`

#### Scenario: Decimal volume does not crash

- GIVEN a crypto bar with `volume=Decimal('1234.5678')`
- WHEN `int(b.volume)` would have been called
- THEN `float(b.volume)` succeeds
- AND the signal is generated without `TypeError`

#### Scenario: All-stock batch unchanged

- GIVEN only stock symbols (no `/`)
- WHEN `_batch_get_symbol_data()` runs
- THEN behavior is identical to the pre-crypto flow

### REQ-CRYPTO-MAIN — Client initialization in main.py

`main.py` MUST create both `StockHistoricalDataClient(api_key, secret_key)` and `CryptoHistoricalDataClient(api_key, secret_key)` and pass both to `Scanner.__init__()`.

#### Scenario: Both clients created

- GIVEN `main.py` initializes the scanner
- WHEN both data clients are constructed
- THEN both use the same `api_key` and `secret_key`
- AND `CryptoHistoricalDataClient` is passed to `Scanner`
