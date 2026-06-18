# Strategy Backtesting Specification

## Purpose

Backtest engine using VectorBT + Yahoo Finance, cached by config hash (SHA-256), returning equity curve + metrics. NEW domain — full spec.

## Requirements

### Requirement: BacktestEngine Interface

| Method | Signature | Behavior |
|--------|-----------|----------|
| `__init__` | `(self, config: dict)` | Store config, compute `config_hash` (SHA-256 of sorted JSON) |
| `run` | `() -> dict` | Fetch yfinance data, run VectorBT, return results |
| `config_hash` | `property -> str` | SHA-256 hex digest |

**Result dict:**

| Field | Type | Description |
|-------|------|-------------|
| `total_return_pct` | float | Total return % |
| `sharpe_ratio` | float | Annualized Sharpe |
| `win_rate` | float | Win % (0-100) |
| `max_drawdown_pct` | float | Max DD % (negative) |
| `total_trades` | int | Trade count |
| `equity_curve` | list | `[{date, equity}, ...]` |
| `trade_log` | list | `[{entry_date, exit_date, pnl_pct}]` |
| `error` | str\|null | Error msg or null |

#### Scenario: Successful backtest returns full result

- GIVEN config with symbols `["SPY"]`, timeframe `1D`, entry `RSI > 70`
- WHEN `run()` is called
- THEN all fields SHALL be populated, `total_trades >= 0`, `equity_curve` non-empty

#### Scenario: Zero trades result

- GIVEN config with empty `entry_rules`
- WHEN `run()` is called
- THEN `total_trades = 0`, `total_return_pct = 0.0`, equity_curve SHALL be flat

### Requirement: Yahoo Finance Data Source

Data SHALL be fetched via `yfinance` for each symbol.

| Timeframe | yfinance Interval | Data period |
|-----------|------------------|-------------|
| `1min` | `1m` | Last 7d |
| `5min` | `5m` | Last 60d |
| `15min` | `15m` | Last 60d |
| `1H` | `60m` | Last 730d |
| `1D` | `1d` | Last 5y |

#### Scenario: Data fetched successfully

- GIVEN config with `symbols: ["SPY"]`, `timeframe: "1D"`
- WHEN data is fetched
- THEN returned DataFrame SHALL have columns `open, high, low, close, volume` with DatetimeIndex

#### Scenario: Invalid ticker returns error

- GIVEN config with `symbols: ["BADTKR"]`
- WHEN data is fetched
- THEN result SHALL contain `"error": "No data for BADTKR"`
- AND no VectorBT run SHALL execute

### Requirement: Cached by Config Hash

Results SHALL be cached via `@st.cache_data` keyed by `config_hash`. Same hash = cached result, no re-fetch.

#### Scenario: Cache hit skips API call

- GIVEN backtest run for hash `abc123`
- WHEN `run()` called again with identical config
- THEN identical result SHALL return
- AND no yfinance API call SHALL be made

#### Scenario: Parameter change = cache miss

- GIVEN cached result for SMA(20)
- WHEN user changes to SMA(50) (new hash)
- THEN fresh backtest SHALL run and new result cached

### Requirement: Metrics Display

Center column SHALL show Plotly equity curve + metrics table.

| Metric | Format | Color |
|--------|--------|-------|
| Total Return | `+12.34%` | Green / Red |
| Sharpe | `1.23` | Default |
| Win Rate | `64.3%` | Default |
| Max DD | `-12.34%` | Always red |
| Trades | `42` | Default |

#### Scenario: Positive return shown in green

- GIVEN `total_return_pct = 12.34`
- WHEN metrics render
- THEN cell SHALL show `+12.34%` in green

#### Scenario: Zero trades shows "No signals generated"

- GIVEN backtest result with 0 trades
- WHEN equity curve renders
- THEN chart SHALL show flat line with annotation "No signals generated"
