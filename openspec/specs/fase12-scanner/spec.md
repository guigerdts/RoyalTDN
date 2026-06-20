# FASE 12 — Scanner: Progreso y Métricas

## Purpose

Add real-time progress bars to the scanner pipeline (liquidity filter + symbol scan) and post-execution metrics panel with timing and signal counts.

## Requirements

### RQ-SC-01 — Progress bar in LiquidityFilter.filter()

SHALL show tqdm during `LiquidityFilter.filter()` loop.

**Format:** `"Filtrando por liquidez: {n}/{total} — {pct:.0f}% completado. ~{eta}"`

### RQ-SC-02 — Progress bar in Scanner.scan()

SHALL show tqdm during the main scan loop over symbols that passed liquidity filter.

**Format:** `"Escaneando {symbol}: {n}/{total} — {pct:.0f}% completado. ~{eta}"`

### RQ-SC-03 — Post-scan metrics panel

SHALL show a Rich Panel after scan completion with:
- `Total símbolos escaneados: {N}`
- `Pasaron filtro de liquidez: {N}/{total} ({pct}%)`
- `Señales generadas: {N}`
- `Tiempo total: {X.X}s`

**Panel title:** `"📊  Resultados del Escaneo"`

### RQ-SC-04 — Initial ETA message

SHALL display before scan: `"Escaneando {N} símbolos... ~{X}min restante"`

Estimate: `ceil(N × 0.3 / 60)` minutes. Use `tqdm.write()` or `console.print()` to avoid interference with tqdm bars.

## Color/Style Contract

| Element | Style |
|---------|-------|
| Panel title | `bold white` |
| Metrics text | default white |
| Border | `white` |

## UI Text Contract

| Context | Spanish String |
|---------|---------------|
| Progress desc (liquidity) | `"Filtrando por liquidez: {n}/{total} — {pct:.0f}% completado. ~{eta}"` |
| Progress desc (scan) | `"Escaneando {symbol}: {n}/{total} — {pct:.0f}% completado. ~{eta}"` |
| Results panel title | `"📊  Resultados del Escaneo"` |
| Total scanned | `"Total símbolos escaneados: {n}"` |
| Liquidity passed | `"Pasaron filtro de liquidez: {n}/{total} ({pct:.0f}%)"` |
| Signals generated | `"Señales generadas: {n}"` |
| Total time | `"Tiempo total: {elapsed:.1f}s"` |
| Initial ETA | `"Escaneando {N} símbolos... ~{X}min restante"` |
