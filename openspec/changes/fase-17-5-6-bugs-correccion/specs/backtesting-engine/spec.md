# Delta for backtesting-engine

## MODIFIED Requirements

### RQ-BT-01 — Progress bar (tqdm) during backtest

SHALL display tqdm progress bars during `run_backtest()`. One bar for the signal generation loop, another for the portfolio simulation loop.

**Format:** `"{symbol} {timeframe} ({period}) — {n}/{total} bars"`

**Data routing:** `_download_data()` MUST check the symbol for `/`. If the symbol contains `/`, SHALL call `broker.get_bars()` (BinanceBroker). Otherwise, SHALL use yfinance (unchanged). When no crypto broker is configured and a `/` symbol is requested, SHALL raise a clear error. When `_download_data()` receives empty/NaN DataFrames from any source, SHALL return None gracefully.
(Previously: _download_data() used yfinance for all symbols; no crypto routing)

#### Scenarios

##### Progress bar shows during signal generation
- GIVEN `run_backtest()` is executing with 252 bars of daily data for symbol "SPY"
- WHEN the signal generation loop iterates over each bar
- THEN a tqdm progress bar is displayed with format `"{symbol} {timeframe} ({period}) — {n}/{total} bars"` where total = 252
- AND tqdm auto-ETA shows seconds remaining after the first few iterations

##### No progress bar when backtest errors before signal loop
- GIVEN `_download_data()` returns None for symbol "INVALID"
- WHEN `run_backtest()` returns an error
- THEN no tqdm progress bar is displayed

##### Portfolio simulation loop also shows progress
- GIVEN signals were generated for 252 bars
- WHEN the portfolio simulation loop runs
- THEN a second tqdm progress bar is displayed for the simulation iteration

##### KeyboardInterrupt during progress bar
- GIVEN a backtest is running with a tqdm progress bar active
- WHEN the user presses Ctrl+C
- THEN the backtest stops gracefully
- AND no orphaned tqdm output remains on screen

##### Crypto symbol downloads from Binance
- GIVEN `_download_data()` receives symbol "BTC/USDT" and a crypto broker is configured
- WHEN the function executes
- THEN `broker.get_bars("BTC/USDT")` is called (not yfinance)

##### Stock symbol still uses yfinance
- GIVEN `_download_data()` receives symbol "SPY"
- WHEN the function executes
- THEN yfinance is used (unchanged behavior)

##### No crypto broker with crypto symbol
- GIVEN `_download_data()` receives symbol "BTC/USDT" and NO crypto broker is configured
- WHEN the function executes
- THEN a clear error is raised indicating no crypto broker is available

##### Empty DataFrame from broker returns None
- GIVEN `broker.get_bars()` returns an empty DataFrame
- WHEN `_download_data()` processes the result
- THEN None is returned gracefully (no crash on NaN)

### RQ-BT-DEFAULT-SYMBOL — Quick backtest symbol depends on SCANNER_UNIVERSE

The quick-backtest default symbol SHALL depend on `SCANNER_UNIVERSE`. When the universe is `"crypto"`, the default SHALL be `"BTC/USDT"`. For all other universes (`"etfs"`, `"sp500"`, `"all"`), the default SHALL remain `"SPY"`. The symbol SHALL be read before the backtest dialog is shown so the user can accept or override.
(Previously: hardcoded "SPY" regardless of SCANNER_UNIVERSE)

#### Scenario: Crypto universe defaults to BTC/USDT
- GIVEN `SCANNER_UNIVERSE=crypto`
- WHEN the quick backtest screen opens
- THEN the default symbol shown is `"BTC/USDT"`
- AND the user MAY edit it before running

#### Scenario: Stocks universe defaults to SPY
- GIVEN `SCANNER_UNIVERSE=etfs` or `sp500` or `all`
- WHEN the quick backtest screen opens
- THEN the default symbol shown is `"SPY"` (unchanged)

#### Scenario: User overrides default
- GIVEN `SCANNER_UNIVERSE=crypto` and the dialog shows "BTC/USDT"
- WHEN the user enters "ETH/USDT"
- THEN the backtest runs on "ETH/USDT" (override respected)

### RQ-BT-VERSION-DEFAULT — Strategy version defaults to 1

Strategy config validation MUST accept a missing `"version"` field. When `config` has no `version` key, the system SHALL apply `config.setdefault("version", 1)` before validation runs. The validation error `"version must be 1"` SHALL NOT occur for strategies without an explicit version field.
(Previously: missing version field caused validation error)

#### Scenario: Missing version defaults to 1
- GIVEN a strategy config with no `"version"` key
- WHEN the strategy is loaded and validated
- THEN `version` is set to `1` automatically
- AND no validation error occurs

#### Scenario: Explicit version 1 passes
- GIVEN a strategy config with `"version": 1`
- WHEN validated
- THEN it passes without modification

#### Scenario: Explicit version != 1 still fails
- GIVEN a strategy config with `"version": 2`
- WHEN validated
- THEN the validation error is still raised (version must be 1)
