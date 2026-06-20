# Scanner — Delta Specification

## ADDED Requirements

### Requirement: RQ-SC-01 — Progress bar in LiquidityFilter.filter()

SHALL display a `tqdm` progress bar during `LiquidityFilter.filter()` execution.

#### Scenario: Progress bar shows during filter

- GIVEN `LiquidityFilter.filter()` is called with 500 symbols
- WHEN the filter loop iterates over each symbol
- THEN a tqdm progress bar is displayed with `desc="Filtrando por liquidez: {n}/{total} — {pct:.0f}% completado. ~{eta}"`
- AND total = 500

#### Scenario: Empty symbol list

- GIVEN `LiquidityFilter.filter()` is called with an empty list
- WHEN the filter runs
- THEN an empty list is returned
- AND a progress bar may appear briefly showing 0/0

#### Scenario: All symbols fail liquidity check

- GIVEN 100 symbols, none passing the liquidity filter
- WHEN `filter()` completes
- THEN the progress bar reaches 100/100
- AND an empty list is returned

#### Scenario: KeyboardInterrupt during filter

- GIVEN a long-running filter operation
- WHEN the user presses Ctrl+C
- THEN execution stops gracefully


### Requirement: RQ-SC-02 — Progress bar in Scanner.scan()

SHALL display a `tqdm` progress bar during the scan loop in `Scanner.scan()`.

#### Scenario: Progress bar shows during scan

- GIVEN `Scanner.scan()` is scanning 200 symbols that passed liquidity filter
- WHEN the scan loop iterates
- THEN a tqdm progress bar is displayed with `desc="Escaneando {symbol}: {n}/{total} — {pct:.0f}% completado. ~{eta}"`
- AND total = 200

#### Scenario: No symbols passed liquidity filter

- GIVEN `Scanner.scan()` with 500 symbols where none passed liquidity filter
- WHEN the scan loop starts
- THEN no scan progress bar is shown (total = 0 symbols to scan)
- AND the result is an empty signals list

#### Scenario: Mixed success — some symbols error

- GIVEN `Scanner.scan()` scanning 50 symbols where 5 raise exceptions in `_get_symbol_data()`
- WHEN the scan completes
- THEN the progress bar reaches 50/50
- AND only the 45 successful symbols produce signals
- AND errors are logged independently (not interrupting the progress bar)

#### Scenario: Single symbol scan

- GIVEN exactly 1 symbol passes liquidity filter
- WHEN the scan loop runs
- THEN the progress bar shows 1/1


### Requirement: RQ-SC-03 — Post-scan metrics panel

SHALL show a Rich Panel with execution metrics after scan completion.

#### Scenario: Metrics displayed after scan

- GIVEN `Scanner.scan()` completed processing 500 symbols (200 passed liquidity, 45 signals generated, elapsed = 30.5s)
- WHEN the scan finishes
- THEN a Rich Panel titled `"📊  Resultados del Escaneo"` is displayed with:
  - `Total símbolos escaneados: 500`
  - `Pasaron filtro de liquidez: 200/500 (40%)`
  - `Señales generadas: 45`
  - `Tiempo total: 30.5s`

#### Scenario: No signals generated

- GIVEN a scan that completed with 0 signals generated
- WHEN the metrics panel is rendered
- THEN it shows `Señales generadas: 0`

#### Scenario: All symbols pass but no signals

- GIVEN 100 symbols, all pass liquidity filter, but none generate signals
- WHEN the metrics panel is rendered
- THEN it shows `Pasaron filtro de liquidez: 100/100 (100%)` and `Señales generadas: 0`

#### Scenario: Very fast scan (< 1 second)

- GIVEN a scan that completes in 0.3 seconds
- WHEN the metrics panel is rendered
- THEN `Tiempo total: 0.3s` is shown (1 decimal place)


### Requirement: RQ-SC-04 — Initial ETA message before scan

SHALL display an estimated time message before the scan begins.

#### Scenario: ETA shown for 500 symbols

- GIVEN the user triggers a scan with 500 symbols
- WHEN the scan is about to begin
- THEN the message `"Escaneando 500 símbolos... ~3min restante"` is displayed
- AND estimated minutes = math.ceil(500 × 0.3 / 60) = math.ceil(2.5) = 3

#### Scenario: ETA for small symbol list (≤ 100)

- GIVEN the user triggers a scan with 50 symbols
- WHEN the scan is about to begin
- THEN the message shows `"Escaneando 50 símbolos... ~1min restante"` (since ceil(50 × 0.3 / 60) = ceil(0.25) = 1)

#### Scenario: Zero symbols

- GIVEN the user triggers a scan with an empty universe (0 symbols)
- WHEN the scan is about to begin
- THEN the message shows `"Escaneando 0 símbolos... ~0min restante"`

#### Scenario: Message does not interfere with tqdm bars

- GIVEN the initial ETA message is printed via `tqdm.write()` or `console.print()`
- WHEN the subsequent progress bars display
- THEN the ETA message does not overlap or corrupt the progress bar lines
