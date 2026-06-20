# Integration — Specification

## Purpose

Wire all FASE-13 changes together: auto-scan scheduling, manual scan from the menu, post-scan metrics display, graceful error handling throughout, and declaring `tqdm` as an explicit dependency.

## Requirements

### REQ-AUTO-SCAN — Auto-scan cada SCANNER_INTERVAL_MINUTES

The legacy loop MUST automatically trigger `Scanner.scan()` every `SCANNER_INTERVAL_MINUTES` (default 60).
- The interval is measured in loop iterations: `iterations = max(1, (interval_minutes * 60) / poll_interval)`.
- Auto-scan SHALL NOT block the main loop — the scan runs in `run_in_executor`.
- When `SCANNER_INTERVAL_MINUTES=0`, auto-scan SHALL be disabled.
- When `self._scanner is None`, auto-scan SHALL be skipped silently.

#### Scenario: Auto-scan cada SCANNER_INTERVAL_MINUTES (default 60)

- GIVEN `SCANNER_INTERVAL_MINUTES=60` and `poll_interval=60`
- WHEN the legacy loop runs
- THEN `scanner_iterations = 60 * 60 / 60 = 60`
- AND `scan()` is called every 60th iteration (every 60 minutes)

#### Scenario: Auto-scan no bloquea el legacy loop

- GIVEN an auto-scan is triggered
- WHEN `Scanner.scan()` is executing via `run_in_executor()`
- THEN the legacy loop continues to process SPY signals
- AND the `await asyncio.sleep(poll_interval)` is NOT delayed

#### Scenario: SCANNER_INTERVAL_MINUTES=0 — no hace auto-scan

- GIVEN `SCANNER_INTERVAL_MINUTES=0`
- WHEN the legacy loop calculates `scanner_iterations`
- THEN `scanner_iterations = max(1, 0) = 1`
- BUT `scan()` is never called because the counter never reaches the threshold
- AND the bot scans only when triggered manually

#### Scenario: Scanner no disponible — auto-scan salta

- GIVEN `self._scanner is None`
- WHEN the auto-scan counter reaches the threshold
- THEN no scan attempt is made
- AND the log shows `"Scanner no disponible — saltando auto-scan"`

### REQ-MANUAL-SCAN — Scan manual desde el menú

The interactive menu option 2 (`Scanner`) MUST support triggering a manual scan via `trigger_scanner()` IPC signal file.

#### Scenario: Opción 2 del menú dispara scan_forzado

- GIVEN the user is on the scanner screen (opción 2)
- WHEN the user answers "s" to "¿Forzar escaneo ahora?"
- THEN `trigger_scanner(logs_dir)` is called
- AND `scan_now_signal.json` is written to logs/
- AND the screen displays "Escaneo disparado. Esperando..."

#### Scenario: scan_forzado crea scan_now_signal.json

- GIVEN `trigger_scanner()` is called
- WHEN the function executes
- THEN `logs/scan_now_signal.json` is created with `{"action": "scan_now", "timestamp": "..."}`
- AND the orchestrator polls this file and triggers `scan()` on the next iteration

#### Scenario: No hay scanner disponible — mensaje informativo

- GIVEN the scanner menu is accessed and `scanner_results.json` is empty
- WHEN the user sees "No hay resultados de escaneo aún."
- THEN no scan is forced
- AND the user can return to the main menu

### REQ-METRICS-PANEL — Post-scan metrics panel en _show_scanner

The scanner screen MUST display a metrics panel with total symbols, passed filter count, signals generated, and elapsed time.

#### Scenario: Metrics panel después de scan: total, passed, signals, time

- GIVEN `scan_history[-1] = {"total_symbols": 500, "passed_symbols": 200, "signals_count": 45, "elapsed_seconds": 30.5}`
- WHEN the scanner screen is rendered
- THEN a Rich Panel shows:
  - "Total símbolos: 500"
  - "Pasaron filtro: 200/500 (40%)"
  - "Señales: 45"
  - "Tiempo: 30.5s"

#### Scenario: 0 señales generadas — metrics muestra 0

- GIVEN `scan_history[-1] = {"total_symbols": 500, "passed_symbols": 200, "signals_count": 0, "elapsed_seconds": 25.0}`
- WHEN the metrics panel is rendered
- THEN it shows "Señales: 0"

#### Scenario: 0 símbolos pasaron filtro — metrics muestra 0/0

- GIVEN `scan_history[-1] = {"total_symbols": 16, "passed_symbols": 0, "signals_count": 0, "elapsed_seconds": 5.0}`
- WHEN the metrics panel is rendered
- THEN it shows "Pasaron filtro: 0/16 (0%)"

### REQ-TQDM-DEP — tqdm como dependencia explícita

`tqdm` MUST be added to `pyproject.toml` under `[project] dependencies`.

#### Scenario: tqdm>=4.66,<5 en pyproject.toml dependencies

- GIVEN `pyproject.toml` is read
- WHEN checking the dependencies list
- THEN `"tqdm>=4.66,<5"` is present
- AND it is NOT under `[project.optional-dependencies]`

#### Scenario: pip install instala tqdm explícitamente

- GIVEN a fresh virtual environment
- WHEN `pip install -e .` is executed
- THEN `tqdm` is installed as a first-level dependency
- AND `import tqdm` succeeds without any optional extras

#### Scenario: Auto-scan con scan manual interleaving

- GIVEN an auto-scan was triggered 30 minutes ago (half interval)
- WHEN the user triggers a manual scan from the menu
- THEN the manual scan runs immediately
- AND the auto-scan counter is NOT reset
- AND the next auto-scan still triggers at the original schedule

#### Scenario: Error fetching scanner_results.json — panel no se muestra

- GIVEN `scanner_results.json` is corrupt or missing
- WHEN `state_loader.load_scanner_results()` returns the default empty structure
- THEN the metrics panel is NOT rendered
- AND the text `"No hay resultados de escaneo aún."` is shown in dim style

#### Scenario: Scan manual cuando el scanner no está disponible

- GIVEN `self._scanner is None` (scanner failed to initialize)
- WHEN the user selects option 2 (Scanner) from the menu
- THEN the screen shows `"No hay resultados de escaneo aún."`
- AND there is NO option to force a scan (no "¿Forzar escaneo ahora?" prompt)
