# Visual Strategy Builder Specification

## Purpose

Behavior of `pages/builder.py`: 3-column Streamlit page for visual strategy composition, indicator picker (16), rule editor, JSON preview, backtesting, save/deploy. NEW domain — full spec.

## Requirements

### Requirement: 3-Column Layout

The page SHALL render three fixed-width columns.

| Column | Width | Content |
|--------|-------|---------|
| Left | 30% | Indicator picker, params, rule tree editor |
| Center | 40% | Backtest trigger, equity curve (Plotly), metrics table |
| Right | 30% | JSON preview (code block), Save/Deploy buttons, error toasts |

#### Scenario: Page renders without error

- GIVEN user navigates to Builder
- WHEN page renders
- THEN 3 `st.columns` SHALL appear with headers "Configuración", "Backtesting", "JSON / Desplegar"

### Requirement: Indicator Picker

Left column SHALL list all 16 indicators. Selecting one SHALL display its editable parameters with defaults.

| Indicator | Params |
|-----------|--------|
| SMA | Period (2-200, def 20), Source |
| EMA | Period (2-200, def 20), Source |
| RSI | Period (2-50, def 14), Source |
| MACD | Fast (2-50, 12), Slow (2-100, 26), Signal (2-50, 9), Source |
| Bollinger Bands | Period (2-200, 20), Std (0.5-5, 2.0), Source |
| ATR | Period (2-100, 14) |
| Volume | (none) |
| Ichimoku Cloud | Tenkan (2-50, 9), Kijun (2-100, 26), Senkou (2-100, 52) |
| SuperTrend | Period (2-100, 10), Multiplier (0.5-10, 3.0) |
| VWAP | Anchor (D/W/M, D) |
| Z-Score | Period (5-100, 21), Entry Threshold (0.5-5, 2.0), Exit Threshold (0.1-3, 0.5) |
| ADX | Period (2-100, 14), Strong Threshold (20-50, 25) |
| OBV | (none) |
| Stochastic | K (2-50, 14), D (2-50, 3), Slowing (1-10, 3) |
| Parabolic SAR | AF (0.001-0.5, 0.02), Max AF (0.01-1.0, 0.2) |
| Smart Money Flow Cloud | Trend Length (5-200, 34), Engine (EMA/ALMA), ALMA Offset (0-1, 0.85), ALMA Sigma (1-20, 6), Smoothing (1-20, 3), Flow Window (2-100, 24), Flow Smoothing (1-20, 5), Flow Power (0.5-5, 1.2), ATR Length (1-100, 14), Min Mult (0.1-5, 0.9), Max Mult (0.1-5, 2.2) |

#### Scenario: Pick indicator shows params

- GIVEN page loaded
- WHEN user selects "SMA" from dropdown
- THEN "Period" slider (20) and "Source" select (close) SHALL appear

### Requirement: Rule Tree Editor

Users SHALL add conditions grouped by AND/OR. Each condition: indicator, operator, value. Max 2 nesting levels.

Smart Money Flow Cloud SHALL expose 14 condition types: buy_signal, sell_signal, bullish_retest, bearish_retest, price_above_upper, price_below_lower, crosses_above_upper, crosses_below_lower, price_above_basis, price_below_basis, flow_strength_gt, flow_strength_lt, regime_bullish, regime_bearish.

#### Scenario: Third nesting level blocked

- GIVEN a tree with 2 nested AND/OR levels
- WHEN user clicks "Add Group"
- THEN button SHALL be disabled with toast "Maximum 2 levels of AND/OR nesting"

### Requirement: Auto-Backtest on Change

Parameter or rule changes SHALL trigger a backtest. Debounced at Streamlit rerun granularity (~1s).

#### Scenario: Parameter change triggers fresh backtest

- GIVEN SMA(20) with RSI > 70 configured
- WHEN user changes SMA period from 20 to 50
- THEN center column SHALL update with new backtest results

### Requirement: Session State Keys

| Key | Type | Initial | Purpose |
|-----|------|---------|---------|
| `strategy_config` | dict | `{}` | Full strategy JSON |
| `indicators_added` | list | `[]` | Selected indicator names |
| `rules` | dict | `{}` | Current rule tree |
| `backtest_results` | dict\|None | `None` | Cached results |
| `strategy_deployed` | bool | `False` | Deploy flag |

#### Scenario: State persists across reruns

- GIVEN user configured an indicator + rule
- WHEN slider change triggers rerun
- THEN `indicators_added` and `rules` SHALL retain prior values

### Requirement: Save and Deploy Buttons

| Button | Action |
|--------|--------|
| 💾 Save | Write JSON to `user_strategies/{name}_{timestamp}.json` |
| 🚀 Deploy | Write JSON + update `.active` symlink + toast "Strategy deployed" |

#### Scenario: Duplicate name appends timestamp

- GIVEN `TestStrategy.json` exists
- WHEN user clicks Save with name "TestStrategy"
- THEN file SHALL be `TestStrategy_20260616T120000Z.json`

### Requirement: Error Display

Invalid config SHALL show error toasts.

#### Scenario: Value clamped shows warning

- GIVEN user sets SMA period to 0
- WHEN slider clamps to 2
- THEN toast: "Period minimum is 2 — value clamped"

#### Scenario: Empty rules saved

- GIVEN user added indicators but zero rules
- WHEN Save is clicked
- THEN JSON SHALL have empty `entry_rules`/`exit_rules`
- AND strategy SHALL produce no signals (always HOLD)
