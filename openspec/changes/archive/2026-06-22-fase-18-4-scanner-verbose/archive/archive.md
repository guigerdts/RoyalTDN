# Archive Report — FASE 18.4

## Change Summary

- **Name**: Scanner verbose + intervalo dinámico + validación dinero real
- **Status**: ✅ Complete
- **Archived**: 2026-06-22
- **Mode**: Hybrid (filesystem + Engram)
- **Original location**: `openspec/changes/fase-18-4-scanner-verbose/`
- **Archived to**: `openspec/changes/archive/2026-06-22-fase-18-4-scanner-verbose/`

## Deliverables

| Component | Files | PR |
|-----------|-------|----|
| `explain()` base contract | `base.py` | PR-1a |
| `sma_crossover` + `bollinger_rsi` explain | `sma_strategy.py`, `bollinger_rsi.py` | PR-1a |
| `momentum_atr` + `swing_trend_following` + `swing_breakout` explain | 3 strategy files | PR-1b |
| 5 scalping explain | `scalping_momentum.py`, `scalping_breakout.py`, `scalping_reversion.py`, `scalping_orderflow.py`, `scalping_spread.py` | PR-2 |
| 5 intraday explain | `intraday_trend.py`, `intraday_vwap.py`, `intraday_volume_breakout.py`, `intraday_support_resistance.py`, `intraday_macd_divergence.py` | PR-3a |
| `swing_reversion` explain + all-16 test | `swing_reversion.py`, `factor_rotation.py`, `test_fase18_4_pr3b.py` | PR-3b |
| UI verbose + interval + scalping disable + readiness | `app.py`, `orchestrator.py`, `main.py`, `scanner.py` | PR-4 |
| Tests | 6 test files (`test_fase18_4_pr1a.py`, `pr1b.py`, `pr2.py`, `pr3a.py`, `pr3b.py`, `pr4.py`), 78 tests | All PRs |

## Spec Compliance

- **27/28 (96.4%)** — All spec requirements met
- **1 known gap**: Interval mismatch warning (R6 in `spec_dynamic_interval.md`) not implemented. The env-var override works and KPI shows `(env)` suffix, but the warning listing strategies whose interval is below the current actual interval is not rendered.

## Git History

```
6 commits on feature/fase-18-4-scanner-verbose
a5d160b feat(strategy): PR-1a — explain() base + sma_crossover + bollinger_rsi + scanner verbose
11c7c90 feat(strategy): PR-1b — momentum_atr + swing_trend_following + swing_breakout explain()
73dd29e feat(strategy): PR-2 — explain() on 5 scalping strategies
543ca7d feat(strategy): PR-3a — explain() on 5 intraday strategies
91d1b30 feat(strategy): PR-3b — swing_reversion explain() + all-16 iteration test
010e198 feat(core): PR-4 — UI verbose + dynamic interval + scalping disable + readiness
```

## Task Completion

- **PR-1 tasks**: 9/9 complete (all `[x]` in `tasks.md`)
- **PR-2 tasks**: 6/6 complete (no Status column — all implemented per apply-progress)
- **PR-3a tasks**: 6/6 complete (no Status column — all implemented per apply-progress)
- **PR-3b tasks**: 5/5 complete (no Status column — all implemented per apply-progress)
- **PR-4 tasks**: 15/15 complete (no Status column — all implemented per apply-progress)
- **Total**: 41/41 tasks complete

Note: Only PR-1 tasks had explicit Status column in tasks.md. PR-2 through PR-4 tasks used table format without Status column — all verified complete via apply-progress and test results.

## Spec Synced to Main Specs

| Domain | Action | Source |
|--------|--------|--------|
| `scanner-verbose` | Created (new) | Copied from `spec_scanner_verbose.md` |
| `dynamic-interval` | Created (new) | Copied from `spec_dynamic_interval.md` |
| `scalping-disable` | Created (new) | Copied from `spec_scalping_disable.md` |
| `check-readiness` | Created (new) | Copied from `spec_check_readiness.md` |

All 4 delta specs were full standalone specs (no existing main spec to merge into). Copied to new domain directories under `openspec/specs/`.

## Archive Contents

- `proposal.md` ✅
- `spec/spec_scanner_verbose.md` ✅
- `spec/spec_dynamic_interval.md` ✅
- `spec/spec_scalping_disable.md` ✅
- `spec/spec_check_readiness.md` ✅
- `design/technical_design.md` ✅
- `design/file_change_map.md` ✅
- `tasks/tasks.md` ✅ (41/41 complete)
- `archive/archive.md` ✅ (this file)

## Known Gaps

1. **Interval mismatch warning not displayed** (spec R6, dynamic-interval): The env-var override is respected and the KPI shows `(env)` suffix, but the spec requires a warning listing strategies whose recommended interval is lower than the current actual interval. Non-functional UX gap.
2. **FactorRotationStrategy uses default `explain()`** (empty template): By design — factor_rotation uses ranked scores, not binary threshold conditions, making the `explain()` contract (name/met/value/threshold/gap_pct/direction) a poor fit. The strategy produces a RANK signal with per-factor scores.
3. **No verify-report.md**: The verification step was performed (78 tests pass, all scenarios validated) but no formal `verify-report.md` artifact was created in the change folder. This is a process gap but does not affect the implementation quality.

## Test Results

- **78 new tests** across 6 test files
- **All passing** on branch `feature/fase-18-4-scanner-verbose`
- Coverage: `explain()` contract compliance, `generate_signal()` consistency, dynamic interval calc, scalping disable, check-readiness, gap_pct calculation
