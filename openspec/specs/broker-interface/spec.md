# Broker Interface Specification

## Purpose

Abstract broker interface (`BaseBroker`) that allows operating with multiple brokers (Alpaca for stocks/ETFs, Binance Testnet for crypto) without modifying the Orchestrator or Scanner when adding new brokers.

## Requirements

### REQ-BROKER-BASE — BaseBroker abstract interface

`BaseBroker` MUST be an abstract base class (ABC) with exactly 7 abstract methods:

| Method | Returns | Description |
|--------|---------|-------------|
| `get_account_balance()` | `float` | Current account equity in USD |
| `get_bars(symbol, timeframe, limit)` | `pd.DataFrame` | OHLCV bars with columns: timestamp, open, high, low, close, volume |
| `submit_order(symbol, side, qty, order_type)` | `OrderResult` | Place an order; `order_type` defaults to `"market"` |
| `get_open_positions()` | `List[dict]` | Currently open positions |
| `close_position(symbol)` | `bool` | Close an open position |
| `is_market_open(symbol)` | `bool` | Whether the market is open for the given symbol |
| `normalize_symbol(symbol)` | `str` | Convert external symbol format to broker-native format |

`OrderResult` SHALL be a `@dataclass` with fields: `order_id: str`, `symbol: str`, `side: str`, `qty: float`, `price: float`, `status: str`, `broker: str`.

#### Scenario: Alpaca normalize_symbol("SPY")
- GIVEN an AlpacaBroker instance
- WHEN `normalize_symbol("SPY")` is called
- THEN it returns `"SPY"`

#### Scenario: Alpaca normalize_symbol("BTC/USD")
- GIVEN an AlpacaBroker instance
- WHEN `normalize_symbol("BTC/USD")` is called
- THEN it returns `"BTC/USD"`

#### Scenario: Binance normalize_symbol("BTC/USD")
- GIVEN a BinanceBroker instance
- WHEN `normalize_symbol("BTC/USD")` is called
- THEN it returns `"BTCUSDT"`

#### Scenario: Binance normalize_symbol("ETH/USD")
- GIVEN a BinanceBroker instance
- WHEN `normalize_symbol("ETH/USD")` is called
- THEN it returns `"ETHUSDT"`

### REQ-BROKER-ALPACA — AlpacaBroker concreto

`AlpacaBroker(BaseBroker)` MUST refactor all existing `TradingClient` calls into the 7-method interface. SHALL delegate orders to `TradingClient.submit_order(market, day)`. SHALL use `StockHistoricalDataClient` for stocks and `CryptoHistoricalDataClient` for symbols containing `/`. SHALL use the Clock API for stock market hours; crypto SHALL return `True` 24/7. `broker` field SHALL be `"alpaca"`.

#### Scenario: submit_order AAPL
- GIVEN an AlpacaBroker instance
- WHEN `submit_order("AAPL", "buy", 10)` is called
- THEN an `OrderResult` with `status="accepted"` is returned

#### Scenario: get_bars BTC/USD uses crypto client
- GIVEN an AlpacaBroker instance
- WHEN `get_bars("BTC/USD", "1Day", 100)` is called
- THEN `CryptoHistoricalDataClient` is used for the request

#### Scenario: get_bars SPY uses stock client
- GIVEN an AlpacaBroker instance
- WHEN `get_bars("SPY", "1Day", 100)` is called
- THEN `StockHistoricalDataClient` is used for the request

#### Scenario: is_market_open crypto 24/7
- GIVEN an AlpacaBroker instance
- WHEN `is_market_open("BTC/USD")` is called on Saturday at 3 PM ET
- THEN it returns `True`

#### Scenario: is_market_open stocks uses Clock
- GIVEN an AlpacaBroker instance
- WHEN `is_market_open("SPY")` is called on Saturday at 3 PM ET
- THEN it returns `False` (market closed)

### REQ-BROKER-BINANCE — BinanceBroker concreto

`BinanceBroker(BaseBroker)` MUST connect to `testnet.binance.vision` when `BINANCE_TESTNET=true`. SHALL use HMAC-SHA-256 authentication with no passphrase. SHALL use pure `requests` + `hmac` — no SDK dependency. API endpoints:

| Operation | Endpoint | Method |
|-----------|----------|--------|
| Account balance | `/api/v3/account` | GET |
| OHLCV bars | `/api/v3/klines` | GET |
| Submit order | `/api/v3/order` | POST |
| Exchange info | `/api/v3/exchangeInfo` | GET |

`normalize_symbol` MUST strip `/` and convert `USD` to `USDT`. `is_market_open` SHALL always return `True`. Rate limiting SHALL use a `TokenBucket` at 10 req/s. `broker` field SHALL be `"binance"`.

#### Scenario: Testnet URL
- GIVEN `BINANCE_TESTNET=true`
- WHEN a BinanceBroker instance is created
- THEN `base_url` is `https://testnet.binance.vision`

#### Scenario: normalize_symbol ETH/USD
- GIVEN a BinanceBroker instance
- WHEN `normalize_symbol("ETH/USD")` is called
- THEN it returns `"ETHUSDT"`

#### Scenario: get_bars returns DataFrame
- GIVEN a BinanceBroker instance with mocked response
- WHEN `get_bars("BTCUSDT", "1h", 100)` is called
- THEN a `pd.DataFrame` with columns timestamp, open, high, low, close, volume is returned

#### Scenario: submit_order FILLED
- GIVEN a BinanceBroker instance with mocked response
- WHEN `submit_order("BTCUSDT", "buy", 0.001)` is called
- THEN an `OrderResult` with `status="FILLED"` is returned

#### Scenario: is_market_open always true
- GIVEN a BinanceBroker instance
- WHEN `is_market_open("BTCUSDT")` is called at any time
- THEN it returns `True`
