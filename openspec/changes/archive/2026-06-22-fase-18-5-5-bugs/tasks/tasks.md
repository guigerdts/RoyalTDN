# Tasks: FASE 18.5 — 3 Bugs + Verificación de Integración

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~50–80 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | 3 bug fixes + tests (entire change) | PR 1 | Single PR under 80 lines, base=`feature/fase-18-5-5-bugs` tracker branch |

## Phase 1: Bug Fixes

- [x] **1.1** `.env` — remove duplicate `SCANNER_UNIVERSE` lines 25-26, keep single `SCANNER_UNIVERSE=crypto`
- [x] **1.2** `src/royaltdn/frontend/menu/app.py` — in `run_menu()` or via `set_scanner()`, sync `_current_universe` from `_scanner.universe.universe_type` at init (not hardcoded `"all"`)
- [x] **1.3** `src/royaltdn/main.py` — in `cmd_run()`, after `scanner.verbose = verbose`, if verbose: start `threading.Thread(target=scanner.scan, kwargs={"verbose": True}, daemon=True)` for non-blocking initial scan (populates `_last_explanations`)
- [x] **1.4** `src/royaltdn/frontend/menu/app.py` — in `_show_scanner()` standard mode section (before the "Forzar escaneo" prompt), add handler for `'v'` key: toggle `_scanner.verbose`; if ON and `_last_explanations` empty show message; if OFF return to standard view
- [x] **1.5** `src/royaltdn/frontend/menu/app.py` — in `_render_verbose_dashboard()` input handler, add `'v'` case to toggle verbose OFF and return to standard scanner mode

## Phase 2: Testing

- [x] **2.1** Create `tests/test_fase18_5_bugs.py` with test for `_last_explanations` populated after background scan
- [x] **2.2** Add test for toggle verbose mode (simulate `'v'` press before and after scan)
- [x] **2.3** Add test for `_current_universe` sync from scanner at startup (not hardcoded `"all"`)
- [x] **2.4** Verify all 78 existing FASE 18.4 tests still pass with the new changes

## Implementation Order

Bug 1 (env + sync) → Bug 3 (background scan) → Bug 5 (toggle handlers) → Tests. Each fix is independent but testing depends on all three being implemented.

## Next Step

Ready for implementation (sdd-apply).
