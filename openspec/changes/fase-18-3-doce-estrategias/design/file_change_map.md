# File Change Map — FASE 18.3

## PR Boundaries (force-chained, 400-line budget)

```
PR #1 ← PR #2 ← PR #3   (feature-branch-chain, each targets previous)
```

### PR 1 (~350 lines): Orchestrator fix + 5 scalping strategies

| File | Action | Description | Est. lines |
|------|--------|-------------|-----------|
| `src/royaltdn/orchestrator.py` | **Modify** | `_build_strategies_list()` — add `"category"` at 3 insertion points (scanner loop at ~L482, fallback entry at ~L493, user strategies loop at ~L509) | +3 |
| `src/royaltdn/strategy/scalping_momentum.py` | **Create** | `ScalpingMomentumStrategy` — return threshold, TF 1min/3min | ~65 |
| `src/royaltdn/strategy/scalping_breakout.py` | **Create** | `ScalpingBreakoutStrategy` — ATR range breakout, TF 1min/5min | ~70 |
| `src/royaltdn/strategy/scalping_reversion.py` | **Create** | `ScalpingReversionStrategy` — SMA ± STD bands, TF 1min/3min | ~70 |
| `src/royaltdn/strategy/scalping_orderflow.py` | **Create** | `ScalpingOrderFlowStrategy` — volume + imbalance ratio, TF 1min/5min | ~70 |
| `src/royaltdn/strategy/scalping_spread.py` | **Create** | `ScalpingSpreadStrategy` — spread SMA reversion, TF 1min/5min | ~70 |

**Verification**: `pytest tests/test_fase18_3_doce_estrategias.py -k "scalping"` passes. Strategies grouped as 🟢 SCALPING in menu.

### PR 2 (~350 lines): 5 intraday strategies

| File | Action | Description | Est. lines |
|------|--------|-------------|-----------|
| `src/royaltdn/strategy/intraday_trend.py` | **Create** | `IntradayTrendStrategy` — ADX + EMA trend, TF 15min/1H | ~70 |
| `src/royaltdn/strategy/intraday_vwap.py` | **Create** | `IntradayVWAPStrategy` — VWAP mean reversion, TF 15min/1H | ~70 |
| `src/royaltdn/strategy/intraday_volume_breakout.py` | **Create** | `IntradayVolumeBreakoutStrategy` — volume surge + breakout, TF 15min/1H | ~70 |
| `src/royaltdn/strategy/intraday_support_resistance.py` | **Create** | `IntradaySupportResistanceStrategy` — S/R bounce, TF 15min/1H | ~70 |
| `src/royaltdn/strategy/intraday_macd_divergence.py` | **Create** | `IntradayMACDDivergenceStrategy` — MACD divergence, TF 15min/1H | ~70 |

**Verification**: `pytest tests/test_fase18_3_doce_estrategias.py -k "intraday"` passes. Strategies grouped as 🟡 INTRADÍA in menu.

### PR 3 (~370 lines): 3 swing strategies + registration + tests

| File | Action | Description | Est. lines |
|------|--------|-------------|-----------|
| `src/royaltdn/strategy/swing_trend_following.py` | **Create** | `SwingTrendFollowingStrategy` — EMA cross + ADX, TF 1d | ~60 |
| `src/royaltdn/strategy/swing_reversion.py` | **Create** | `SwingReversionStrategy` — z-score reversion, TF 1d | ~55 |
| `src/royaltdn/strategy/swing_breakout.py` | **Create** | `SwingBreakoutStrategy` — multi-day breakout, TF 1d | ~55 |
| `src/royaltdn/main.py` | **Modify** | Add 13 imports + 13 instantiation gates + update `STRATEGIES_ENABLED` default | +50 |
| `tests/test_fase18_3_doce_estrategias.py` | **Create** | Parametrized test: 13 strategies x 8 test cases via `@pytest.mark.parametrize` | ~150 |

**Verification**: `pytest tests/test_fase18_3_doce_estrategias.py -v` reports 104+ tests passing. `python -c "from royaltdn.main import *"` no ImportError.

## Detailed Change Specifications

### orchestrator.py — `_build_strategies_list()` (PR 1, +3 lines)

**Scanner strategies loop** (~L482, after `"timeframe"`):
```python
"category": getattr(strategy, 'category', 'swing'),
```

**Fallback entry** (~L493, add to existing dict):
```python
"category": "swing",
```

**User strategies loop** (~L509, after `"timeframe"`):
```python
"category": getattr(strat, 'category', 'swing'),
```

### main.py — Registration (PR 3)

**Imports** (in the `try` block at ~L287, after existing imports):
```python
from royaltdn.strategy.scalping_momentum import ScalpingMomentumStrategy
from royaltdn.strategy.scalping_breakout import ScalpingBreakoutStrategy
from royaltdn.strategy.scalping_reversion import ScalpingReversionStrategy
from royaltdn.strategy.scalping_orderflow import ScalpingOrderFlowStrategy
from royaltdn.strategy.scalping_spread import ScalpingSpreadStrategy
from royaltdn.strategy.intraday_trend import IntradayTrendStrategy
from royaltdn.strategy.intraday_vwap import IntradayVWAPStrategy
from royaltdn.strategy.intraday_volume_breakout import IntradayVolumeBreakoutStrategy
from royaltdn.strategy.intraday_support_resistance import IntradaySupportResistanceStrategy
from royaltdn.strategy.intraday_macd_divergence import IntradayMACDDivergenceStrategy
from royaltdn.strategy.swing_trend_following import SwingTrendFollowingStrategy
from royaltdn.strategy.swing_reversion import SwingReversionStrategy
from royaltdn.strategy.swing_breakout import SwingBreakoutStrategy
```

**STRATEGIES_ENABLED default** (~L316):
```python
"sma_crossover,bollinger_rsi,momentum_atr,factor_rotation,"
"scalping_momentum,scalping_breakout,scalping_reversion,scalping_orderflow,scalping_spread,"
"intraday_trend,intraday_vwap,intraday_volume_breakout,intraday_support_resistance,intraday_macd_divergence,"
"swing_trend_following,swing_reversion,swing_breakout"
```

**Instantiation gates** (after existing blocks at ~L325, same pattern):
```python
if "scalping_momentum" in strategies_enabled:
    strategies["scalping_momentum"] = ScalpingMomentumStrategy(category="scalping")
# ... repeat for all 13
```

### Test File — `tests/test_fase18_3_doce_estrategias.py` (PR 3)

Use `@pytest.mark.parametrize` with strategy class, name, category, and params as arguments. Eight test functions, each parametrized over the 13 strategies:

1. `test_instantiation(strategy_class, name, category)`
2. `test_generate_signal_none_data(strategy_class)`
3. `test_generate_signal_crypto(strategy_class, synthetic_data)`
4. `test_generate_signal_stocks(strategy_class, synthetic_data)`
5. `test_get_parameters_none(strategy_class)`
6. `test_get_parameters_crypto(strategy_class)`
7. `test_validate(strategy_class)`
8. `test_category(strategy_class, category)`

Synthetic OHLCV fixture: 100-row `pd.DataFrame` with `open, high, low, close, volume` columns using deterministic sequences that trigger known signal patterns.
