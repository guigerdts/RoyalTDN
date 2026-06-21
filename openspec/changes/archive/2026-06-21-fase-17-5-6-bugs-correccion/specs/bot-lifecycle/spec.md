# Delta for bot-lifecycle

## MODIFIED Requirements

### REQ-CRYPTO-LIQUIDITY — Liquidity filter routes crypto through broker, handles NaN

`LiquidityFilter` MUST detect `/` in the symbol to route to the correct data source:
- `/` present → `broker.get_bars()` (uses the broker assigned to crypto assets)
- No `/` → `StockHistoricalDataClient.get_stock_bars()` (unchanged)
- SHALL share the same `TokenBucket` for rate limiting with stock calls
- SHALL use `SCANNER_CRYPTO_MIN_VOLUME` env var (default `100_000` USD) as minimum volume threshold
- **SHALL handle NaN/empty DataFrames from any data source:** when `get_bars()` or `get_stock_bars()` returns an empty DataFrame or a DataFrame where the volume column is all NaN, SHALL log a debug warning and skip the symbol (return False) instead of crashing.
(Previously: NaN/empty DataFrames from crypto broker could crash the volume check pipeline)

#### Scenario: Symbol with / uses broker.get_bars

- GIVEN a symbol containing `/` (e.g. `"BTC/USD"`)
- WHEN `LiquidityFilter.filter()` processes it with a crypto broker configured
- THEN `broker.get_bars()` is called with the symbol
- AND the shared `TokenBucket` is consumed

#### Scenario: Stock symbol still uses get_stock_bars

- GIVEN a symbol without `/` (e.g. `"SPY"`)
- WHEN `LiquidityFilter.filter()` processes it
- THEN `get_stock_bars()` is called (unchanged behavior)

#### Scenario: Empty DataFrame from crypto broker

- GIVEN `broker.get_bars()` returns an empty DataFrame for `"BTC/USD"`
- WHEN `LiquidityFilter.filter()` processes it
- THEN a debug warning is logged
- AND the symbol is skipped (returns False)
- AND no crash occurs

#### Scenario: NaN volume column from any source

- GIVEN `broker.get_bars()` returns a DataFrame where the volume column is all NaN
- WHEN `LiquidityFilter.filter()` processes the symbol
- THEN a debug warning is logged
- AND the symbol is skipped (returns False)
- AND no crash occurs

#### Scenario: Valid crypto data passes filter

- GIVEN `broker.get_bars()` returns a valid DataFrame with sufficient volume (> SCANNER_CRYPTO_MIN_VOLUME)
- WHEN `LiquidityFilter.filter()` processes the symbol
- THEN the symbol passes liquidity (returns True)
- AND volume is computed correctly using float arithmetic

### Requirement: PAUSADO Status Display — Immediate refresh on resume

MUST render `bot_status` in header, Control, Dashboard KPI. `_log_activity()` on pause/resume.

On resume, the status.json rewrite SHALL be synchronous (not deferred to a thread). The header SHALL read `logs_dir` parameter (instead of a hardcoded `logs/` path) to locate `status.json`. After writing, the system SHALL wait for the file to be readable before returning.
(Previously: status.json could be written asynchronously, causing stale "PAUSADO" in header after resume)

#### Scenario: Pause → PAUSADO
- GIVEN bot ONLINE
- WHEN user pauses
- THEN header "PAUSADO" bold yellow, Control "Bot: PAUSADO", Dashboard KPI "PAUSADO"

#### Scenario: Resume → ONLINE — immediate refresh
- GIVEN bot was PAUSADO
- WHEN user resumes
- THEN status.json is rewritten synchronously
- AND the header reflects "ONLINE" on the next render cycle
- AND no stale "PAUSADO" remains

#### Scenario: logs_dir parameter threaded correctly
- GIVEN the menu uses a `logs_dir` parameter (not hardcoded `"logs/"`)
- WHEN resume writes status.json
- THEN the file path is `{logs_dir}/status.json`
- AND the file is readable immediately after write

#### Scenario: Immediate switch via signal file
- GIVEN ONLINE status
- WHEN pause_signal.json `action:"pause"` is detected
- THEN status.json `bot_status` → "PAUSADO" synchronously
