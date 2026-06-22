# Scanner Verbose Specification

## Purpose

Add `explain()` to every strategy so users see WHY a signal was (or was not) generated, with a two-level UI showing compact closeness bars per strategy per symbol and full decision-tree condition tables. Output to `logs/scanner_verbose.log` and activated via `--verbose` CLI flag.

## Requirements

### Requirement 1: explain() abstract method on BaseStrategy

The system MUST define a new abstract method `explain(self, data: pd.DataFrame) -> Dict[str, Any]` on `BaseStrategy`.

The returned dict MUST contain:
- `"indicators"`: dict of computed indicator values (strategy-specific, e.g. `{"sma_fast": 150.25, "sma_slow": 148.10}`)
- `"conditions"`: list of dicts, each with keys `name` (str), `met` (bool), `value` (float), `threshold` (float), `gap_pct` (float, 0.0 when met), `direction` (str, `"above"` or `"below"`)
- `"signal"`: `None` if no signal, or dict with keys `action` ("buy"/"sell"/"hold"), `price` (float), `reason` (str)

#### Scenario: explain() returns structured result on triggered signal
- GIVEN a strategy instance with computed indicators exceeding threshold
- WHEN `explain(data)` is called
- THEN the returned dict has `"indicators"` with at least one key AND `"conditions"` has at least one entry where `met` is `True` AND `"signal"` is not None with `action` equal to the expected signal

#### Scenario: explain() returns structured result when no signal
- GIVEN a strategy instance with indicators below threshold
- WHEN `explain(data)` is called
- THEN the returned dict has at least one `"conditions"` entry where `met` is `False` AND `"signal"` is `None`

#### Scenario: gap_pct calculation is correct
- GIVEN a condition with `value=100`, `threshold=110`, `direction="above"`
- WHEN `explain(data)` computes gap
- THEN `gap_pct` equals `abs((100 - 110) / 110) * 100` (9.09% below threshold)

### Requirement 2: _compute_indicators() extraction pattern

Each concrete strategy that implements `generate_signal()` SHOULD extract indicator computation into `_compute_indicators(data: pd.DataFrame) -> Dict[str, Any]`.

`generate_signal()` SHALL call `self._compute_indicators(data)` and then apply its logic gates. `explain()` SHALL call `self._compute_indicators(data)` and compare each condition individually.

#### Scenario: generate_signal() delegates to _compute_indicators()
- GIVEN a strategy implementing `_compute_indicators()`
- WHEN `generate_signal(data)` is called
- THEN the strategy internally calls `_compute_indicators(data)` and uses the returned dict for signal logic

#### Scenario: explain() delegates to _compute_indicators()
- GIVEN a strategy implementing `_compute_indicators()`
- WHEN `explain(data)` is called
- THEN the strategy internally calls `_compute_indicators(data)` and builds conditions from each computed value against its threshold

### Requirement 3: scan(verbose=True) behavior

The `Scanner.scan()` method MUST accept a `verbose: bool = False` parameter.

When `verbose=True`, after computing `generate_signal()` for each (strategy, symbol) pair, the scanner SHALL call `strategy.explain(data)` and store the result in `self._last_explanations[strategy.name][symbol]`.

#### Scenario: verbose scan stores explanations
- GIVEN a scanner with 3 strategies and 2 symbols
- WHEN `scan(verbose=True)` is called
- THEN `self._last_explanations` has 3 strategy keys, each with 2 symbol keys, each containing an explain() dict

#### Scenario: non-verbose scan does not store
- GIVEN a scanner
- WHEN `scan(verbose=False)` is called (default)
- THEN `self._last_explanations` is unchanged or empty

### Requirement 4: Verbose log file

When `scan(verbose=True)` completes, the system SHALL append a formatted entry to `logs/scanner_verbose.log`.

Each entry SHALL include an ISO-8601 timestamp, the symbol, strategy name, signal action (or "NO SIGNAL"), and summary of condition results (met count / total).

#### Scenario: verbose log written on scan
- GIVEN `scan(verbose=True)` produces explanations for 2 symbols × 3 strategies
- WHEN the scan cycle ends
- THEN `logs/scanner_verbose.log` contains 6 entries (one per strategy per symbol) with timestamps

### Requirement 5: Manual scan via 's' key

When the user presses 's' in the Scanner screen, the system SHALL call `trigger_scanner()` and then re-render the Scanner screen with the updated results.

If verbose mode is active (via `--verbose` flag), the manual scan SHALL also call `scan(verbose=True)` and populate `self._last_explanations`.

#### Scenario: manual scan in verbose mode refreshes explanations
- GIVEN user is on Scanner screen with `--verbose` active
- WHEN user presses 's'
- THEN `trigger_scanner()` is called AND `scan(verbose=True)` populates explanations AND screen re-renders

### Requirement 6: UI Level 1 — Compact Dashboard

The Scanner screen SHALL render a Per-Symbol Panel when verbose mode is active.

Each symbol panel SHALL contain:
- A Rich `Table` with columns: strategy name, key indicator value(s), closeness bar, indicator color
- Closeness bar: filled `█` characters proportional to how close the value is to threshold (10 segments)
- Indicator color: green when signal active, yellow when >70% of threshold, red when <=70%
- Navigation: `↑`/`↓` select symbol, `E` expand to Level 2, `0` back

#### Scenario: L1 shows per-panel strategy rows with bars
- GIVEN scanner has explanations for symbol "SPY" with 3 strategies
- WHEN Scanner L1 renders
- THEN "SPY" panel shows 3 rows, each with strategy name, indicator value, a closeness bar, and a colored indicator

#### Scenario: navigation between symbols
- GIVEN 5 symbols with explanations
- WHEN user presses `↓`
- THEN focus moves to the next symbol panel

### Requirement 7: UI Level 2 — Decision Tree

When user presses 'E' on a selected symbol, the system SHALL render a detailed table per strategy for that symbol.

Each strategy table SHALL show: condition name, real value, threshold, ✅/❌ indicator, gap percentage if condition not met.

If all conditions for a strategy are met (signal generated), the table footer SHALL show `"🟢 SEÑAL BUY/SELL generada a $X.XX"`.

#### Scenario: L2 shows condition details
- GIVEN symbol "SPY" with 2 strategies, one with signal and one without
- WHEN user presses 'E' on SPY
- THEN two tables render: first shows all ✅ with signal line, second shows ❌ on failed conditions with gap % AND no signal line

#### Scenario: L2 exit back to L1
- GIVEN user is viewing L2 for a symbol
- WHEN user presses `0` or `Escape`
- THEN display returns to L1 compact dashboard

### Requirement 8: Log filter for "verbose"

The Logs screen (`_show_logs()`) MUST support a new filter option `"verbose"` that searches `logs/scanner_verbose.log` instead of the main log buffer.

#### Scenario: verbose filter loads verbose log
- GIVEN user selects "verbose" from log filter options
- WHEN `_show_logs()` renders
- THEN lines from `logs/scanner_verbose.log` are displayed instead of main log lines

### Requirement 9: --verbose CLI flag

The CLI SHALL support a `--verbose` flag. When set, the scanner SHALL operate in verbose mode by default (auto-scans produce verbose output, manual scans show L1/L2 UI).

#### Scenario: --verbose flag activates verbose
- GIVEN `python -m royaltdn --verbose` is executed
- WHEN the scanner runs its first auto-scan
- THEN `scan(verbose=True)` is called AND `self._last_explanations` is populated

### Requirement 10: Background scan at startup when --verbose is active

When `--verbose` is active, the system MUST start a non-blocking scan daemon at startup to populate `_last_explanations` before the user enters the Scanner screen.

#### Scenario: verbose runs background scan
- GIVEN `--verbose` is set
- WHEN `main.py` initializes
- THEN `threading.Thread(target=scanner.scan, kwargs={"verbose": True}, daemon=True)` starts
- AND startup proceeds without blocking (no `.join()`)

#### Scenario: verbose inactive skips scan
- GIVEN `--verbose` is NOT set
- WHEN `main.py` initializes
- THEN no background scan thread is started

### Requirement 11: 'v' key toggles verbose mode in Scanner UI

Scanner screen MUST toggle `scanner.verbose` when `'v'` is pressed. The handler SHALL be consumed within `_show_scanner()` — shall NOT bubble to menu dispatch.

#### Scenario: toggle on
- GIVEN user on scanner screen, verbose OFF
- WHEN user presses `'v'`
- THEN `self._scanner.verbose` toggles to `True` AND screen re-renders with verbose dashboard

#### Scenario: toggle off
- GIVEN user on scanner screen, verbose ON
- WHEN user presses `'v'`
- THEN `self._scanner.verbose` toggles to `False` AND screen re-renders without verbose dashboard

#### Scenario: 'v' consumed by scanner (no dispatch)
- GIVEN user on scanner screen
- WHEN user presses `'v'`
- THEN no main menu option is triggered AND scanner screen remains active

### Requirement 12: Verbose dashboard handles mid-session state

When verbose is toggled ON mid-session, dashboard MUST show explanations or a loading state.

#### Scenario: explanations available
- GIVEN `_last_explanations` is populated
- WHEN `_render_verbose_dashboard()` renders
- THEN strategy tables with indicator values and closeness bars are shown

#### Scenario: explanations empty (no scan yet)
- GIVEN `_last_explanations` is empty
- WHEN `_render_verbose_dashboard()` renders
- THEN message `"No hay datos verbose aún — presiona 's' para escanear"` is displayed
