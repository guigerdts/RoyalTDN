# Tasks: SMF Cloud + Adaptive Trailing + 12 Replacement Strategies

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

| Field | Value |
|-------|-------|
| Estimated changed lines | 320–370 |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR #1 (Foundation, ~120 lines) → PR #2 (Application, ~200-250 lines) |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | SMF indicators + adaptive_mult + unit tests | PR #1 | Base = feature/tracker branch |
| 2 | Adaptive trailing + YAML strategies + optimizer + integration tests | PR #2 | Base = PR #1 branch |

## Phase 1 (Foundation) — PR #1

- [x] 1.1 Add `_compute_smf()` in `conditions.py`: single-pass CLV → RawFlow → MF → Strength → Basis → ATR → upper/lower bands
- [x] 1.2 Add `adaptive_mult(strength, min_mult, max_mult)` utility function in `conditions.py`
- [x] 1.3 Add 5 indicator wrappers: `smf_upper`, `smf_lower`, `smf_basis`, `smf_flow`, `smf_strength` in `conditions.py`
- [x] 1.4 Register all 5 in `_INDICATORS` dict + implement module-level cache on `_compute_smf` keyed by `(id(data), flow_len, ema_period, atr_period)` with >10-entry eviction
- [x] 1.5 Unit tests: `_compute_smf` returns 9-key dict with sufficient data, empty dict on <15 bars, zero volume/prices don't raise; all 5 wrappers return correct fields; `adaptive_mult` clamping (0→min, 1→max, NaN→min, out-of-range clamped); cache hit/miss/eviction; compound operators resolve via `_INDICATORS`

## Phase 2 (Application) — PR #2

- [x] 2.1 Modify `_check_exit()` in `base.py`: parse `min_mult`/`max_mult` from trailing_stop params, compute `adaptive_mult(strength)` from `_compute_smf`, fall back to existing ATR behavior when params absent
- [x] 2.2 Replace 4 scalping.yaml strategies (15m): `smf_retest_rsi`, `smf_momentum_ema`, `smf_breakout_volume`, `smf_reversion_bb` — each with SMF indicators in entry conditions + short_entry mirror + adaptive trailing
- [x] 2.3 Replace 4 intraday.yaml strategies (1h): `smf_trend_adx`, `smf_retest_bollinger`, `smf_momentum_volume`, `smf_zscore_reversion` — SMF + ADX/BB/RSI combos
- [x] 2.4 Replace 4 swing.yaml strategies (1d): `smf_trend_bollinger`, `smf_momentum_adx`, `smf_reversion_zscore`, `smf_retest_rsi` — wider risk params
- [x] 2.5 Add `_PARAM_RANGES` entries in `optimize.py`: `flow_len` (int, 10–50), `ema_period` (int, 10–60), `atr_period` (int, 7–30), `min_mult` (float, 0.5–1.5, step=0.1), `max_mult` (float, 1.5–4.0, step=0.1)
- [x] 2.6 Add `_SMF_SHARED_PARAMS = {"flow_len", "ema_period", "atr_period"}` + shared-cache linking in `suggest_params()` so first SMF condition suggests canonical keys and subsequent ones reuse

## Phase 3 (Cleanup) — included in PR #2

- [x] 3.1 Integration tests: `test_smf_integration.py` — YAML loading, SMF cell graph evaluation, _PARAM_RANGES validation, backward compat, adaptive trailing
- [x] 3.2 Cleanup: verify `pytest tests/ -v` passes (70 passed, 31 skipped), no unused imports or dead code
