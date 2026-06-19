# Proposal: FASE 11 — Mejoras del menú interactivo — 15 funcionalidades + corrección de PAUSADO

## Intent

Menú Fase 10 no refleja "PAUSADO" y carece de características profesionales. 15 mejoras + corrección para producción.

## Scope

### In Scope
- **PAUSADO**: Header y Control muestran estado correcto
- **Estrategias**: Parámetros en tabla, toggle activo, eliminar, editar builder, vista unificada, backtest rápido
- **Dashboard**: Auto-refresh configurable + badges notificación
- **Trades**: Filtro fecha, rendimiento por estrategia, export CSV/JSON, stats avanzadas
- **Control**: Alertas configurables (alert_thresholds.json)
- **Op. 7**: Simulación What-if (modificar riesgo, re-backtest, comparar)
- **Op. 8**: Visor actividad con `_log_activity()`

### Out of Scope
- Web/mobile UI, Textual TUI, API REST, motor backtesting, nuevas fuentes datos, BD persistente

## Capabilities

### New Capabilities
- `what-if-simulation`: Modificar riesgo, re-backtest, comparar resultados
- `activity-logging`: Registro estructurado de actividad + visor paginado

### Modified Capabilities
- `interactive-menu`: Dashboard (auto-refresh, badges), Estrategias (CRUD + builder edit + backtest rápido), Trades (filtros, export, stats), Control (alertas)

## Approach

- **PAUSADO**: `orchestrator.py` escribe `bot_status: "PAUSADO"`; `_print_header()` y `_show_control()` detectan y renderizan amarillo
- **Estrategias**: StrategyStore CRUD reusado. Builder acepta `existing_config` para edit. Toggle escribe `active` field; orchestrator filtra. Backtest rápido reusa `run_backtest()`
- **Dashboard**: Loop con `time.sleep(N)` + countdown. Badges via mtime de archivos señal
- **Trades**: Filtros datetime. Export csv/json stdlib. Stats con pandas agrupado
- **Alertas**: Leer/escribir `alert_thresholds.json` con validación
- **Simulación**: Clonar config, modificar risk, `run_backtest()`, tabla comparativa
- **Actividad**: `_log_activity()` append a `user_activity.log`; visor con paginación

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/frontend/menu/app.py` | Modified | ~15 cambios + 2 nuevas opciones |
| `src/royaltdn/orchestrator.py` | Modified | PAUSADO, active filter, log_activity |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Builder refactoring (edit mode) | Medium | Thread `existing_config` param |
| Concurrencia menu+orchestrator | Low | Atomic writes, StateLoader TTL |
| numpy/pandas ausentes | Low | Graceful import error handling |

## Rollback Plan

`git revert` merge commit. Eliminar `alert_thresholds.json` si existe. Sin migración irreversible.

## Dependencies

Ninguna nueva. Reusa pandas, numpy, Rich, StateLoader, StrategyStore, `run_backtest()`.

## Success Criteria

- [ ] PAUSADO en amarillo al pausar; ONLINE al reanudar
- [ ] Estrategias: toggle, delete, edit con precarga, unified view, quick backtest
- [ ] Dashboard: auto-refresh Ns con countdown, badges en menú
- [ ] Trades: filtro fecha, export CSV/JSON, stats sin crash
- [ ] Alertas: leer/escribir alert_thresholds.json desde menú
- [ ] Op. 7: what-if corre backtest modificado y muestra comparativa
- [ ] Op. 8: visor paginado con actividad registrada
