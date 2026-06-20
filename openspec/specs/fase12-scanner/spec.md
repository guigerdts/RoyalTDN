# FASE 12 — Scanner: Progreso y Métricas

## Purpose

Add real-time progress bars to the scanner pipeline (liquidity filter + symbol scan) and post-execution metrics panel with timing and signal counts.

## Requirements

### RQ-SC-01 — Progress bar in LiquidityFilter.filter()

SHALL show tqdm during `LiquidityFilter.filter()` loop.

**Format:** `"Filtrando por liquidez: {n}/{total} — {pct:.0f}% completado. ~{eta}"`

#### Scenarios

##### Progress bar shows during filter
- GIVEN `LiquidityFilter.filter()` is called with 500 symbols
- WHEN the filter loop iterates over each symbol
- THEN a tqdm progress bar is displayed with `desc="Filtrando por liquidez: {n}/{total} — {pct:.0f}% completado. ~{eta}"`
- AND total = 500

##### Empty symbol list
- GIVEN `LiquidityFilter.filter()` is called with an empty list
- WHEN the filter runs
- THEN an empty list is returned
- AND a progress bar may appear briefly showing 0/0

##### All symbols fail liquidity check
- GIVEN 100 symbols, none passing the liquidity filter
- WHEN `filter()` completes
- THEN the progress bar reaches 100/100
- AND an empty list is returned

##### KeyboardInterrupt during filter
- GIVEN a long-running filter operation
- WHEN the user presses Ctrl+C
- THEN execution stops gracefully

### RQ-SC-02 — Progress bar in Scanner.scan()

SHALL show tqdm during the main scan loop over symbols that passed liquidity filter.

**Format:** `"Escaneando {symbol}: {n}/{total} — {pct:.0f}% completado. ~{eta}"`

#### Scenarios

##### Progress bar shows during scan
- GIVEN `Scanner.scan()` is scanning 200 symbols that passed liquidity filter
- WHEN the scan loop iterates
- THEN a tqdm progress bar is displayed with `desc="Escaneando {symbol}: {n}/{total} — {pct:.0f}% completado. ~{eta}"`
- AND total = 200

##### No symbols passed liquidity filter
- GIVEN `Scanner.scan()` with 500 symbols where none passed liquidity filter
- WHEN the scan loop starts
- THEN no scan progress bar is shown (total = 0 symbols to scan)
- AND the result is an empty signals list

##### Mixed success — some symbols error
- GIVEN `Scanner.scan()` scanning 50 symbols where 5 raise exceptions in `_get_symbol_data()`
- WHEN the scan completes
- THEN the progress bar reaches 50/50
- AND only the 45 successful symbols produce signals
- AND errors are logged independently (not interrupting the progress bar)

##### Single symbol scan
- GIVEN exactly 1 symbol passes liquidity filter
- WHEN the scan loop runs
- THEN the progress bar shows 1/1

### RQ-SC-03 — Post-scan metrics panel

SHALL show a Rich Panel after scan completion with:
- `Total símbolos escaneados: {N}`
- `Pasaron filtro de liquidez: {N}/{total} ({pct}%)`
- `Señales generadas: {N}`
- `Tiempo total: {X.X}s`

**Panel title:** `"📊  Resultados del Escaneo"`

#### Scenarios

##### Metrics displayed after scan
- GIVEN `Scanner.scan()` completed processing 500 symbols (200 passed liquidity, 45 signals generated, elapsed = 30.5s)
- WHEN the scan finishes
- THEN a Rich Panel titled `"📊  Resultados del Escaneo"` is displayed with:
  - `Total símbolos escaneados: 500`
  - `Pasaron filtro de liquidez: 200/500 (40%)`
  - `Señales generadas: 45`
  - `Tiempo total: 30.5s`

##### No signals generated
- GIVEN a scan that completed with 0 signals generated
- WHEN the metrics panel is rendered
- THEN it shows `Señales generadas: 0`

##### All symbols pass but no signals
- GIVEN 100 symbols, all pass liquidity filter, but none generate signals
- WHEN the metrics panel is rendered
- THEN it shows `Pasaron filtro de liquidez: 100/100 (100%)` and `Señales generadas: 0`

##### Very fast scan (< 1 second)
- GIVEN a scan that completes in 0.3 seconds
- WHEN the metrics panel is rendered
- THEN `Tiempo total: 0.3s` is shown (1 decimal place)

### RQ-SC-04 — Initial ETA message

SHALL display before scan: `"Escaneando {N} símbolos... ~{X}min restante"`

Estimate: `ceil(N × 0.3 / 60)` minutes. Use `tqdm.write()` or `console.print()` to avoid interference with tqdm bars.

#### Scenarios

##### ETA shown for 500 symbols
- GIVEN the user triggers a scan with 500 symbols
- WHEN the scan is about to begin
- THEN the message `"Escaneando 500 símbolos... ~3min restante"` is displayed
- AND estimated minutes = math.ceil(500 × 0.3 / 60) = math.ceil(2.5) = 3

##### ETA for small symbol list (≤ 100)
- GIVEN the user triggers a scan with 50 symbols
- WHEN the scan is about to begin
- THEN the message shows `"Escaneando 50 símbolos... ~1min restante"` (since ceil(50 × 0.3 / 60) = ceil(0.25) = 1)

##### Zero symbols
- GIVEN the user triggers a scan with an empty universe (0 symbols)
- WHEN the scan is about to begin
- THEN the message shows `"Escaneando 0 símbolos... ~0min restante"`

##### Message does not interfere with tqdm bars
- GIVEN the initial ETA message is printed via `tqdm.write()` or `console.print()`
- WHEN the subsequent progress bars display
- THEN the ETA message does not overlap or corrupt the progress bar lines

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
