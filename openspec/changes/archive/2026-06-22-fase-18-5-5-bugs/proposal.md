# Proposal: FASE 18.5 — 5 Bugs + Verificación de Integración

## Intent

Corregir 3 bugs confirmados de FASE 18.4 que afectan la experiencia del scanner y la gestión del universo. Bug 1 (universo incorrecto) es el más crítico porque el usuario ve "all" toda la operativa. Bug 3 (verbose sin datos) y Bug 5 (sin toggle verbose) son UX blockers para usuarios que usan `--verbose`.

## Scope

### In Scope
- Bug 1: Limpiar duplicados `SCANNER_UNIVERSE` en `.env` + sincronizar `_current_universe` desde el scanner en startup
- Bug 3: Ejecutar scan inicial no-bloqueante al startup cuando `--verbose` está activo
- Bug 5: Agregar handler `'v'` en `_show_scanner` (modo normal) y en `_render_verbose_dashboard` (modo verbose) para togglear `_scanner.verbose`
- Bug 2: Se corrige automáticamente al resolver Bug 1 (dependencia)
- Verificación: suite de 30+ pruebas manuales Given/When/Then

### Out of Scope
- Bug 4 (rechazado en exploration — no existe auto-scan al startup)
- Nuevas features o cambios de especificación
- Refactor de pipeline de ejecución o arquitectura de scanners

## Capabilities

### New Capabilities
None — bug fixes only, no new spec-level behavior.

### Modified Capabilities
None — all fixes align implementation with existing specs (universe.md, scanner-verbose/spec.md).

## Approach

PR único de ~150-200 líneas con 3 fixes atómicos y suite de verificación. Orden de implementación:

1. **Bug 1**: Editar `.env` (eliminar líneas 24-26 duplicadas, dejar `SCANNER_UNIVERSE=crypto`) + en `app.py` cambiar `_current_universe: str = "all"` a leer desde `os.getenv("SCANNER_UNIVERSE", "all")` al startup.
2. **Bug 5**: Agregar handler `'v'` en `_show_scanner` (toggle antes del prompt "Forzar escaneo") y en `_render_verbose_dashboard` (toggle en el loop L1).
3. **Bug 3**: En `main.py`, después de `scanner.verbose = verbose`, si `verbose=True` lanzar `threading.Thread(target=scanner.scan, kwargs={"verbose": True}, daemon=True).start()` para poblar `_last_explanations` sin bloquear startup.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `.env` | Modified | Eliminar líneas duplicadas de `SCANNER_UNIVERSE` (24-26) |
| `src/royaltdn/frontend/menu/app.py` | Modified | Bug 1: inicializar `_current_universe` desde env. Bug 5: handler `'v'` en scanner |
| `src/royaltdn/main.py` | Modified | Bug 3: scan inicial no-bloqueante cuando `--verbose` está activo |
| `src/royaltdn/scanner/scanner.py` | None | Escaneo asíncrono, `scan()` acepta `verbose=True` sin cambios |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Bug 3: scan inicial tarda demasiado y satura CPU | Low | Usar `daemon=True` + timeout implícito (no `join()`) |
| Bug 1: leer env al startup rompe ciclo de universo | Low | Solo lectura inicial; `_cycle_universe` mantiene su lógica actual |
| Bug 5: handler 'v' conflictivo con otras teclas | Low | Usar tecla dedicada, sin overlap con j/k/e/s/0 |

## Rollback Plan

Revertir cambios en `app.py` y `main.py` con `git revert`. `.env` requiere restauración manual (se edita fuera del repo, no trackeado). La verificación completa se ejecuta después de los fixes y no requiere rollback.

## Dependencies

- Ninguna externa. Los 3 fixes son autónomos dentro del código existente.
- Bug 1 debe completarse antes de verificar Bug 2 (consecuencia automática).

## Success Criteria

- [ ] `_current_universe` refleja `SCANNER_UNIVERSE` real al abrir el menú
- [ ] `'v'` togglea verbose mode en scanner (modo normal y verbose dashboard)
- [ ] `_last_explanations` se puebla automáticamente cuando `--verbose` está activo
- [ ] Suite de verificación pasa 30+ pruebas manuales sin regresiones
- [ ] Todos los tests unitarios existentes pasan
