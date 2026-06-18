# Dynamic Strategy Engine Specification

## Purpose

Define interfaces for 16 indicators (15 pandas-ta + 1 custom Smart Money Flow Cloud), recursive rule evaluation (max depth 2), and DynamicStrategy (BaseStrategy subclass). NEW domain — full spec.

## Requirements

### Requirement: Indicators — 16 Functions

`strategy/indicators.py` SHALL expose one function per indicator. Each SHALL accept `data: pd.DataFrame` and `source` (enum: `open|high|low|close|volume|hl2|hlc3|ohlc4`) defaulting to `close`.

| # | Function | Parameters (defaults) | Returns |
|---|----------|----------------------|---------|
| 1 | `SMA` | `period=20` | Series |
| 2 | `EMA` | `period=20` | Series |
| 3 | `RSI` | `period=14` | Series |
| 4 | `MACD` | `fast=12, slow=26, signal=9` | DataFrame: MACD, MACD_signal, MACD_hist |
| 5 | `BollingerBands` | `period=20, std=2` | DataFrame: BB_upper, BB_middle, BB_lower |
| 6 | `ATR` | `period=14` | Series |
| 7 | `Volume` | (none) | Series |
| 8 | `Ichimoku` | `tenkan=9, kijun=26, senkou=52` | DataFrame: tenkan, kijun, senkou_a, senkou_b, chikou |
| 9 | `SuperTrend` | `period=10, multiplier=3.0` | DataFrame: supertrend, supertrend_direction |
| 10 | `VWAP` | `anchor=D` | Series |
| 11 | `ZScore` | `period=21, entry_threshold=2.0, exit_threshold=0.5` | Series |
| 12 | `ADX` | `period=14` | Series |
| 13 | `OBV` | (none) | Series |
| 14 | `Stochastic` | `k_period=14, d_period=3` | DataFrame: Stoch_k, Stoch_d |
| 15 | `ParabolicSAR` | `af=0.02, max_af=0.2` | Series |
| 16 | `SmartMoneyFlowCloud` | `trend_length=34, trend_engine="EMA", alma_offset=0.85, alma_sigma=6.0, trend_smoothing=3, flow_window=24, flow_smoothing=5, flow_power=1.2, atr_length=14, min_mult=0.9, max_mult=2.2` | DataFrame: basis, upper_band, lower_band, regime, flow_strength, switch_up, switch_down, retest_bull, retest_bear |

**Constraint:** All integer period params SHALL clamp to >= 2. `PSAR.af > 0, max_af > af`. `SmartMoneyFlowCloud.trend_engine` SHALL be one of `EMA|ALMA`. `flow_power >= 0.5`. `min_mult < max_mult`.

#### Scenario: All indicators compute from valid OHLCV

- GIVEN a DataFrame with 200 bars of OHLCV data
- WHEN each indicator is called with defaults
- THEN it SHALL return correct type (Series or DataFrame) with same length as input
- AND no function SHALL raise

#### Scenario: Insufficient data returns NaN

- GIVEN a DataFrame with 10 bars
- WHEN `Ichimoku(data)` is called (requires 52 bars)
- THEN output SHALL be all NaN until row 52
- AND no exception SHALL raise

#### Scenario: Period=0 clamped to 2

- GIVEN `SMA(data, period=0)`
- WHEN called
- THEN it SHALL compute with `period=2` silently

#### Scenario: Smart Money Flow Cloud computes all fields

- GIVEN a DataFrame with 100 bars of OHLCV data
- WHEN `SmartMoneyFlowCloud(data)` is called with defaults
- THEN it SHALL return a DataFrame with columns: basis, upper_band, lower_band, regime, flow_strength, switch_up, switch_down, retest_bull, retest_bear
- AND no function SHALL raise

#### Scenario: SMF EMA vs ALMA engine

- GIVEN `trend_engine="ALMA"` with `alma_offset=0.85, alma_sigma=6`
- WHEN `SmartMoneyFlowCloud(data, trend_engine="ALMA")` is called
- THEN basis SHALL use ALMA instead of EMA

### Requirement: Rule Engine — Recursive Tree Evaluation

`rule_engine.py` SHALL parse JSON rule trees and evaluate against computed indicators. Max nesting: 2 AND/OR levels.

**Operators by category:**

| Category | Operators |
|----------|-----------|
| Comparison | `gt`, `gte`, `lt`, `lte`, `eq`, `neq` |
| Crossover | `crosses_above`, `crosses_below` |
| Band | `inside_band`, `breaks_above_band`, `breaks_below_band` |
| Overbought/Oversold | `is_overbought`, `is_oversold`, `exits_overbought`, `exits_oversold` |
| Ichimoku cloud | `price_above_cloud`, `price_below_cloud`, `price_in_cloud` |
| Trend strength | `trend_strong`, `trend_weak` |
| Ichimoku lines | `tenkan_crosses_kijun`, `price_crosses_chikou` |
| SMF Signal | `smf_buy_signal`, `smf_sell_signal`, `smf_bullish_retest`, `smf_bearish_retest` |
| SMF Band | `price_above_smf_upper`, `price_below_smf_lower`, `smf_crosses_above_upper`, `smf_crosses_below_lower` |
| SMF Basis | `price_above_smf_basis`, `price_below_smf_basis` |
| SMF Flow | `smf_flow_strength_gt`, `smf_flow_strength_lt` |
| SMF Regime | `smf_regime_bullish`, `smf_regime_bearish` |

#### Scenario: Simple comparison evaluates

- GIVEN tree `{"operator":"AND","conditions":[{"indicator":"RSI","params":{"period":14},"operator":"gt","value":70}]}` and data where RSI(14) last = 75
- WHEN `evaluate(tree, data)` is called
- THEN it SHALL return `True`

#### Scenario: Depth=3 raises ValueError

- GIVEN a tree with 3 nested AND/OR levels
- WHEN `evaluate(tree, data)` is called
- THEN it SHALL raise `ValueError("Max nesting depth (2) exceeded")`

#### Scenario: Empty conditions → False

- GIVEN tree with `"conditions": []`
- WHEN evaluated
- THEN it SHALL return `False`

### Requirement: DynamicStrategy — BaseStrategy Subclass

```python
class DynamicStrategy(BaseStrategy):
    def __init__(self, config: dict)
    @classmethod def from_file(cls, path: str) -> DynamicStrategy
    def generate_signal(self, data: pd.DataFrame) -> dict | None
    def get_parameters(self) -> dict
    def validate(self) -> bool
    @property def name(self) -> str  # → f"dynamic_{config['name']}"
```

#### Scenario: BUY when entry rules match

- GIVEN config with entry `RSI > 70` and data where RSI last = 75
- WHEN `generate_signal(data)` is called
- THEN return `{"action": "BUY", "price": float, "metadata": dict}`

#### Scenario: None when no rules match

- GIVEN entry `RSI > 70` and current RSI = 50
- WHEN called
- THEN return `None`

#### Scenario: Unknown indicator → validate=False

- GIVEN config with `"indicator": "BAD_INDICATOR"`
- WHEN `validate()` is called
- THEN return `False`

#### Scenario: SMF buy signal triggers entry

- GIVEN config with entry rule `smf_buy_signal == true` and data where SMF.switch_up last = True
- WHEN `generate_signal(data)` is called
- THEN return `{"action": "BUY", ...}`

#### Scenario: SMF regime bearish blocks buy

- GIVEN config with entry rule requiring `smf_regime_bullish` but regime = -1
- WHEN `generate_signal(data)` is called
- THEN return `None`
