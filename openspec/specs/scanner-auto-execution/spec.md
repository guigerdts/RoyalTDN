# Scanner Auto-Execution Specification

## Purpose

Automatic execution of scanner signals with risk management, multi-broker routing, and portfolio position management.

## Requirements

### PPM Multi-Broker

The `PortfolioPositionManager` MUST support positions from multiple brokers. The `Position` dataclass SHALL include a `broker: str = "alpaca"` field. Internal composite keys SHALL use `f"{broker}:{symbol}"` format to prevent symbol collisions across brokers. `open_position()` SHALL accept an optional `broker` parameter (defaults to `"alpaca"`). A `get_positions_by_broker(broker)` method SHALL filter and return positions for a specific broker. `get_symbol_exposure()` SHALL accept an optional `broker` filter parameter. `get_total_exposure()` SHALL sum exposure across all brokers.

#### Scenario: Two brokers same symbol
- GIVEN an open position `Alpaca:AAPL` and `Binance:BTCUSDT`
- WHEN `get_all_positions()` is called
- THEN both positions are returned as separate entries

#### Scenario: Combined equity
- GIVEN `equity=200000`, positions `1800` (Alpaca) + `32500` (Binance)
- WHEN `get_total_exposure()` is called
- THEN total exposure percentage is 17.15%

#### Scenario: Filter by broker
- GIVEN positions in both Alpaca and Binance
- WHEN `get_symbol_exposure("AAPL", broker="alpaca")` is called
- THEN only Alpaca AAPL exposure is calculated

### REQ-EXEC-BROKER-ROUTING — Per-symbol broker routing

The Orchestrator MUST route execution per symbol using `self.brokers[asset_type]`. Symbols containing `/` SHALL route to the crypto broker (`BinanceBroker`). Symbols without `/` SHALL route to the stocks broker (`AlpacaBroker`). The `_get_broker_for_symbol(symbol)` method SHALL implement this routing. Fallback SHALL use the stocks broker when no crypto broker is configured.

#### Scenario: BTC/USD routes to Binance
- GIVEN `brokers = {"stocks": AlpacaBroker, "crypto": BinanceBroker}`
- WHEN `_get_broker_for_symbol("BTC/USD")` is called
- THEN `BinanceBroker` is returned for data and order execution

#### Scenario: SPY routes to Alpaca
- GIVEN `brokers = {"stocks": AlpacaBroker, "crypto": BinanceBroker}`
- WHEN `_get_broker_for_symbol("SPY")` is called
- THEN `AlpacaBroker` is returned for data and order execution

#### Scenario: Fallback when no crypto broker
- GIVEN `brokers = {"stocks": AlpacaBroker}` (no crypto key)
- WHEN `_get_broker_for_symbol("BTC/USD")` is called
- THEN `AlpacaBroker` is returned as fallback

### REQ-RISK-MULTI-BROKER — Multi-broker risk management

`RiskManager.check_portfolio_risk()` MUST accept a `brokers: Dict[str, BaseBroker]` parameter and consolidate equity across ALL brokers for combined drawdown calculation. `close_all_positions()` (kill switch) SHALL iterate ALL brokers and call `close_position()` on each. `get_atr()` SHALL accept a `broker: BaseBroker` parameter and use `broker.get_bars()` for ATR calculation. When `get_bars()` returns insufficient data for ATR calculation, SHALL return `0.0` gracefully.

#### Scenario: Combined equity
- GIVEN `Alpaca equity = 100000`, `1.5 BTC @ 65000 USD each = 97500`
- WHEN `check_portfolio_risk()` computes total equity
- THEN total is `197500`

#### Scenario: Kill switch all brokers
- GIVEN both Alpaca and Binance have open positions
- WHEN `close_all_positions()` is called
- THEN both brokers' `close_position()` are called

#### Scenario: get_atr with broker param
- GIVEN a broker instance with bar data
- WHEN `get_atr("BTC/USD", 14, broker=crypto_broker)` is called
- THEN ATR is calculated using `crypto_broker.get_bars()` data

#### Scenario: get_atr insufficient data
- GIVEN a broker instance with insufficient bar data
- WHEN `get_atr("BTC/USD", 14, broker=crypto_broker)` is called
- THEN `0.0` is returned gracefully

### REQ-LEGACY-KILL-GLOBAL — Legacy loop backward compatibility

The legacy `close_all_positions` loop SHALL include Binance positions. When `close_position()` is called without a broker context, it SHALL search across all brokers. `_execute_signal()` SHALL delegate `close_position()` calls through the correct broker.

#### Scenario: Close all positions
- GIVEN open positions `SPY` (Alpaca) and `BTC/USD` (Binance)
- WHEN `close_all_positions()` is called
- THEN both `SPY` and `BTC/USD` positions are closed

#### Scenario: Legacy loop uses stocks broker
- GIVEN the legacy execution loop
- WHEN a stock signal triggers
- THEN the stocks broker is used for order execution

#### Scenario: Legacy close_position uses stocks broker
- GIVEN the legacy loop
- WHEN `close_position("SPY")` is called
- THEN the stocks broker's `close_position()` is used

### REQ-PPM-BACKWARD-COMPAT — PPM backward compatibility

`open_position()` SHALL default `broker` to `"alpaca"` when not provided. `close_position()` without a `broker` parameter SHALL search all composite keys for the symbol. `get_position()` without a `broker` parameter SHALL search all composite keys.

#### Scenario: open_position defaults to alpaca
- GIVEN `open_position("AAPL", "buy", 10, 150.0)` is called without broker
- THEN broker defaults to `"alpaca"`

#### Scenario: close_position without broker
- GIVEN positions in multiple brokers
- WHEN `close_position("BTC/USD")` is called without broker
- THEN all keys are searched and the matching position is closed

#### Scenario: get_position without broker
- GIVEN positions in multiple brokers
- WHEN `get_position("BTC/USD")` is called without broker
- THEN all keys are searched and the matching position is returned

### REQ-ENV-VARS — Environment variables

The following environment variables MUST be supported:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BINANCE_API_KEY` | No | — | Binance API key for REST authentication |
| `BINANCE_SECRET_KEY` | No | — | Binance secret key for HMAC signing |
| `BINANCE_TESTNET` | No | `false` | When `true`, connects to testnet.binance.vision |
| `BROKER_CRYPTO` | No | `binance` | Crypto broker backend identifier |

#### Scenario: Binance env vars loaded
- GIVEN `BINANCE_API_KEY` and `BINANCE_SECRET_KEY` are set
- WHEN `main.py` initializes
- THEN a `BinanceBroker` instance is created and added to the brokers dict

#### Scenario: No crypto configured
- GIVEN neither `BINANCE_API_KEY` nor `BINANCE_SECRET_KEY` is set
- WHEN `main.py` initializes
- THEN no crypto broker is created; the system operates in stocks-only mode
