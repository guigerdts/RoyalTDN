# Delta for scanner-display

## MODIFIED Requirements

### REQ-DISPLAY-FIX — Menú scanner usa top_signals y tabla rankeada

`_show_scanner` in `app.py` MUST read `last_scan["top_signals"]` instead of `last_scan["symbols"]`.
- The table SHALL have columns: Symbol, Action, Price, Score, Strategy.
- The metrics panel SHALL show: total, passed, signals, elapsed time (from `scan_history[-1]`).
- After a forced scan (trigger_scanner + sleep), the screen SHALL reload and display the updated results.
- **Before rendering, SHALL filter out entries where `strategy == "mock"`.** The empty/missing check SHALL use the filtered list. When the filtered list is empty or `top_signals` is empty/missing, SHALL show an empty state message: `"No hay resultados de escaneo aún."`
- The post-scan metrics panel SHALL be shown regardless of whether top_signals is empty.
(Previously: top_signals displayed as-is without filtering mock entries; empty check only considered raw list)

#### Scenario: Tabla usa top_signals en vez de symbols

- GIVEN `last_scan` contains `{"top_signals": [{"symbol": "SPY", "action": "BUY", "price": 450.0, "score": 0.85, "strategy": "sma_crossover"}]}`
- WHEN `_show_scanner` renders the table
- THEN the table reads from `last_scan["top_signals"]`
- AND it does NOT attempt to read `last_scan["symbols"]`

#### Scenario: Tabla rankeada: Symbol, Action, Price, Score, Strategy

- GIVEN top_signals contains 2 entries
- WHEN the table is rendered
- THEN the table has 5 columns: Symbol, Action, Price, Score, Strategy
- AND each row shows the corresponding values
- AND BUY actions are styled in green, SELL in red

#### Scenario: Metrics panel se muestra después de scan forzado

- GIVEN scan_history has an entry with total_symbols=500, passed_symbols=200, signals_count=45, elapsed_seconds=30.5
- WHEN the scanner screen is shown
- THEN a Rich Panel displays:
  - "Total símbolos: 500"
  - "Pasaron filtro: 200/500 (40%)"
  - "Señales: 45"
  - "Tiempo: 30.5s"

#### Scenario: Refrescar resultados después de scan forzado

- GIVEN the user chooses to force a scan (inputs "s")
- WHEN `trigger_scanner()` completes and `time.sleep(5)` elapses
- THEN `state_loader.load_scanner_results()` is called again
- AND the table re-renders with updated `top_signals`

#### Scenario: All mock entries show empty state

- GIVEN `last_scan["top_signals"]` contains only entries with `strategy: "mock"`
- WHEN `_show_scanner` renders
- THEN mock entries are filtered out
- AND the filtered list is empty
- AND `"No hay resultados de escaneo aún."` is displayed in dim style
- AND no table is rendered

#### Scenario: Mixed real and mock entries

- GIVEN `top_signals` has 3 real entries (strategy != "mock") and 2 mock entries
- WHEN the table is rendered
- THEN only the 3 real entries appear in the table
- AND mock entries are not displayed

#### Scenario: No mock entries — unchanged behavior

- GIVEN `top_signals` has 5 real entries, none with `strategy: "mock"`
- WHEN the table is rendered
- THEN all 5 entries appear (no filtering applied)
- AND behavior is identical to pre-fix flow

#### Scenario: Empty state cuando no hay top_signals

- GIVEN `last_scan` is `{}` or `{"top_signals": []}`
- WHEN `_show_scanner` renders
- THEN the text `"No hay resultados de escaneo aún."` is displayed in dim style
- AND no table is rendered

#### Scenario: Scan history muestra datos correctos

- GIVEN `scan_history` is empty
- WHEN the screen renders
- THEN the metrics panel is NOT shown (no history to read from)

- GIVEN `scan_history` has 1 entry
- WHEN the screen renders
- THEN the metrics panel uses `scan_history[-1]` for its values

#### Scenario: Timestamp del último scan se muestra

- GIVEN `last_scan["timestamp"]` is `"2026-06-20T12:00:00+00:00"`
- WHEN the screen renders
- THEN the text `"Timestamp: 2026-06-20T12:00:00+00:00"` is displayed in cyan

#### Scenario: Símbolo inválido o faltante en top_signals

- GIVEN `top_signals` contains `{"action": "BUY", "price": 100.0, "score": 0.5, "strategy": "sma"}` without a `symbol` key
- WHEN the table row is rendered
- THEN the Symbol cell shows `"?"` as fallback

#### Scenario: Score faltante en una señal

- GIVEN `top_signals` contains `{"symbol": "AAPL", "action": "BUY", "price": 150.0}` without `score` or `strategy`
- WHEN the table row is rendered
- THEN the Score cell shows `"—"` (em dash)
- AND the Strategy cell shows `"—"` (em dash)

#### Scenario: Action column colorea BUY verde y SELL rojo

- GIVEN `top_signals` has a BUY and a SELL signal
- WHEN the table is rendered
- THEN the BUY action is displayed with green ANSI color
- AND the SELL action is displayed with red ANSI color
- AND no 24-bit hex colors are used
