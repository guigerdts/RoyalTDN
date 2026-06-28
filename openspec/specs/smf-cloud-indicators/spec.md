# SMF Cloud Indicators Specification

## Purpose

Five indicator functions wrapping `_compute_smf()`, plus `adaptive_mult()` — all registered in `_INDICATORS` — enabling YAML-based strategies to reference SMF Cloud values in entry/exit conditions.

## Requirements

| ID | Function | Returns | Params | Edge Case |
|----|----------|---------|--------|-----------|
| SMF-01 | `_compute_smf()` | `dict` (9 keys) | `flow_len=24, ema_period=34, atr_period=14` | Empty dict on insufficient data |
| SMF-02 | `smf_upper()` | `float` | — | `0.0` |
| SMF-03 | `smf_lower()` | `float` | — | `0.0` |
| SMF-04 | `smf_basis()` | `float` | — | `0.0` |
| SMF-05 | `smf_flow()` | `float` | — | `0.0` |
| SMF-06 | `smf_strength()` | `float` | — | `0.0` |
| SMF-07 | `adaptive_mult()` | `float` | `min_mult=0.9, max_mult=2.2` | `min_mult` (when strength is NaN) |

### Requirement SMF-01: `_compute_smf`

`_compute_smf(data, flow_len, ema_period, atr_period)` SHALL compute a single-pass pipeline: CLV → RawFlow → MF → Strength → Basis → ATR → upper/lower bands.

The returned dict SHALL contain exactly these keys: `clv, raw_flow, mf, strength, mult, basis, atr, upper, lower`.

#### Scenario: Sufficient data returns all 9 keys

- GIVEN market data with 50+ bars (close, high, low, volume)
- WHEN `_compute_smf(data)` is called with default params
- THEN the result dict contains all 9 keys
- AND all values are finite floats

#### Scenario: Insufficient data returns empty dict

- GIVEN market data with fewer than 15 bars
- WHEN `_compute_smf(data)` is called
- THEN the result is an empty dict `{}`

#### Scenario: Zero volume or zero price does not raise

- GIVEN market data where volume or price is zero for all bars
- WHEN `_compute_smf(data)` is called
- THEN no exception is raised
- AND relevant numeric fields are `0.0`

### Requirement SMF-02 to SMF-06: Five wrapper functions

Each wrapper function (smf_upper, smf_lower, smf_basis, smf_flow, smf_strength) SHALL call `_compute_smf(data)` and return a single float from the corresponding dict key.

#### Scenario: All wrappers return valid floats with sufficient data

- GIVEN market data with 50+ bars
- WHEN each of the 5 wrappers is called
- THEN each returns a `float` value
- AND smf_upper >= smf_basis >= smf_lower
- AND smf_strength is in [0.0, 1.0]

#### Scenario: All wrappers return 0.0 with insufficient data

- GIVEN market data with fewer than 15 bars
- WHEN each of the 5 wrappers is called
- THEN each returns `0.0`

### Requirement SMF-07: `adaptive_mult`

`adaptive_mult(strength, min_mult, max_mult)` SHALL compute `min_mult + (max_mult - min_mult) * clamp(strength, 0, 1)`.

#### Scenario: Strength maps to multiplier

- GIVEN `min_mult=0.9, max_mult=2.2`
- WHEN `adaptive_mult(0.0, ...)` is called
- THEN the result is `0.9`
- WHEN `adaptive_mult(1.0, ...)` is called
- THEN the result is `2.2`
- WHEN `adaptive_mult(0.5, ...)` is called
- THEN the result is `1.55`

#### Scenario: Out-of-range strength is clamped

- GIVEN `min_mult=0.9, max_mult=2.2`
- WHEN `adaptive_mult(-0.5, ...)` is called
- THEN the result is `0.9`
- WHEN `adaptive_mult(1.5, ...)` is called
- THEN the result is `2.2`

#### Scenario: NaN strength returns min_mult

- GIVEN `min_mult=0.9, max_mult=2.2`
- WHEN `adaptive_mult(float("nan"), ...)` is called
- THEN the result is `0.9`

### Requirement SMF-08: `_INDICATORS` registration

All 5 wrappers + `adaptive_mult` SHALL be registered in the `_INDICATORS` dict by name.

#### Scenario: All SMF indicators are resolvable

- GIVEN the `_resolve_value` function
- WHEN each of "smf_upper", "smf_lower", "smf_basis", "smf_flow", "smf_strength", "adaptive_mult" is resolved
- THEN each returns a valid function reference

#### Scenario: Compound operators work

- GIVEN a condition string `"price > smf_basis"`
- WHEN `evaluate()` is called with that operator
- THEN the condition resolves both sides correctly
- AND returns a boolean verdict

### Out of Scope

- Multi-symbol flow averaging
- Custom parameter isolation per condition in optimizer
