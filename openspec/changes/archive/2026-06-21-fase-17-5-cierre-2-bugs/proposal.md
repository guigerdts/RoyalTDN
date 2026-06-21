# Proposal: FASE 17.5 (CIERRE) — Corrección definitiva de los 2 bugs restantes

## Intent

Cerrar los 2 bugs que sobrevivieron al ciclo anterior de FASE 17.5 (6 bugs
corregidos). Ambos fueron detectados en pruebas con Binance Testnet y bloquean
el escaneo crypto con datos reales.

## Scope

### In Scope
- **Bug 2**: `AssetUniverse._get_default_crypto()` retorna símbolos en formato
  Alpaca (BTC/USD) incluso con Binance activo. Binance testnet espera BTCUSDT.
  Fix: hacer `_get_default_crypto()` broker-aware, retornando BTCUSDT/ETHUSDT
  cuando el broker activo es Binance. Si el DataFrame sigue vacío tras
  `broker.get_bars()`, loguear warning con el mensaje
  `"⚠️ Sin datos para {symbol}. Posiblemente el par no está disponible en el testnet."`
  Sin fallback a Alpaca.
- **Bug 7**: Caché `.pyc` impide que cambios de código se reflejen sin limpiar
  `__pycache__` manualmente. Fix: `sys.dont_write_bytecode = True` al tope de
  `src/royaltdn/__init__.py`.

### Out of Scope
- Fallback a Alpaca cuando Binance retorna DataFrames vacíos (excluido por diseño)
- Descubrimiento dinámico de pares crypto
- Limpieza de duplicados en `.env`
- Cualquier otro bug reportado y ya corregido en el ciclo anterior

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `scanner-universe`: REQ-UNIVERSE-CRYPTO — `_get_default_crypto()` debe ser
  broker-aware. Cuando el broker activo es Binance, retorna símbolos sin slash
  (BTCUSDT, ETHUSDT, LTCUSDT, etc.). Se añade un warning visible cuando
  `get_bars()` devuelve DataFrame vacío.
- `build-lifecycle`: Se deshabilita la escritura de bytecode cache (`.pyc`)
  mediante `sys.dont_write_bytecode = True` para evitar que el intérprete use
  bytecode obsoleto.

## Approach

1. **Bug 2 (universe.py)**: Modificar `_get_default_crypto()` para aceptar un
   parámetro opcional `broker_type: str = "alpaca"`. Si `broker_type == "binance"`,
   retornar `DEFAULT_CRYPTO_BINANCE` (BTCUSDT, ETHUSDT, LTCUSDT, BCHUSDT,
   LINKUSDT, UNIUSDT, AAVEUSDT, MATICUSDT, DOGEUSDT, SHIBUSDT). El caller
   (`main.py`) pasa el tipo activo.
2. **Bug 2 (filters.py)**: En `LiquidityFilter.filter()`, cuando `df.empty` tras
   `crypto_broker.get_bars()`, loguear `logger.warning()` con el mensaje en
   español y continuar (skip). Sin fallback.
3. **Bug 7 (__init__.py)**: Agregar `import sys; sys.dont_write_bytecode = True`
   como primeras líneas ejecutables del archivo.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/scanner/universe.py` | Modified | `_get_default_crypto()` broker-aware + nueva constante `DEFAULT_CRYPTO_BINANCE` |
| `src/royaltdn/scanner/filters.py` | Modified | Warning visible cuando broker crypto retorna DataFrame vacío |
| `src/royaltdn/__init__.py` | Modified | `sys.dont_write_bytecode = True` |
| `src/royaltdn/main.py` | Modified | Pasar broker_type a `AssetUniverse.get_symbols()` (o al constructor) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Broker detection errada retorna símbolos equivocados para Alpaca | Low | Detección por presencia de `BINANCE_API_KEY` en env; default Alpaca |
| Formato Binance no coincide con lo que espera BinanceBroker.get_bars() | Low | Validar en test manual contra testnet |

## Rollback Plan

Revert commits individualmente:
- `git revert <commit-bug7>` para `.pyc` si causa problemas de rendimiento
  (inusual pero trivial)
- `git revert <commit-bug2>` para símbolos crypto si la detección de broker
  Produce falsos positivos
Ambos cambios son independientes y pueden revertirse por separado.

## Dependencies

None — cambios autónomos sin dependencias externas.

## Success Criteria

- [ ] `SCANNER_UNIVERSE=crypto` con Binance activo retorna símbolos BTCUSDT,
      ETHUSDT, etc. (sin slash)
- [ ] `SCANNER_UNIVERSE=crypto` sin Binance (Alpaca solamente) retorna
      BTC/USD, ETH/USD, etc. (con slash, comportamiento actual)
- [ ] Cuando `broker.get_bars()` retorna DataFrame vacío para un símbolo crypto,
      se loguea warning visible: `"⚠️ Sin datos para BTCUSDT..."` y el símbolo
      se salta (no falla, no crashea)
- [ ] `python -m royaltdn <comando>` ya no genera archivos `.pyc` en `__pycache__/`
- [ ] Cambios de código en `src/royaltdn/` se reflejan sin necesidad de limpiar
      caché manualmente
