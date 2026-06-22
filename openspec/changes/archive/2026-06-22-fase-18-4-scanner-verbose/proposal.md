# Proposal: FASE 18.4 — Scanner verbose + intervalo dinámico + validación dinero real

## Intent

4 problemas user-facing del scanner actual: (A) 0 señales sin explicación, (B) intervalo fijo 60min ignorando estrategias activas, (C) scalping activo en universos non-crypto, (D) no hay comando pre-lanzamiento para validar readiness.

## Scope

### In Scope
1. **Scanner Verbose**: `explain()` abstract method en BaseStrategy → implementar en 17 estrategias. Scanner `scan(verbose=True)` escribe `logs/scanner_verbose.log`. UI: L1 compacto con closeness bars por estrategia, L2 decision tree con checkmarks/gaps. Navegación ↑/↓ símbolos, 'E' expandir, '0' volver, 's' forzar scan. Filtro "verbose" en Logs. Flag `--verbose` en CLI.
2. **Dynamic Interval**: auto-ajuste según estrategias activas (scalping→2min, intraday→15min, swing→240min, none→60min). Overridable vía `SCANNER_INTERVAL_MINUTES`. KPI "Scan: cada Xmin" + warning si intervalo > recomendado.
3. **Disable Scalping on non-crypto**: en universe change a non-crypto, set `active=false` para scalping en `strategies.json`. Notificación menú: "🔴 Scalping desactivado". Reactivación manual con warning.
4. **check-readiness CLI**: 7 checks (trades≥50, Sharpe>0.5, slippage<0.5%, kill switch tested, Telegram OK, broker connectivity). Rich Panel + verdict READY / CASI LISTO / NO RECOMENDADO.

### Out of Scope
- Verbose mode en auto-scans nocturnos (solo manual o `--verbose`)
- Realtime streaming de explanations (archivo + UI on-demand)
- Backtest para validar readiness (check es puntual, no histórico pesado)

## Capabilities

### New Capabilities
- `scanner-verbose`: Explain() contract, verbose scan output, visual decision trees
- `check-readiness`: Pre-flight validation command with 7 checks

### Modified Capabilities
- `strategy-execution`: `explain()` abstract method added to BaseStrategy, implemented by all 17 strategies. Shared `_compute_indicators()` extracted from `generate_signal()` to avoid duplication.
- `interactive-menu`: Scanner screen rewrite (L1/L2 dual mode), Logs filter "verbose", interval display in KPI/Scanner, scalping notification on universe change

## Approach

Exploration confirmed: (A) extract `_compute_indicators()` from each strategy → share with `explain()`, (B) compute recommended interval from active strategies' `category`, (C) hook `_cycle_universe()` → check scalping → write `strategies.json`, (D) new `cmd_check_readiness()` in main.py using `StateLoader` + broker pings. PR chain: Part D standalone first, then Parts A-C together (share scanner UI code).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/strategy/base.py` | Modified | `explain()` abstract + `_compute_indicators()` pattern |
| `src/royaltdn/strategy/*.py` (17 files) | Modified | `explain()` + `_compute_indicators()` per strategy |
| `src/royaltdn/scanner/scanner.py` | Modified | `scan(verbose=)` param, `explain_all()`, verbose log writer |
| `src/royaltdn/orchestrator.py` | Modified | Dynamic interval calc from strategies, interval warning |
| `src/royaltdn/main.py` | Modified | `--verbose` flag, `cmd_check_readiness()` |
| `src/royaltdn/frontend/menu/app.py` | Modified | Scanner L1/L2 UI, KPI interval, scalping notify, Logs filter |
| `tests/test_fase18_4_scanner_verbose.py` | New | Test explain(), verbose scan, interval calc, readiness check |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Logic duplication: `generate_signal()` vs `explain()` | **High** | Extract `_compute_indicators()` — 17 strategies × 2 methods = 34 impls, catch duplication in review |
| ~800+ lines across 17 strategies + scanner + UI > 400 budget | **High** | Force-chained: PR1=check-readiness (standalone), PR2=explain() on base+3 strategies+scanner, PR3=remaining 14 strategies, PR4=UI rewrite+interval+scalping-disable |
| `explain()` diverging from actual `generate_signal()` logic | Medium | Tests: `explain()` conditions must produce same signal as `generate_signal()` |
| Interval override ignored if user sets SCANNER_INTERVAL_MINUTES | Low | Env var has priority — documented, no runtime override |

## Rollback Plan

Revert by PR reverse order: PR4 (UI) → PR3 (strategies) → PR2 (explain base) → PR1 (check-readiness). No data migration. `scanner_verbose.log` is append-only — safe to leave. If `explain()` causes import errors, revert base.py first (breaks all explain, generate_signal unaffected).

## Dependencies

- BaseStrategy with `category` attr and `_PROFILES` pattern (FASE 18.2/18.3 — already in main)
- 17 strategy files with `generate_signal(symbol=)` + `_PROFILES` (FASE 18.3 — already merged)
- `_cycle_universe()` + `set_universe_setter` in app.py (FASE 17.5 — already merged)

## Success Criteria

- [ ] `explain()` returns indicator conditions (name, met, value, threshold, gap_pct, direction) + signal info for all 17 strategies
- [ ] `scan(verbose=True)` writes `logs/scanner_verbose.log` with per-symbol strategy explanations
- [ ] Scanner UI shows L1 compact view with closeness bars; 'E' shows L2 decision tree with checkmarks/gaps; ↑/↓ navigation between symbols
- [ ] Logs screen filter "verbose" shows only verbose log lines
- [ ] `--verbose` flag in CLI activates verbose mode
- [ ] Interval auto-adjusts: scalping→2min, intraday→15min, swing→240min, none→60min; env var override respected
- [ ] Dashboard KPI shows "Scan: cada Xmin"; Scanner shows "Intervalo: X min"
- [ ] Universe change to etfs/sp500/auto-disables scalping strategies in strategies.json; "🔴 Scalping desactivado" notification shown
- [ ] `python -m royaltdn check-readiness` shows Rich Panel with 7 checks + verdict
- [ ] All tests pass: explain() + generate_signal() consistency, interval calc, readiness checks
