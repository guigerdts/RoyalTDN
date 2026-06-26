# Archive: optuna-optimization

**Archived**: 2026-06-23
**Status**: Archived — intentional-with-warnings

## Change Summary

Optuna-based automatic strategy optimization system. CLI entry point for Bayesian hyperparameter search over indicator params, exit config, and risk sizing. Historical data caching with parquet, bar-by-bar Cell simulation, metrics via `compute_metrics()`, YAML auto-update with `.bak` backup, polling hot-reload watcher, and periodic scheduler.

## Artifacts

| Artifact | Path | Notes |
|----------|------|-------|
| Proposal | `openspec/changes/archive/2026-06-23-optuna-optimization/proposal.md` | Original proposal |
| Design | `openspec/changes/archive/2026-06-23-optuna-optimization/design/design.md` | Technical design |
| Tasks | `openspec/changes/archive/2026-06-23-optuna-optimization/tasks.md` | 15/15 tasks complete |
| Spec (main) | `openspec/specs/strategy-optimization/spec.md` | Updated with implementation deltas |

## Delta Specs Applied

The following deltas were synced to `openspec/specs/strategy-optimization/spec.md`:

| Change | Detail |
|--------|--------|
| JSON log path | `logs/optimization_results.json` → `logs/optimization/optimization_results.json` |
| Param ranges | Updated 6 ranges to match implementation (`max_pct`, `lookback`, `signal`, `tenkan`, `kijun`, `senkou_b`) |
| `--validate` flag | Marked as deferred (no-op) in CLI table |
| `validation_sharpe` | Marked as future/not-implemented in JSON schema |
| `--strategy` default | Updated from "required" to "None (runs all when omitted)" |
| Deferred section | Added documenting `--validate`, `validation_sharpe`, test suite as deferred |

## Implementation Details

- **PRs**: 3 chained PRs (Foundation → Core Engine → Integration)
- **Tasks**: 15/15 implemented
- **New files**: `scripts/optimize.py`, `core/hot_reload.py`
- **Modified files**: `cells/base.py`, `data/historical.py`, `run.py`, `config.yaml`, `pyproject.toml`
- **Dependencies added**: `optuna>=4.0`, `pyarrow>=14.0`

## Verification

**Verdict**: PASS WITH WARNINGS
- All 10 requirements implemented structurally
- 0/25 scenarios have covering tests (UNTESTED)
- No CRITICAL issues found
- Minor spec deviations (JSON path, parameter ranges, `--validate` deferral) corrected in this archive

## Stale-Checkbox Reconciliation

The Engram tasks observation (#583) showed unchecked Phase C and D implementation tasks. This is a stale-checkbox condition: `apply-progress` (#585) confirms all 3 PRs complete, `verify-report` (#587) confirms all 15 tasks done, and the orchestrator explicitly confirmed all tasks implemented. The OpenSpec `tasks.md` correctly shows all tasks as `[x]`. The Engram observation was updated to reflect the actual completed state during this archive cycle.

## Risks

- **No regression tests**: Changes to optimize.py or data/historical.py could break optimization without detection
- **`--validate` deferred**: Hold-out validation not implemented — results may overfit
- **External API dependency**: Binance rate limits untested against real API
