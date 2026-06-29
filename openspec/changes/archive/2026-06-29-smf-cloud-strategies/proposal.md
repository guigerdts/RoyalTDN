# Proposal: Smf Cloud Strategies

## Intent

Replace 12 non-viable strategy cells across 3 YAML templates with new combinations using the Smart Money Flow (SMF) Cloud indicator + existing indicators (RSI, Bollinger, EMA, ADX). Add adaptive trailing stops that tighten as flow strength increases.

## Scope

### In Scope
- `_compute_smf()` shared helper + `adaptive_mult()` utility in `conditions.py`
- 5 indicator functions: `smf_upper`, `smf_lower`, `smf_basis`, `smf_flow`, `smf_strength`, all registered in `_INDICATORS`
- `_check_exit()` in `cells/base.py` — adaptive trailing via `adaptive_mult(strength, min_mult, max_mult)`
- `_PARAM_RANGES` entries in `optimize.py`: `flow_len`, `ema_period`, `atr_period`, `min_mult`, `max_mult`
- 12 replacement strategy blocks across `scalping.yaml`, `intraday.yaml`, `swing.yaml`
- Unit tests for SMF indicators and `adaptive_mult`

### Out of Scope
- Multi-timeframe confirmation within a single cell (separate feature)
- Multi-symbol flow averaging (each cell evaluates independently)
- Custom indicator parameter isolation in optimizer (shared params documented but not enforced)
- Changes to `inference/graph.py` or `cells/loader.py`

## Capabilities

### New Capabilities
- `smf-cloud-indicators`: 5 indicator functions + `_compute_smf` + `adaptive_mult` + `_INDICATORS` registration
- `adaptive-trailing`: `_check_exit()` enhancement for dynamic trailing via strength-based multiplier
- `smf-cloud-strategies`: 12 YAML strategy blocks replacing non-viable cells across 3 timeframes

### Modified Capabilities
None — all capabilities are new.

## Approach

| Layer | What | How |
|-------|------|-----|
| `conditions.py` | `_compute_smf()` | Single-pass CLV → RawFlow → MF → Strength → Basis → ATR → bands |
| `conditions.py` | 5 public indicators | Each wraps `_compute_smf`, returns one field |
| `conditions.py` | `adaptive_mult()` | `min_mult + (max_mult - min_mult) * clamp(strength, 0, 1)` |
| `conditions.py` | `_INDICATORS` | Register all 5 by name → function |
| `cells/base.py` | `_check_exit()` | `trail_pct = atr_pct * adaptive_mult(strength, min_mult, max_mult)` |
| `optimize.py` | `_PARAM_RANGES` | 5 new entries: int/float + ranges |
| YAML files | 12 strategy cells | 3 per file: some "pure" SMF Cloud, rest SMF + RSI/BB/EMA/ADX |

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/inference/conditions.py` | Modify | +`_compute_smf`, +5 indicators, +`adaptive_mult`, update `_INDICATORS` |
| `src/royaltdn/cells/base.py` | Modify | `_check_exit()` adaptive trailing logic |
| `src/royaltdn/scripts/optimize.py` | Modify | +5 `_PARAM_RANGES` entries |
| `src/royaltdn/cells/templates/scalping.yaml` | Modify | 4 strategy blocks replaced with SMF combos |
| `src/royaltdn/cells/templates/intraday.yaml` | Modify | 4 strategy blocks replaced with SMF combos |
| `src/royaltdn/cells/templates/swing.yaml` | Modify | 4 strategy blocks replaced with SMF combos |
| `tests/` | New | SMF indicator tests + `adaptive_mult` tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Volume data quality on 15m for illiquid symbols | Medium | Document data requirements; no pipeline guard in MVP |
| Shared params (`flow_len`, `ema_period`) optimized independently per condition | Medium | Use Optuna `suggest_int` with shared trial keys across conditions sharing same param |
| 15× SMF recomputation per bar in optimizer | Low | `_compute_smf` mitigates within-call cost; acceptable for 15m-1d |

## Rollback Plan

Revert each file independently:
- `conditions.py`: remove 5 indicators + `_compute_smf` + `adaptive_mult`, restore `_INDICATORS`
- `base.py`: revert `_check_exit()` to fixed `atr_multiplier`
- YAML files: restore `*.yaml` from git (`git checkout -- templates/*.yaml`)

## Dependencies

- Existing `conditions.py` indicator pattern (compound ops in `evaluate()` work unchanged)
- Existing `_check_exit()` exit rule parsing (add `adaptive_mult` as optional field)

## Success Criteria

- [ ] All 5 SMF indicators registered and evaluable from YAML configs
- [ ] `adaptive_mult()` returns correct bounded values (unit tests)
- [ ] Adaptive trailing works in backtests with SMF strategy
- [ ] All 3 YAML files updated with 12 new strategy cells
- [ ] Tests pass: `pytest tests/ -v`
- [ ] Optimization runs without errors for SMF strategies
