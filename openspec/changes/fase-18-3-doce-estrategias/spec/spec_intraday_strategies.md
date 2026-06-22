# Intraday Strategies Specification

## Purpose

Five intraday strategies targeting 15min (crypto) / 1H (stocks) timeframes with `category="intraday"`. Each implements `BaseStrategy` with dual `_PROFILES`, `generate_signal(data, symbol=None)` with local variable resolution, `get_parameters(symbol=None)` with three-way branch, and `validate()`.

## ADDED Requirements

### Requirement: Intraday Trend

The system MUST implement `IntradayTrendStrategy` with params: crypto `trend_period=14, adx_threshold=25`, stocks `trend_period=20, adx_threshold=20`. Signal: BUY when ADX > threshold and EMA(fast) > EMA(slow). SELL when ADX > threshold and EMA(fast) < EMA(slow). Timeframe: crypto `"15min"`, stocks `"1H"`.

#### Scenario: Strong uptrend detected
- GIVEN 15min data with ADX(14)=35 and EMA(7) > EMA(14) for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"` with ADX value in metadata

#### Scenario: ADX below threshold
- GIVEN 15min data with ADX(14)=18 for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns None (no trend strength)

### Requirement: Intraday VWAP

The system MUST implement `IntradayVWAPStrategy` with params: crypto `vwap_multiplier=2.0, vwap_period=14`, stocks `vwap_multiplier=1.5, vwap_period=20`. Signal: BUY when close < VWAP - dev*STD. SELL when close > VWAP + dev*STD. Timeframe: crypto `"15min"`, stocks `"1H"`.

#### Scenario: VWAP mean reversion BUY
- GIVEN 15min data where close is 2.5 STD below VWAP for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"`

#### Scenario: Close near VWAP
- GIVEN 15min data where close is within 0.5 STD of VWAP for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns None

### Requirement: Intraday Volume Breakout

The system MUST implement `IntradayVolumeBreakoutStrategy` with params: crypto `volume_surge_pct=200, breakout_period=10`, stocks `volume_surge_pct=150, breakout_period=20`. Signal: BUY when volume > SMA(volume) * (surge/100) AND price breaks recent range high. Timeframe: crypto `"15min"`, stocks `"1H"`.

#### Scenario: Volume-confirmed breakout BUY
- GIVEN 15min data with volume 300% of average and price above 10-period high for ETH/USDT
- WHEN `generate_signal(data, symbol="ETH/USDT")` is called
- THEN it returns `action: "BUY"` with volume surge ratio in metadata

#### Scenario: Price breakout without volume confirmation
- GIVEN 15min data with price above range high but volume only 120% of average
- WHEN `generate_signal(data, symbol="ETH/USDT")` is called
- THEN it returns None

### Requirement: Intraday Support Resistance

The system MUST implement `IntradaySupportResistanceStrategy` with params: crypto `sr_period=20, bounce_pct=0.5`, stocks `sr_period=30, bounce_pct=0.3`. Signal: BUY when close near support level and bouncing up. SELL when close near resistance and bouncing down. Timeframe: crypto `"15min"`, stocks `"1H"`.

#### Scenario: Support bounce BUY
- GIVEN 15min data where price touched SMA(20) and bounced 0.8% for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"` with bounce percentage in metadata

#### Scenario: No clear S/R zone
- GIVEN 15min data where price is mid-range between support and resistance
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns None

### Requirement: Intraday MACD Divergence

The system MUST implement `IntradayMACDDivergenceStrategy` with params: crypto `fast_period=12, slow_period=26, signal_period=9`, stocks `fast_period=12, slow_period=26, signal_period=9`. Signal: BUY on bullish divergence (price lower low, MACD higher low). SELL on bearish divergence (price higher high, MACD lower high). Timeframe: crypto `"15min"`, stocks `"1H"`.

#### Scenario: Bullish MACD divergence
- GIVEN 15min data where price made a lower low but MACD made a higher low for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"`

#### Scenario: Bearish MACD divergence
- GIVEN 15min data where price made a higher high but MACD made a lower high for AAPL
- WHEN `generate_signal(data, symbol="AAPL")` is called
- THEN it returns `action: "SELL"`

## Common Requirements

All intraday strategies MUST:
- Set `self._category = "intraday"` in `__init__`
- Return `"intraday"` from the `category` property
- Include `"category": "intraday"` in `get_parameters(symbol=None)` output

## Out of Scope

- Multi-timeframe confirmation (each strategy uses a single timeframe from its profile)
- Real-time MACD divergence recalculation on each tick

## Test Considerations

- Test each strategy with synthetic OHLCV data containing known patterns
- Test `get_parameters(symbol=None)` returns both profiles with prefixed keys
- Test `validate()` returns False when any numeric parameter is <= 0
- Test category is always `"intraday"` regardless of profile
