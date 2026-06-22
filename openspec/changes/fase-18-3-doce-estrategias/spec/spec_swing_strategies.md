# Swing Strategies Specification

## Purpose

Three swing strategies targeting 1d timeframe (both crypto and stocks) with `category="swing"`. Each implements `BaseStrategy` with dual `_PROFILES`, `generate_signal(data, symbol=None)` with local variable resolution, `get_parameters(symbol=None)` with three-way branch, and `validate()`.

## ADDED Requirements

### Requirement: Swing Trend Following

The system MUST implement `SwingTrendFollowingStrategy` with params: crypto `fast_ema=7, slow_ema=25, trend_strength=25`, stocks `fast_ema=10, slow_ema=30, trend_strength=20`. Signal: BUY when EMA(fast) > EMA(slow) and ADX >= trend_strength. SELL when EMA(fast) < EMA(slow) and ADX >= trend_strength. Timeframe: `"1d"` for both profiles.

#### Scenario: Multi-timeframe uptrend
- GIVEN 1d data with EMA(7) > EMA(25) and ADX(14)=32 for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"` with both EMAs and ADX in metadata

#### Scenario: Trend direction change
- GIVEN 1d data where EMA(7) just crossed below EMA(25) with ADX=28 for AAPL
- WHEN `generate_signal(data, symbol="AAPL")` is called
- THEN it returns `action: "SELL"`

### Requirement: Swing Reversion

The system MUST implement `SwingReversionStrategy` with params: crypto `lookback_period=20, z_score_threshold=2.0`, stocks `lookback_period=30, z_score_threshold=1.5`. Signal: BUY when z-score < -threshold (oversold). SELL when z-score > +threshold (overbought). Timeframe: `"1d"` for both profiles.

#### Scenario: Oversold mean reversion BUY
- GIVEN 1d data where z-score of close(20) = -2.5 for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"` with z-score in metadata

#### Scenario: Overbought mean reversion SELL
- GIVEN 1d data where z-score of close(20) = 2.0 for AAPL
- WHEN `generate_signal(data, symbol="AAPL")` is called
- THEN it returns `action: "SELL"`

### Requirement: Swing Breakout

The system MUST implement `SwingBreakoutStrategy` with params: crypto `breakout_period=20, volume_confirm=True`, stocks `breakout_period=30, volume_confirm=True`. Signal: BUY when close > max(high[-breakout_period:]) and (if volume_confirm) volume > avg_volume[-breakout_period:]. SELL when close < min(low[-breakout_period:]) with volume confirmation. Timeframe: `"1d"` for both profiles.

#### Scenario: Multi-day breakout BUY
- GIVEN 1d data where close exceeds 20-period high with volume above average for BTC/USDT
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns `action: "BUY"` with breakout level and volume ratio in metadata

#### Scenario: Breakout without volume confirmation
- GIVEN 1d data where close exceeds 20-period high but volume is below average
- WHEN `generate_signal(data, symbol="BTC/USDT")` is called
- THEN it returns None (volume_confirm=True requires both conditions)

## Common Requirements

All swing strategies MUST:
- Set `self._category = "swing"` in `__init__`
- Return `"swing"` from the `category` property
- Include `"category": "swing"` in `get_parameters(symbol=None)` output

## Out of Scope

- Multi-timeframe confirmation beyond the strategy's own timeframe
- Portfolio-level position sizing (handled by Orchestrator risk pipeline)

## Test Considerations

- Test each strategy with synthetic 1d OHLCV data spanning 60+ periods
- Test `generate_signal(data, symbol="BTC/USDT")` uses crypto profile
- Test `generate_signal(data, symbol="AAPL")` uses stocks profile
- Test `validate()` returns False with zero or negative parameters
- Test `name` property uniqueness — no overlap with existing swing strategies (sma_crossover, bollinger_rsi, momentum_atr)
