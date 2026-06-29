# SMF Cloud Strategies Specification

## Purpose

Replace 12 non-viable cells with SMF Cloud combinations + existing indicators (RSI, BB, EMA, ADX). 4 cells per timeframe, 3 files.

## Strategy Cell Layout

| File | Timeframe | Cell 1 | Cell 2 | Cell 3 | Cell 4 |
|------|-----------|--------|--------|--------|--------|
| `scalping.yaml` | 15m | SMF retest+RSI | SMF breakout+vol | SMF reversion+BB | SMF flow+EMA |
| `intraday.yaml` | 1h | SMF trend+EMA | SMF trend+ADX | SMF reversion+BB | SMF flow+RSI |
| `swing.yaml` | 1d | SMF swing+BB | SMF swing+RSI | SMF momentum+ADX | SMF flow+EMA |

### Requirement SCS-01: 15m scalping cells

Each of the 4 scalping cells SHALL operate on 15m data and include SMF Cloud indicators in their entry conditions.

| Cell | Entry Logic | Conditions | Exit Style |
|------|-------------|------------|------------|
| `scalping_smf_retest` | AND | `price < smf_basis`, `rsi < 40` | Adaptive trailing |
| `scalping_smf_breakout` | AND | `price > smf_upper`, `volume_surge` | Fixed take-profit |
| `scalping_smf_reversion` | AND | `price > smf_upper`, `bollinger_lower < smf_lower` | Adaptive trailing |
| `scalping_smf_flow` | AND | `smf_strength > 0.6`, `price > ema(20)` | Fixed trailing |

#### Scenario: Scalping SMF indicators resolve

- GIVEN scalping.yaml conditions referencing `smf_basis`, `smf_upper`, `smf_strength`
- WHEN the cell graph evaluates on 50+ bars
- THEN all SMF indicators resolve to float values

#### Scenario: Insufficient data returns False

- GIVEN fewer than 15 bars
- WHEN the cell entry graph evaluates
- THEN it returns False

### Requirement SCS-02: 1h intraday cells

Each of the 4 intraday cells SHALL operate on 1h data and combine SMF with trend/reversion indicators.

| Cell | Entry Logic | Conditions | Exit Style |
|------|-------------|------------|------------|
| `intraday_smf_trend_ema` | AND | `price > smf_basis`, `price > ema(50)` | Adaptive trailing |
| `intraday_smf_trend_adx` | AND | `price > smf_basis`, `adx > 25` | Adaptive trailing |
| `intraday_smf_reversion_bb` | AND | `price < smf_lower`, `price < bollinger_lower` | Fixed take-profit |
| `intraday_smf_flow_rsi` | AND | `smf_strength > 0.5`, `rsi > 55` | Fixed trailing |

#### Scenario: ADX filter gates entry

- GIVEN 1h data with adx > 25, price > smf_basis
- WHEN `intraday_smf_trend_adx` evaluates
- THEN it returns True
- WHEN adx < 20
- THEN it returns False

### Requirement SCS-03: 1d swing cells

Each swing cell SHALL operate on daily data with wider risk parameters.

| Cell | Entry Logic | Conditions | Exit Style |
|------|-------------|------------|------------|
| `swing_smf_bb` | AND | `price < smf_lower`, `price < bollinger_lower` | Fixed take-profit |
| `swing_smf_rsi` | AND | `price < smf_basis`, `rsi < 35` | Adaptive trailing |
| `swing_smf_momentum_adx` | AND | `smf_strength > 0.5`, `adx > 30` | Adaptive trailing |
| `swing_smf_flow_ema` | AND | `smf_strength > 0.4`, `price > ema(100)` | Fixed trailing |

#### Scenario: Wider trailing for swing

- GIVEN `swing_smf_rsi` with `min_mult: 0.7, max_mult: 3.0`
- WHEN trailing evaluates
- THEN range is wider than scalping (0.9–2.2)

### Requirement SCS-04: Short entry mirroring

Each cell SHALL provide a `short_entry` mirroring entry logic with inverted comparisons.

#### Scenario: Conditions invert for short

- GIVEN long entry `price > smf_basis`
- WHEN short_entry defines `price < smf_basis`
- THEN both directions are covered

### Requirement SCS-05: Risk params per timeframe

| Parameter | Scalping | Intraday | Swing |
|-----------|----------|----------|-------|
| `sizing` | 0.005–0.01 | 0.01–0.02 | 0.02–0.04 |
| `max_positions` | 3 | 3 | 2 |
| `max_hold_hours` | 4 | 24 | 168 |

#### Scenario: Scalping sizing is 1%

- GIVEN `sizing: 0.01` on a scalping cell
- WHEN the cell emits a signal
- THEN sizing fraction is 0.01

### Out of Scope

- Multi-timeframe confirmation within a cell
- Per-condition param isolation in optimizer
