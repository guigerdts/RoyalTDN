# Registration Specification — main.py + Tests

## Purpose

Register all 13 new strategies in `src/royaltdn/main.py` so the scanner can discover and instantiate them. Add a single parametrized test file covering instantiation, signal generation, parameter retrieval, and validation for all strategies.

## ADDED Requirements

### Requirement: main.py imports

`src/royaltdn/main.py` MUST import all 13 strategy classes at the top of the scanner initialization block (within the `try` block alongside existing imports).

Imports MUST use the pattern: `from royaltdn.strategy.{module} import {ClassName}`.

#### Scenario: All imports resolve
- GIVEN main.py with all 13 imports
- WHEN `python -c "from royaltdn.main import *"` runs
- THEN no ImportError is raised

### Requirement: main.py strategy instantiation

The scanner `strategies` dict in `cmd_run()` MUST include all 13 strategies, each gated by its name in `strategies_enabled`. Pattern:

```
if "scalping_momentum" in strategies_enabled:
    strategies["scalping_momentum"] = ScalpingMomentumStrategy(category="scalping")
```

Each strategy MUST be instantiated with its `category=` parameter.

#### Scenario: All strategies registered
- GIVEN STRATEGIES_ENABLED includes all 15 strategy names (3 existing + 13 new)
- WHEN the scanner strategies dict is constructed
- THEN it has 16 entries (3 existing + 13 new)
- AND each strategy's `category` matches its grouping

#### Scenario: Feature flag disables a strategy
- GIVEN STRATEGIES_ENABLED="sma_crossover,bollinger_rsi"
- WHEN the scanner strategies dict is constructed
- THEN only 2 entries exist
- AND no ImportError occurs for unimported strategies

### Requirement: STRATEGIES_ENABLED default

The `os.getenv("STRATEGIES_ENABLED")` default in `main.py` MUST include all 13 new strategy names, comma-separated, alongside the 3 existing ones.

Default value: `"sma_crossover,bollinger_rsi,momentum_atr,factor_rotation,scalping_momentum,scalping_breakout,scalping_reversion,scalping_orderflow,scalping_spread,intraday_trend,intraday_vwap,intraday_volume_breakout,intraday_support_resistance,intraday_macd_divergence,swing_trend_following,swing_reversion,swing_breakout"`

#### Scenario: Default includes all
- GIVEN no STRATEGIES_ENABLED env var is set
- WHEN `cmd_run()` reads the default
- THEN it contains 16 strategy names

### Requirement: Parametrized tests

The system MUST include `tests/test_fase18_3_doce_estrategias.py` with `@pytest.mark.parametrize` covering each strategy. Test cases per strategy:

1. **Instantiation**: `ClassName(category=CATEGORY)` succeeds, `strategy.name` matches, `strategy.category` matches
2. **generate_signal(data=None)**: returns None gracefully (no crash on empty data)
3. **generate_signal(synthetic_data, symbol="BTC/USDT")**: returns dict or None (no exception)
4. **generate_signal(synthetic_data, symbol="AAPL")**: returns dict or None (no exception)
5. **get_parameters()**: returns dict with `crypto_*` and `stocks_*` keys when `symbol=None`
6. **get_parameters(symbol="BTC/USDT")**: returns crypto profile dict
7. **validate()**: returns True with default params
8. **category**: property returns the expected category string

Synthetic OHLCV data SHALL be a `pd.DataFrame` with 100 rows of columns `open, high, low, close, volume` using `np.random` or fixed sequences with known patterns to trigger signals.

#### Scenario: All parametrized cases pass
- GIVEN the test file with parametrize over 13 strategies x 8 cases
- WHEN `pytest tests/test_fase18_3_doce_estrategias.py -v` runs
- THEN 104+ tests pass (some cases may produce multiple assertions)
- AND no strategy raises an unhandled exception

#### Scenario: Strategy with invalid params
- GIVEN a strategy instantiated with `momentum_period=0`
- WHEN `validate()` is called
- THEN it returns False
- AND `get_parameters()` still returns a valid dict

## Out of Scope

- Auto-discovery of strategy modules (registration remains manual)
- Unit tests for signal accuracy/backtesting (covered by strategy-specific tests)
- Integration tests with live scanner

## Test Considerations

- Test file must be importable without live API keys, Redis, or broker connections
- Use `conftest.py` fixtures if synthetic data generation is shared across test modules
- Each parametrize entry should have a clear `id=` for readable pytest output
- Cover both `symbol=None` (default params) and `symbol=<crypto/stock>` branches in `get_parameters`
