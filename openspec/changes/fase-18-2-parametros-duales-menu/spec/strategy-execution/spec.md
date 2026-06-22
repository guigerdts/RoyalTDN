# Strategy Execution Specification

## Purpose

Defines how trading strategies generate signals with market-type-aware dual parameter profiles (crypto vs stocks) and a category system for visual grouping.

## Requirements

### Requirement: BaseStrategy — Optional symbol parameter

`BaseStrategy.generate_signal()` MUST accept an optional `symbol` parameter: `generate_signal(self, data: pd.DataFrame, symbol: Optional[str] = None)`.

When `symbol` is provided, the concrete strategy SHALL use `is_crypto_symbol(symbol)` from `scanner.universe` to select the crypto or stocks parameter profile. When `symbol` is None, the strategy SHALL fall back to the stocks profile for backward compatibility.

#### Scenario: Crypto symbol selects crypto profile
- GIVEN a strategy with dual param profiles
- WHEN `generate_signal(data, symbol="BTC/USD")` is called
- THEN the crypto profile parameters are used for signal computation

#### Scenario: Stock symbol selects stock profile
- GIVEN a strategy with dual param profiles
- WHEN `generate_signal(data, symbol="SPY")` is called
- THEN the stock profile parameters are used for signal computation

#### Scenario: No symbol defaults to stocks
- GIVEN a strategy with dual param profiles
- WHEN `generate_signal(data)` is called without symbol
- THEN the stock profile is used (backward compatibility)

#### Scenario: Binance format crypto symbols detected
- GIVEN a strategy with dual param profiles
- WHEN `generate_signal(data, symbol="BTCUSDT")` is called
- THEN `is_crypto_symbol("BTCUSDT")` returns True and crypto profile is used

### Requirement: BaseStrategy — Category attribute

`BaseStrategy` MUST define a `category` property (str) defaulting to `"swing"`. Concrete strategies MAY override the default. The category SHALL be serializable via `get_parameters()`.

#### Scenario: Default category
- GIVEN a new strategy inheriting from BaseStrategy
- WHEN `strategy.category` is accessed
- THEN it returns `"swing"`

#### Scenario: Category in get_parameters
- GIVEN a strategy instance
- WHEN `get_parameters()` is called
- THEN the returned dict includes a `"category"` key with the strategy's category

### Requirement: SMA Crossover dual params

`SMAStrategy` MUST store two parameter profiles:
- Crypto: `sma_fast=7, sma_slow=25, timeframe="1d"`
- Stocks: `sma_fast=5, sma_slow=20, timeframe="1d"`

Selection SHALL happen per `generate_signal()` call via `symbol` parameter.

#### Scenario: Crypto SMA params
- GIVEN an SMAStrategy instance
- WHEN `generate_signal(data, symbol="ETH/USD")` is called
- THEN internal `self.sma_fast` is 7 AND `self.sma_slow` is 25

#### Scenario: Stock SMA params
- GIVEN an SMAStrategy instance
- WHEN `generate_signal(data, symbol="SPY")` is called
- THEN internal `self.sma_fast` is 5 AND `self.sma_slow` is 20

### Requirement: Bollinger RSI dual params

`BollingerRSIStrategy` MUST store two parameter profiles:
- Crypto: `bb_period=15, bb_std=2.5, rsi_period=10, rsi_oversold=25, rsi_overbought=75, max_bars_hold=20, timeframe="5min"`
- Stocks: `bb_period=20, bb_std=2.0, rsi_period=14, rsi_oversold=30, rsi_overbought=70, max_bars_hold=30, timeframe="15min"`

#### Scenario: Crypto Bollinger RSI params
- GIVEN a BollingerRSIStrategy instance
- WHEN `generate_signal(data, symbol="BTC/USD")` is called
- THEN `bb_period=15, bb_std=2.5, rsi_oversold=25, rsi_overbought=75` apply

#### Scenario: Stock Bollinger RSI params
- GIVEN a BollingerRSIStrategy instance
- WHEN `generate_signal(data, symbol="SPY")` is called
- THEN `bb_period=20, bb_std=2.0, rsi_oversold=30, rsi_overbought=70` apply

### Requirement: Momentum ATR dual params

`MomentumATRStrategy` MUST store two parameter profiles:
- Crypto: `momentum_period=15, atr_period=14, atr_max_pct=4.0, exit_period=3, timeframe="1d"`
- Stocks: `momentum_period=20, atr_period=20, atr_max_pct=2.0, exit_period=5, timeframe="1d"`

#### Scenario: Crypto Momentum ATR params
- GIVEN a MomentumATRStrategy instance
- WHEN `generate_signal(data, symbol="BTC/USD")` is called
- THEN `momentum_period=15, atr_max_pct=4.0, exit_period=3` apply

#### Scenario: Stock Momentum ATR params
- GIVEN a MomentumATRStrategy instance
- WHEN `generate_signal(data, symbol="SPY")` is called
- THEN `momentum_period=20, atr_max_pct=2.0, exit_period=5` apply

### Requirement: Scaffold category values

The 3 existing strategies MUST return `category="swing"` from `get_parameters()`. No other categories exist yet — `"scalping"` and `"intraday"` are placeholders for FASE 18.3.

#### Scenario: All 3 strategies return swing
- GIVEN sma_crossover, bollinger_rsi, and momentum_atr instances
- WHEN `get_parameters()["category"]` is read
- THEN all three return `"swing"`

### Requirement: Scanner passes symbol to generate_signal

The scanner `scan()` loop MUST pass the current `symbol` to `strategy.generate_signal(data, symbol=symbol)`. Existing callers without symbol (legacy orchestrator loop, tests) SHALL NOT break.

#### Scenario: Scanner passes symbol
- GIVEN the scanner is iterating symbols
- WHEN calling `generate_signal` for a symbol
- THEN the symbol is passed as a keyword argument

#### Scenario: Legacy callers unaffected
- GIVEN code calling `strategy.generate_signal(data)` without symbol
- THEN the call succeeds and uses stock defaults

## Out of Scope

- Timeframe mismatch between scanner (daily bars) and intraday crypto params — handled in FASE 18.3
- User strategies (DynamicStrategy) — not modified
- FactorRotation strategy — not modified

## Test Considerations

- Test each strategy with crypto symbol → verify crypto params used
- Test each strategy with stock symbol → verify stock params used
- Test each strategy without symbol → verify stock defaults
- Test backward compat: all existing `generate_signal(data)` calls still work
- Test `category` property on all 3 strategies returns "swing"
- Test scanner loop forwards `symbol` arg correctly
