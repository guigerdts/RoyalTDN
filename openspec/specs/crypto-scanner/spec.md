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

### REQ-CRYPTO-LIQUIDITY — Liquidity filter routes crypto through broker

`LiquidityFilter` MUST detect `/` in the symbol to route to the correct data source:
- `/` present → `broker.get_bars()` (uses the broker assigned to crypto assets)
- No `/` → `StockHistoricalDataClient.get_stock_bars()` (unchanged)
- SHALL share the same `TokenBucket` for rate limiting with stock calls
- SHALL use `SCANNER_CRYPTO_MIN_VOLUME` env var (default `100_000` USD) as minimum volume threshold

#### Scenario: Symbol with / uses broker.get_bars

- GIVEN a symbol containing `/` (e.g. `"BTC/USD"`)
- WHEN `LiquidityFilter.filter()` processes it with a crypto broker configured
- THEN `broker.get_bars()` is called with the symbol
- AND the shared `TokenBucket` is consumed

#### Scenario: Stock symbol still uses get_stock_bars

- GIVEN a symbol without `/` (e.g. `"SPY"`)
- WHEN `LiquidityFilter.filter()` processes it
- THEN `get_stock_bars()` is called (unchanged behavior)

### REQ-CRYPTO-SCANNER — Scanner multi-broker data routing

`Scanner` MUST accept a `brokers: Dict[str, BaseBroker]` parameter in `__init__()`. `_batch_get_symbol_data()` SHALL route crypto symbols (containing `/`) to `brokers["crypto"].get_bars()` and stock symbols to `StockHistoricalDataClient`. MUST use `float(b.volume)` universally (replacing `int(b.volume)`).

#### Scenario: Mixed batch routes by broker

- GIVEN `_batch_get_symbol_data()` receives stock and crypto symbols
- WHEN batches are formed
- THEN stock symbols use `StockHistoricalDataClient` (unchanged)
- AND crypto symbols use `brokers["crypto"].get_bars()`

#### Scenario: Decimal volume does not crash

- GIVEN a crypto bar with `volume=Decimal('1234.5678')`
- WHEN `int(b.volume)` would have been called
- THEN `float(b.volume)` succeeds
- AND the signal is generated without `TypeError`

#### Scenario: All-stock batch unchanged

- GIVEN only stock symbols (no `/`)
- WHEN `_batch_get_symbol_data()` runs
- THEN behavior is identical to the pre-crypto flow

### REQ-CRYPTO-MAIN — Multi-broker initialization in main.py

`main.py` MUST create `BinanceBroker` when `BINANCE_API_KEY` is set and pass it via a `brokers: Dict[str, BaseBroker]` dict to `Scanner.__init__()` and `Orchestrator.__init__()`.

#### Scenario: BinanceBroker created and passed

- GIVEN `BINANCE_API_KEY` and `BINANCE_SECRET_KEY` are set
- WHEN `main.py` initializes the scanner
- THEN `BinanceBroker` is constructed with the testnet URL when `BINANCE_TESTNET=true`
- AND the `brokers` dict with `"crypto"` key is passed to `Scanner` and `Orchestrator`
