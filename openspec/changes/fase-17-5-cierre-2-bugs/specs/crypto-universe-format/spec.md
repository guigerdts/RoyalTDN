# Delta for crypto-universe-format

## MODIFIED Requirements

### Requirement: REQ-CRYPTO-UNIVERSE — Crypto asset universe

`AssetUniverse` MUST accept `"crypto"` as a valid universe type (via `VALID_UNIVERSE_TYPES`) and SHALL return exactly 10 hardcoded pairs from broker-aware constants when universe is `"crypto"`.

`AssetUniverse` SHALL accept an optional `broker_type` parameter (default `"alpaca"`). `_get_default_crypto()` SHALL return the correct symbol format based on the active broker:

- `broker_type="alpaca"` (default): returns Alpaca-format pairs from `DEFAULT_CRYPTO`.
- `broker_type="binance"`: returns Binance-format pairs from `DEFAULT_CRYPTO_BINANCE`.

**`DEFAULT_CRYPTO`:** `BTC/USD, ETH/USD, LTC/USD, BCH/USD, LINK/USD, UNI/USD, AAVE/USD, MATIC/USD, DOGE/USD, SHIB/USD`

**`DEFAULT_CRYPTO_BINANCE`:** `BTCUSDT, ETHUSDT, LTCUSDT, BCHUSDT, LINKUSDT, UNIUSDT, AAVEUSDT, MATICUSDT, DOGEUSDT, SHIBUSDT`

(Previously: `_get_default_crypto()` returned hardcoded Alpaca-format symbols regardless of broker.)

#### Scenario: Default broker returns Alpaca-format pairs

- GIVEN `SCANNER_UNIVERSE=crypto` and `broker_type` defaults to `"alpaca"`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN exactly the 10 `DEFAULT_CRYPTO` pairs are returned (e.g. `BTC/USD`, `ETH/USD`)
- AND no API call is made

#### Scenario: Binance broker returns Binance-format pairs

- GIVEN `SCANNER_UNIVERSE=crypto` and `broker_type="binance"`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN exactly the 10 `DEFAULT_CRYPTO_BINANCE` pairs are returned (e.g. `BTCUSDT`, `ETHUSDT`)
- AND no API call is made

### Requirement: REQ-CRYPTO-LIQUIDITY — Liquidity filter routes crypto through broker, handles NaN

`LiquidityFilter` MUST detect `/` in the symbol to route to the correct data source:
- `/` present → `broker.get_bars()` (uses the broker assigned to crypto assets)
- No `/` → `StockHistoricalDataClient.get_stock_bars()` (unchanged)
- SHALL share the same `TokenBucket` for rate limiting with stock calls
- SHALL use `SCANNER_CRYPTO_MIN_VOLUME` env var (default `100_000` USD) as minimum volume threshold
- **SHALL handle empty DataFrames from crypto broker:** when `broker.get_bars()` returns an empty DataFrame, SHALL log a warning at `logger.warning()` level with the message `"⚠️ Sin datos para {symbol}. Posiblemente el par no está disponible en el testnet."` and skip the symbol (return False) instead of crashing.
- **SHALL handle NaN DataFrames from any data source:** when `get_bars()` or `get_stock_bars()` returns a DataFrame where the volume column is all NaN, SHALL log a debug warning and skip the symbol (return False) instead of crashing.
(Previously: empty DataFrames from crypto broker logged a debug warning without specific message; `_get_default_crypto()` was not broker-aware.)

#### Scenario: Symbol with / uses broker.get_bars

- GIVEN a symbol containing `/` (e.g. `"BTC/USD"`)
- WHEN `LiquidityFilter.filter()` processes it with a crypto broker configured
- THEN `broker.get_bars()` is called with the symbol
- AND the shared `TokenBucket` is consumed

#### Scenario: Stock symbol still uses get_stock_bars

- GIVEN a symbol without `/` (e.g. `"SPY"`)
- WHEN `LiquidityFilter.filter()` processes it
- THEN `get_stock_bars()` is called (unchanged behavior)

#### Scenario: Empty DataFrame from crypto broker logs visible warning

- GIVEN `broker.get_bars()` returns an empty DataFrame for a crypto symbol
- WHEN `LiquidityFilter.filter()` processes it
- THEN a warning at `logger.warning()` level is logged with the message `"⚠️ Sin datos para {symbol}..."`
- AND the symbol is skipped (returns False)
- AND no crash occurs

#### Scenario: NaN volume column from any source

- GIVEN `broker.get_bars()` returns a DataFrame where the volume column is all NaN
- WHEN `LiquidityFilter.filter()` processes the symbol
- THEN a debug warning is logged
- AND the symbol is skipped (returns False)
- AND no crash occurs

#### Scenario: Valid crypto data passes filter

- GIVEN `broker.get_bars()` returns a valid DataFrame with sufficient volume (`> SCANNER_CRYPTO_MIN_VOLUME`)
- WHEN `LiquidityFilter.filter()` processes the symbol
- THEN the symbol passes liquidity (returns True)
- AND volume is computed correctly using float arithmetic

### Requirement: REQ-CRYPTO-MAIN — Multi-broker initialization in main.py

`main.py` MUST create `BinanceBroker` when `BINANCE_API_KEY` is set and pass it via a `brokers: Dict[str, BaseBroker]` dict to `Scanner.__init__()` and `Orchestrator.__init__()`.

`main.py` MUST detect the active crypto broker and pass `broker_type` to `AssetUniverse.__init__()`. Broker type SHALL be `"binance"` when `BINANCE_API_KEY` is set, and `"alpaca"` otherwise.

(Previously: `main.py` did not pass `broker_type` to `AssetUniverse`.)

#### Scenario: BinanceBroker created and passed

- GIVEN `BINANCE_API_KEY` and `BINANCE_SECRET_KEY` are set
- WHEN `main.py` initializes the scanner
- THEN `BinanceBroker` is constructed with the testnet URL when `BINANCE_TESTNET=true`
- AND the `brokers` dict with `"crypto"` key is passed to `Scanner` and `Orchestrator`

#### Scenario: Broker type forwarded to AssetUniverse

- GIVEN `BINANCE_API_KEY` is set
- WHEN `AssetUniverse` is initialized
- THEN `broker_type="binance"` is passed to `AssetUniverse.__init__()`
- AND `get_symbols()` returns Binance-format pairs

#### Scenario: Default broker type when no Binance

- GIVEN `BINANCE_API_KEY` is NOT set
- WHEN `AssetUniverse` is initialized
- THEN `broker_type` defaults to `"alpaca"`
- AND `get_symbols()` returns Alpaca-format pairs
