# Tasks: FASE 18.2 — Parámetros duales crypto/stocks + Reorganización visual del menú

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~250 (158 + 93) |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Strategy layer + scanner (~158 lines) → PR 2: Menu + main.py (~93 lines) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Dual params + category system + scanner dispatch | PR 1 | Base branch = feature/tracker (`fase-18-2-parametros-duales-menu`) |
| 2 | Menu reorg + universe quick-select | PR 2 | Base = PR 1 branch; depends on category existing in strategies |

## Phase 1: Foundation — Category + Universe setter

- [ ] 1.1 `strategy/base.py` — Add `category="swing"` param to `__init__`, add `category` property
- [ ] 1.2 `strategy/base.py` — Add optional `symbol=None` to `generate_signal()` signature; make `get_parameters()` concrete (remove `@abstractmethod`, return `{"timeframe": ..., "category": ...}`)
- [ ] 1.3 `scanner/universe.py` — Add `@universe_type.setter` that validates + calls `invalidate_cache()`
- [ ] 1.4 `tests/` — Verify `isinstance(s, BaseStrategy)` + category default + universe setter invalidates cache. **Depends on: 1.1–1.3**

## Phase 2: Dual params — Three strategies

- [ ] 2.1 `strategy/sma_strategy.py` — Add `_PROFILES` dict, pass `category="swing"` to super, add `symbol` to `generate_signal()` with profile resolution (local vars), implement `get_parameters(symbol)` three-way
- [ ] 2.2 `strategy/bollinger_rsi.py` — Same 4-change pattern as 2.1 (profiles, category, symbol routing, three-way get_parameters)
- [ ] 2.3 `strategy/momentum_atr.py` — Same 4-change pattern as 2.1
- [ ] 2.4 `tests/` — Unit: each strategy with crypto symbol → crypto profile, stock symbol → stock profile, no symbol → stocks default. **Depends on: 1.1–1.2, 2.1–2.3**

## Phase 3: Scanner dispatch

- [ ] 3.1 `scanner/scanner.py` — In `scan()` loop, replace `strategy.generate_signal(data)` with `inspect.signature()` check + conditional `symbol` kwarg
- [ ] 3.2 `tests/` — Mock FactorRotationStrategy, verify `symbol` NOT passed via inspect dispatch. **Depends on: 3.1**

## Phase 4: Menu reorganization

- [ ] 4.1 `frontend/menu/app.py` — Add module-level universe vars: `_current_universe`, `_UNIVERSE_CYCLE`, `_universe_setter`, `set_universe_setter()`
- [ ] 4.2 `frontend/menu/app.py` — Add `_cycle_universe()` helper that wraps index, calls setter if wired
- [ ] 4.3 `frontend/menu/app.py` — `_print_header()`: add `[cyan]Universe: {name}[/]` line after pause status
- [ ] 4.4 `frontend/menu/app.py` — `_print_menu()`: add `("U", "Cambiar universo...")` item before `("0", "Salir")`
- [ ] 4.5 `frontend/menu/app.py` — Main loop: handle `cmd.lower() == "u"` → call `_cycle_universe()`, log, print confirmation
- [ ] 4.6 `frontend/menu/app.py` — `_show_estrategias()`: group entries by `config.get("category", "swing")`, render Rich Table per category section with colored headers (🔵 SWING, etc.), add Categoría column, dim placeholder for empty sections
- [ ] 4.7 `main.py` — In `cmd_run()`, wire `set_universe_setter()` after scanner creation, before `run_menu()`
- [ ] 4.8 `tests/` — Verify `_cycle_universe()` cycles correctly, 'U' key handler works, category sections render. **Depends on: 4.1–4.7**

## PR Boundaries

### PR 1 — Strategy layer + scanner dispatch
**Files**: `base.py`, `universe.py`, `sma_strategy.py`, `bollinger_rsi.py`, `momentum_atr.py`, `scanner.py` + tests
**Base**: `feature/fase-18-2-parametros-duales-menu`
**Tasks**: 1.1–1.4, 2.1–2.4, 3.1–3.2
**Est. lines**: ~158

### PR 2 — Menu reorganization + universe quick-select
**Files**: `app.py`, `main.py` + tests
**Base**: PR 1 branch (previous PR's branch — not main)
**Tasks**: 4.1–4.8
**Est. lines**: ~93
**Depends on**: PR 1 (strategies must have `category` attr for menu to render sections)
