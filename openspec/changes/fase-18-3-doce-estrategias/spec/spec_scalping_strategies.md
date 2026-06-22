# Scalping Strategies Specification

## Purpose

Five scalping strategies targeting 1min (crypto) / 3-5min (stocks) timeframes with `category="scalping"`. Each implements `BaseStrategy` with dual `_PROFILES`, `generate_signal(data, symbol=None)` with local variable resolution, `get_parameters(symbol=None)` with three-way branch, and `validate()`.

## ADDED Requirements

### Requirement: Scalping Momentum

The system MUST implement `ScalpingMomentumStrategy` with params: crypto `momentum_period=5, min_momentum_pct=1.0`, stocks `momentum_period=10, min_momentum_pct=0.5`. Signal: BUY when close return over `momentum_period` >= `min_momentum_pct`. SELL when return <= -`min_momentum_pct`. Timeframe: crypto `"1min"`, stocks `"3min"`.

#### Scenario: Fast momentum BUY detected
- GIVEN 1min candle data with recent 6% gain over 5 periods for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"` with metadata containing `momentum_return`

#### Scenario: Stock momentum below threshold
- GIVEN 3min candle data with only 0.2% return over 10 periods for AAPL
- WHEN `generate_signal(data, symbol="AAPL")` is called
- THEN it returns None

### Requirement: Scalping Breakout

The system MUST implement `ScalpingBreakoutStrategy` with params: crypto `breakout_period=10, breakout_multiplier=2.0`, stocks `breakout_period=20, breakout_multiplier=1.5`. Signal: BUY when close > `max(high[-breakout_period:])` * 1.0 and range > ATR * `breakout_multiplier`. Timeframe: crypto `"1min"`, stocks `"5min"`.

#### Scenario: Crypto range breakout
- GIVEN 1min data where price breaks above 10-period high with 2.5x ATR range
- WHEN `generate_signal(data, symbol="ETH/USDT")` is called
- THEN it returns `action: "BUY"` with `price`

#### Scenario: No breakout in range
- GIVEN 1min data where price stays within 10-period range
- WHEN `generate_signal(data, symbol="ETH/USDT")` is called
- THEN it returns None

### Requirement: Scalping Reversion

The system MUST implement `ScalpingReversionStrategy` with params: crypto `reversion_period=10, deviation_threshold=2.0`, stocks `reversion_period=14, deviation_threshold=1.5`. Signal: BUY when close < SMA - dev * STD. SELL when close > SMA + dev * STD. Timeframe: crypto `"1min"`, stocks `"3min"`.

#### Scenario: Oversold mean reversion BUY
- GIVEN 1min data where close is 2.5 STD below SMA(10) for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"`

#### Scenario: Insufficient data for calculation
- GIVEN 1min data with fewer than `reversion_period + 1` rows
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns None

### Requirement: Scalping Order Flow

The system MUST implement `ScalpingOrderFlowStrategy` with params: crypto `volume_threshold=1_000_000, imbalance_ratio=2.0`, stocks `volume_threshold=500_000, imbalance_ratio=1.5`. Signal: BUY when tick volume > threshold and buy/sell ratio > imbalance_ratio. Timeframe: crypto `"1min"`, stocks `"5min"`.

#### Scenario: Volume imbalance BUY
- GIVEN 1min data with buy volume 3x sell volume above 1M total
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"`

#### Scenario: Volume below threshold
- GIVEN 1min data with total volume below 1M threshold
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns None

### Requirement: Scalping Spread

The system MUST implement `ScalpingSpreadStrategy` with params: crypto `spread_period=10, spread_threshold=2.0`, stocks `spread_period=20, spread_threshold=1.5`. Signal: BUY when current spread > SMA(spread, period) * threshold (widening). SELL when current spread < SMA(spread, period) / threshold (compression). Timeframe: crypto `"1min"`, stocks `"5min"`.

#### Scenario: Spread widening detected
- GIVEN 1min data where current spread is 2.5x the 10-period average
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"`

#### Scenario: Spread compression detected
- GIVEN 1min data where current spread is 0.4x the 10-period average
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "SELL"`

## Common Requirements

All scalping strategies MUST:
- Set `self._category = "scalping"` in `__init__`
- Return `"scalping"` from the `category` property
- Include `"category": "scalping"` in `get_parameters(symbol=None)` output

## Out of Scope

- Tick-level order book data (strategies use OHLCV + volume only)
- Latency optimization for sub-second execution

## Test Considerations

- Test each strategy with synthetic OHLCV data for both crypto and stock profiles
- Test `get_parameters(symbol=None)` returns both `crypto_*` and `stocks_*` prefixed keys
- Test `validate()` returns True with defaults, False with invalid params
- Test `name` property returns unique string matching the filename convention
