# Proposal: Fase 9 — Textual TUI Migration + Builder Reconstruction

## Intent

Replace the Rich-based `console/` TUI with a Textual-based professional TUI. Rebuild the visual Builder (dead since Streamlit removal in Fase 8) as an interactive Textual screen. Rich stays for CLI-only output (`main.py` cmd_status/cmd_logs). The `logs/*.json` data contract is unchanged — screens consume the same dicts from StateLoader.

## Scope

### In Scope
- New `frontend/textual/` package: TextualApp, 7 screens, 4 widgets, CSS
- Keyboard navigation with Textual BINDINGS (1-6 for screens, P/R/S/Q/H hotkeys)
- Rebuilt BuilderScreen with tabs: Indicators, Rules, Backtesting, Save/Load
- Reuse 4 pure-python modules unchanged: StateLoader, LogBuffer, commands.py, builder_state.py
- 3 chained PRs: (1) Foundation + 6 base screens, (2) BuilderScreen, (3) Tests + polish

### Out of Scope
- Removing `console/` — kept until textual/ is verified
- Streaming data (Orchestrator still writes files atomically)
- Mobile/tablet layouts
- Theme switching (deferred)

## Capabilities

### New Capabilities
- `textual-tui`: Textual-based professional TUI replacing the Rich console. Covers: RoyalTDNApp, screen navigation, 7 screens, reusable widgets, CSS styling, keyboard bindings, Builder reconstruction, IPC via signal files, async state polling.

### Modified Capabilities
None — this is a frontend-only replacement. Backend capabilities (scanner, strategy, trading, IPC, JSON contracts) are unchanged.

## Approach

Full replacement: build `textual/` from scratch, keep `console/` untouched until the new TUI is verified. 1:1 screen mapping from current Rich layouts. Textual's async event loop replaces Rich's 2fps sync render loop + threaded input hack.

```
src/royaltdn/frontend/textual/
├── app.py              # RoyalTDNApp — screen registry, BINDINGS
├── screens/            # 7 screens (Dashboard, Scanner, Estrategias,
│                       #   Trades, Logs, Help, Builder)
├── widgets/            # StatusBar, MetricsGrid, LogPanel, BuilderCanvas
└── css/                # app.tcss, screens.tcss, builder.tcss
```

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/frontend/textual/` | New | Textual package (15+ files) |
| `src/royaltdn/main.py` | Modified | Import TextualApp instead of run_console |
| `pyproject.toml` | Modified | Add textual, pytest-textual deps |
| `tests/test_textual/` | New | Textual test package |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Textual API changes | Low | Pin `textual>=8.0,<9` |
| Async TUI + sync Orchestrator threading | Low | StateLoader TTL + set_interval polling |
| Builder complexity | High | Reuse builder_state.py + strategy/schema.py |
| Termux compatibility | Medium | Test with `TEXTUAL_COLORS=16` fallback |
| Delivery budget (~1500-2000 lines) | High | 3 chained PRs, each under 800 lines |

## Rollback Plan

Per PR: `git revert` merge commit. `console/` is never removed, so fallback exists at every step. Full rollback: delete `textual/`, revert pyproject.toml, revert main.py import.

## Dependencies

- `textual>=8.0,<9` (already installed: 8.2.7)
- `pytest-textual` (test dependency)

## Success Criteria

- [ ] All 6 base screens render correct data from StateLoader
- [ ] Keyboard navigation works without Enter (BINDINGS only)
- [ ] BuilderScreen can load indicator defs, build rule tree, run backtest, save strategy
- [ ] All existing tests (StateLoader, LogBuffer, commands) still pass
- [ ] New textual tests exist and pass
- [ ] Running `python -m royaltdn` loads TextualApp
- [ ] Each PR keeps changed lines under 800
