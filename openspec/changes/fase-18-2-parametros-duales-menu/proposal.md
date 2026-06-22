# Proposal: FASE 18.2 — Parámetros duales crypto/stocks + Reorganización visual del menú

## Intent

El bot opera hoy con un único set de parámetros por estrategia, pero crypto y stocks requieren perfiles distintos (crypto más agresivo, stocks más conservador). Sin esta distinción, las señales son subóptimas en uno de los dos mercados. Además, el menú de estrategias es plano y sin categorías — al crecer a 15+ estrategias en FASE 18.3, será inmanejable. Esta propuesta introduce parámetros duales por mercado y reorganiza el listado visualmente.

## Scope

### In Scope
1. **Dual params**: SMA Crossover (crypto: 7/25, stocks: 5/20), Bollinger RSI (crypto: 15/2.5/10/25/75/20, stocks: 20/2.0/14/30/70/30), Momentum ATR (crypto: 15/14/4.0/3, stocks: 20/20/2.0/5)
2. **Category system**: `category` attr en BaseStrategy + "swing" en las 3 estrategias existentes
3. **Menu reorg**: `_show_estrategias` con secciones coloreadas (🔵 SWING, espacio para 🟢 SCALPING y 🟡 INTRADÍA)
4. **Universe quick-select**: Tecla 'U' en main menu para cambiar universo sin navegar a Control
5. **Scanner integration**: Pasar `symbol` a `generate_signal()` para selección de perfil

### Out of Scope
- Creación de 12 nuevas estrategias (FASE 18.3)
- Timeframe dinámico por mercado para el scanner (requiere cambios en batch download)
- Estrategias de usuario (DynamicStrategy) — no se modifican

## Capabilities

### New Capabilities
- `universe-quick-select`: Cambio rápido de universo de escaneo sin navegación por submenús

### Modified Capabilities
- `interactive-menu`: Tabla de estrategias categorizada con colores; tecla 'U' agregada al menú principal
- `strategy-execution`: `generate_signal()` recibe `symbol` opcional para seleccionar perfil de parámetros por mercado

## Approach

1. **BaseStrategy**: Agregar `category: str = "swing"` como atributo de clase en `__init__`. Extender `generate_signal(data, symbol=None)` con parámetro opcional.
2. **Estrategias concretas**: Cada estrategia almacena dos perfiles de parámetros (`_params_crypto`, `_params_stocks`). En `generate_signal()`, usa `is_crypto_symbol()` para seleccionar perfil si `symbol` está presente; defaults a perfil stocks.
3. **Scanner**: Pasar `symbol` a `strategy.generate_signal(data, symbol=symbol)` (cambio mínimo, compatibilidad retroactiva).
4. **Menu**: `_show_estrategias()` agrupa por `category` con secciones Rich Table coloreadas. `_print_menu()` agrega opción 'U' antes del 0.
5. **main.py**: Pasar `category` en instanciación de estrategias (default "swing").

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/strategy/base.py` | Modified | `category` attr + `symbol` param en `generate_signal()` |
| `src/royaltdn/strategy/sma_strategy.py` | Modified | Perfiles duales, `symbol` routing |
| `src/royaltdn/strategy/bollinger_rsi.py` | Modified | Perfiles duales, `symbol` routing |
| `src/royaltdn/strategy/momentum_atr.py` | Modified | Perfiles duales, `symbol` routing |
| `src/royaltdn/scanner/scanner.py` | Modified | Pasar `symbol` a `generate_signal()` |
| `src/royaltdn/frontend/menu/app.py` | Modified | Categorías en tabla + tecla 'U' |
| `src/royaltdn/main.py` | Modified | Instanciación con category |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Backward compat de `generate_signal(symbol=None)` | Low | Parámetro opcional con default → llamadas existentes no se rompen |
| Parámetro `category` no usado por DynamicStrategy | Low | `BaseStrategy.__init__()` asigna default — estrategias existentes heredan sin cambio |
| get_parameters() con perfiles duales (confusi n visual) | Medium | `get_parameters()` retorna ambos perfiles con prefijo `crypto_` / `stocks_` |

## Rollback Plan

Revert commits de los 7 archivos afectados. Si hay cambios intermedios (FASE 18.3), revertir por archivo: `base.py` y `scanner.py` primero (restauran interface), luego estrategias, luego menú. Sin migración de datos involucrada.

## Dependencies

- `is_crypto_symbol()` ya existe en `src/royaltdn/scanner/universe.py` — sin cambios necesarios

## Success Criteria

- [ ] `generate_signal(data, symbol="BTC/USD")` usa perfil crypto y produce parámetros esperados
- [ ] `generate_signal(data)` sin symbol usa perfil stocks (backward compat)
- [ ] Menú de estrategias muestra secciones 🔵 SWING / 🟢 SCALPING / 🟡 INTRADÍA con colores
- [ ] Tecla 'U' cambia universo sin errores
- [ ] Scanner produce señales con ambos perfiles según el símbolo
