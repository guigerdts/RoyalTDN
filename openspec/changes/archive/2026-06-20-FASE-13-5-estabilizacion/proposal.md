# Proposal: FASE 13.5 — Estabilización

## Intent

Fix 4 bugs from FASE 13 testing: navigation gaps, mock data leaks into production views, and missing log file fallback.

## Scope

### In Scope
- Add `0=Volver` navigation to Dashboard, Scanner, Activity
- Skip `strategy == "mock"` signals in Scanner; show placeholder
- Fallback to `logs/bot.log` (last 50 lines) when LogBuffer empty
- Reset `logs/trades.json` to empty; backup seed data to `tests/fixtures/mock_trades.json`
- 2 chained PRs (Bugs 1-3 → PR1, Bug 4 → PR2) against `feature/fase-13-5`

### Out of Scope
- LogBuffer persistence redesign. Spec-level changes (these align with existing spec intent).

## Capabilities

**New:** None — implementation fixes, not new capabilities.
**Modified:** None — no spec-level behavior changes.

## Approach

**PR1 — Navigation & Display (Bugs 1-3):**
- `_show_dashboard()`: early return after manual mode exit in auto-refresh
- `_show_scanner()`: add `[0] Volver`, skip mock signals
- `_show_activity()`: replace `_wait_enter()` with `0=Volver`
- `_show_logs()`: when LogBuffer empty, read+colorize last 50 lines of `logs/bot.log`

**PR2 — Trades Reset (Bug 4):**
- Copy `logs/trades.json` → `tests/fixtures/mock_trades.json`
- Write empty trades file: `{"trades":[], "total_trades":0, ...}`

## Affected Areas

| File | Impact | Change |
|------|--------|--------|
| `src/royaltdn/frontend/menu/app.py` (4 fns) | Modified | Navigation, mock skip, log fallback |
| `logs/trades.json` | Modified | Reset to empty |
| `tests/fixtures/mock_trades.json` | New | Seed data backup |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| bot.log encoding fails | Low | try/except, degrade gracefully |
| Empty trades breaks readers | Med | `load_trades()` already handles empty lists |
| Chained PR diff bleed | Low | Target intermediate branch; rebase if dirty |

## Rollback

- PR1: revert 4 function changes in `app.py`
- PR2: restore `trades.json` from fixtures, delete fixtures file

## Dependencies

None.

## Success Criteria

- [ ] Dashboard auto-refresh shows `0=Volver` and exits to menu
- [ ] Scanner skips mock signals, shows placeholder when no real data
- [ ] Activity has `0=Volver` instead of `Enter para volver`
- [ ] Logs show bot.log content when LogBuffer empty
- [ ] Trades show empty state, not AAPL/MSFT seed data
