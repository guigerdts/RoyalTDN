# Adaptive Trailing Specification

## Purpose

Enhance `_check_exit()` in `cells/base.py` to compute trailing stop distance dynamically using SMF flow strength. The multiplier tightens as strength increases, reducing risk in high-conviction flows.

## Requirements

| ID | Requirement | Strength | Backward Compat |
|----|-------------|----------|-----------------|
| AT-01 | Trailing stop accepts `min_mult` + `max_mult` params | MUST | Yes (optional) |
| AT-02 | `adaptive_mult(strength)` scales the ATR multiplier | MUST | — |
| AT-03 | Strength sourced from `_compute_smf` per bar | MUST | — |
| AT-04 | Exit rules WITHOUT `min_mult`/`max_mult` behave as before | MUST | Yes |
| AT-05 | `_PARAM_RANGES` entries for optimization | MUST | — |

### Requirement AT-01: YAML exit params

Exit rules of type `trailing_stop` SHALL accept optional `min_mult` and `max_mult` in their `params` dict. When present, the ATR-based trailing distance SHALL be calculated as `atr_pct * adaptive_mult(strength, min_mult, max_mult)`.

#### Scenario: Adaptive trailing in YAML

- GIVEN a trailing_stop rule with `atr_multiplier: 2.0, min_mult: 0.8, max_mult: 2.5`
- WHEN the cell is in position and `_check_exit()` evaluates the trailing stop
- THEN the trail distance is `atr_pct * adaptive_mult(strength, 0.8, 2.5)`

#### Scenario: Strength is computed per bar

- GIVEN market data with sufficient bars for `_compute_smf`
- WHEN `_check_exit()` evaluates adaptive trailing
- THEN the strength value is extracted from `_compute_smf(data)["strength"]`

### Requirement AT-02: Multiplier bounds

`adaptive_mult` SHALL clamp the effective multiplier to `[min_mult, max_mult]` regardless of strength values.

#### Scenario: Weak flow widens the trail

- GIVEN strength=0.0, min_mult=0.8, max_mult=2.5
- WHEN adaptive trailing is computed
- THEN the trail multiplier is 0.8 (wider stop = more room)

#### Scenario: Strong flow tightens the trail

- GIVEN strength=1.0, min_mult=0.8, max_mult=2.5
- WHEN adaptive trailing is computed
- THEN the trail multiplier is 2.5 (tighter stop = less risk)

### Requirement AT-03: Backward compatibility

Exit rules without `min_mult` and `max_mult` fields SHALL fall back to the existing `atr_multiplier`-only behavior. No existing strategy cell SHALL require changes to its exit config.

#### Scenario: Existing strategy unaffected

- GIVEN a trailing_stop rule with only `atr_multiplier: 2.0` (no min/max_mult)
- WHEN `_check_exit()` evaluates the trailing stop
- THEN the trail distance is `atr_multiplier * atr` (unchanged)
- AND `adaptive_mult` is NOT invoked

### Requirement AT-04: Optimizer param ranges

`_PARAM_RANGES` in `optimize.py` SHALL include entries for `min_mult` (float, 0.5–2.0) and `max_mult` (float, 1.5–4.0), both OPTUNA `suggest_float` with `log=False`.

#### Scenario: Optimizer discovers both params

- GIVEN a strategy using adaptive trailing
- WHEN the optimizer runs with SMF indicators enabled
- THEN `min_mult` and `max_mult` appear in the sampled parameter set

### Requirement AT-05: Fixed-pct trailing unchanged

Fixed-percentage trailing (`pct` mode) SHALL NOT be affected by adaptive trailing logic. The adaptive mechanism SHALL ONLY modify ATR-based trailing.

#### Scenario: Pct-mode trailing ignores adaptive

- GIVEN a trailing_stop rule with `pct: 1.5` (no atr_multiplier)
- WHEN `_check_exit()` evaluates the trailing stop
- THEN the exit distance is `pct * entry_price * exit_pct_scale`
- AND `adaptive_mult` is NOT called

### Out of Scope

- Adaptive stop-loss or take-profit (trailing only)
- Re-computation of SMF flow across multiple bars for exit (uses current bar only)
