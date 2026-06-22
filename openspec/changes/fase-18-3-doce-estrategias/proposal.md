# Proposal: FASE 18.3 — 12 (13) nuevas estrategias Scalping, Intraday, Swing

## Intent

El bot tiene hoy 3 estrategias swing (sma_crossover, bollinger_rsi, momentum_atr). Las categorías 🟢 SCALPING y 🟡 INTRADÍA están vacías, y swing tiene solo 3 opciones. Sin más estrategias, el scanner no puede diversificar señales por perfil de trading ni cubrir distintos horizontes temporales. Esta propuesta agrega 13 estrategias distribuidas en las 3 categorías, más la corrección crítica de propagación de `category` en el orquestador — sin la cual ninguna estrategia se mostraría en su categoría correcta en el menú.

## Scope

### In Scope
1. **13 nuevas estrategias**: 5 scalping (1min crypto / 3-5min stocks), 5 intraday (15min crypto / 1H stocks), 3 swing (1d)
2. **Fix orchestrator**: `_build_strategies_list()` debe incluir `category` en el dict — hoy omite el campo, todo cae a "swing"
3. **Registro manual en main.py**: imports, instanciaciones, defaults de `STRATEGIES_ENABLED`
4. **Tests parametrizados**: 1 archivo con cobertura de todas las estrategias (instanciación, generate_signal, get_parameters, validate)

### Out of Scope
- Auto-descubrimiento de estrategias (sigue siendo manual en main.py)
- Timeframe dinámico por mercado en scanner (depende de batch download)
- Estrategias de usuario (DynamicStrategy) — no se modifican
- Refactor de `_build_strategies_list()` (solo se agrega el campo faltante)

## Capabilities

### New Capabilities
- Ninguna — las 3 capabilities ya existen

### Modified Capabilities
- `strategy-execution`: 13 nuevas implementaciones de `BaseStrategy` en categorías scalping, intraday y swing
- `interactive-menu`: Corrección en orquestador para que `category` se propague a `strategies.json` y el menú agrupe correctamente por categoría

## Approach

1. **Template de estrategia**: Copiar patrón de `momentum_atr.py` — `_PROFILES` dict, `__init__(category=)`, `generate_signal(data, symbol=None)` con resolución local de perfil, `get_parameters(symbol=None)` con three-way branch, `name` property, `validate()`
2. **Orchestrator fix**: Agregar `"category": getattr(strategy, 'category', 'swing')` en `_build_strategies_list()` tanto para scanner strategies como para fallback y user strategies
3. **main.py**: Agregar imports + 13 `if "name" in strategies_enabled: strategies["name"] = ClassName(category=...)` blocks, más defaults actualizados en `STRATEGIES_ENABLED`
4. **Tests**: 1 archivo parametrizado con `@pytest.mark.parametrize` que prueba cada estrategia con datos sintéticos OHLCV

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/strategy/scalping_momentum.py` | **New** | Scalping momentum, TF: crypto 1min / stocks 3min |
| `src/royaltdn/strategy/scalping_breakout.py` | **New** | Scalping breakout, TF: crypto 1min / stocks 5min |
| `src/royaltdn/strategy/scalping_reversion.py` | **New** | Scalping mean reversion, TF: crypto 1min / stocks 3min |
| `src/royaltdn/strategy/scalping_orderflow.py` | **New** | Scalping order flow, TF: crypto 1min / stocks 5min |
| `src/royaltdn/strategy/scalping_spread.py` | **New** | Scalping spread mean reversion, TF: crypto 1min / stocks 5min |
| `src/royaltdn/strategy/intraday_trend.py` | **New** | Intraday trend following, TF: crypto 15min / stocks 1H |
| `src/royaltdn/strategy/intraday_vwap.py` | **New** | Intraday VWP reversion, TF: crypto 15min / stocks 1H |
| `src/royaltdn/strategy/intraday_volume_breakout.py` | **New** | Intraday volume breakout, TF: crypto 15min / stocks 1H |
| `src/royaltdn/strategy/intraday_support_resistance.py` | **New** | Intraday S/R, TF: crypto 15min / stocks 1H |
| `src/royaltdn/strategy/intraday_macd_divergence.py` | **New** | Intraday MACD divergence, TF: crypto 15min / stocks 1H |
| `src/royaltdn/strategy/swing_trend_following.py` | **New** | Swing trend following, TF: 1d |
| `src/royaltdn/strategy/swing_reversion.py` | **New** | Swing mean reversion, TF: 1d |
| `src/royaltdn/strategy/swing_breakout.py` | **New** | Swing breakout, TF: 1d |
| `src/royaltdn/orchestrator.py` | **Modified** | Fix `_build_strategies_list()` — agregar `category` al dict |
| `src/royaltdn/main.py` | **Modified** | Agregar imports, instanciaciones, defaults STRATEGIES_ENABLED |
| `tests/test_fase18_3_doce_estrategias.py` | **New** | Tests parametrizados (instanciación, señal, params, validación) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Review size ~900 líneas > 400 budget | **High** | Force-chained PRs: PR1 = category fix + template testing + 5 scalping; PR2 = 5 intraday; PR3 = 3 swing + main.py + tests |
| Categorías no se ven en menú sin el fix de orchestrator | **High** | El fix es PR1, prioridad máxima — se mergea primero y se verifica en isolation |
| Estrategias boilerplate-heavy, lógica repetitiva | Medium | Template pattern + test parametrizado reduce el riesgo de errores por copia |
| `get_parameters(symbol=None)` no incluye category en retorno | Low | Incluir `"category": self._category` en ambos branches del three-way |

## Rollback Plan

Revertir por PR: PR3 → PR2 → PR1. Sin migración de datos. Si hay cambios posteriores, revertir orchestrator.py primero (libera la categorización), luego main.py (quita registros), luego strategy files.

## Dependencies

- `BaseStrategy` con `category` attr (FASE 18.2 — ya en main)
- `_show_estrategias()` con lógica de categorías (FASE 18.2 — ya en app.py)

## Success Criteria

- [ ] Cada estrategia se instancia con su categoría correcta (`scalping`, `intraday`, `swing`)
- [ ] `generate_signal(data, symbol="BTC/USDT")` produce señal con perfil crypto
- [ ] `generate_signal(data, symbol="AAPL")` produce señal con perfil stocks
- [ ] `_build_strategies_list()` incluye `"category"` en cada entrada de `strategies.json`
- [ ] Menú muestra estrategias agrupadas bajo 🟢 SCALPING / 🟡 INTRADÍA / 🔵 SWING
- [ ] `get_parameters(symbol=None)` retorna ambos perfiles con prefijos `crypto_`/`stocks_` + `category`
- [ ] `validate()` pasa para todas las estrategias con defaults
- [ ] Tests parametrizados pasan para las 13 estrategias
