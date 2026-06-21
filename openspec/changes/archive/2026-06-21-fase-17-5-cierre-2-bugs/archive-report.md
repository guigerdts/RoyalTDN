# Archive Report: FASE 17.5 (CIERRE) — Corrección definitiva de los 2 bugs restantes

## Metadata

| Field | Value |
|-------|-------|
| **Change** | FASE 17.5 (CIERRE) — Corrección definitiva de los 2 bugs restantes |
| **Archive Date** | 2026-06-21 |
| **Archive Path** | `openspec/changes/archive/2026-06-21-fase-17-5-cierre-2-bugs/` |
| **Verdict** | ✅ Pass |
| **Archiver** | sdd-archive sub-agent |

## Completeness Gate

- [x] All 8 tasks marked `[x]` in filesystem `tasks.md`
- [x] Verify report: PASS WITH WARNINGS — no CRITICAL issues
- [x] Engram tasks observation (#515) reconciled: stale checkboxes updated to match filesystem (apply-progress + verify-report confirmed completion)

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `crypto-scanner` | Updated | 3 MODIFIED requirements merged from `crypto-universe-format` delta: REQ-CRYPTO-UNIVERSE (broker_type + DEFAULT_CRYPTO_BINANCE), REQ-CRYPTO-LIQUIDITY (Spanish warning for empty DF), REQ-CRYPTO-MAIN (broker_type forwarding to AssetUniverse). REQ-CRYPTO-SCANNER preserved unchanged. |
| `build-lifecycle` | Created | New spec created from delta: REQ-PYC-DISABLE (bytecode cache writing disabled at module load). |

## Archive Contents

- `proposal.md` ✅ — Intent, scope, approach for both bugs
- `exploration.md` ✅ — Prior exploration artifacts
- `specs/` ✅ — Delta specs: `crypto-universe-format/`, `build-lifecycle/`
- `design.md` ✅ — Technical design: Option A+C, is_crypto_symbol(), broker detection
- `tasks.md` ✅ — 8/8 tasks complete (Bug 7: 1 task, Bug 2: 5 tasks, Tests: 3 tasks)
- `verify-report.md` ✅ — PASS WITH WARNINGS (W1: aarch64 env issue, W2/W3: untested scenarios — pre-existing gaps, not regressions)
- `archive-report.md` ✅ — This file

## Source of Truth Updated

- `openspec/specs/crypto-scanner/spec.md` — merged 3 MODIFIED requirements
- `openspec/specs/build-lifecycle/spec.md` — new spec created

## Engram Artifact Lineage

| Artifact | Observation ID | Type |
|----------|---------------|------|
| `sdd/fase-17-5-cierre-2-bugs/proposal` | #512 | architecture |
| `sdd/fase-17-5-cierre-2-bugs/spec` | #513 | architecture |
| `sdd/fase-17-5-cierre-2-bugs/design` | #514 | architecture |
| `sdd/fase-17-5-cierre-2-bugs/tasks` | #515 (updated) | architecture |
| `sdd/fase-17-5-cierre-2-bugs/verify-report` | #517 | architecture |
| `sdd/fase-17-5-cierre-2-bugs/archive-report` | (this) | architecture |

## Reconciliation Notes

The Engram tasks observation (#515) contained stale unchecked checkboxes (`- [ ]`) because `sdd-apply` updated only the filesystem `tasks.md`. The verify report (#517) confirmed all 8 tasks complete. The Engram observation was updated to match during archive. This is a mechanical checkbox reconciliation — all tasks were confirmed complete by verify-report apply-progress evidence.

## Observations

- **Bug 7 (pyc cache)**: Minimal 1-line change (`sys.dont_write_bytecode = True`) — zero side effects, fully independent from Bug 2.
- **Bug 2 (crypto format)**: Richer change affecting 6 files + tests. The `is_crypto_symbol()` centralized helper reduced future maintenance cost for crypto detection. All 5 `/`-in-symbol detection sites across 4 files were migrated.
- **Verify warnings**: W2/W3 (untested NaN volume + valid data scenarios) are pre-existing gaps not introduced by this change. Recommend addressing as tech debt.
