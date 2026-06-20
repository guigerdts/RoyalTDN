# Async Scan — Specification

## Purpose

Convert `Scanner.scan()` from synchronous to asynchronous execution so it does not block the asyncio event loop. Use `loop.run_in_executor()` to offload the blocking `scan()` call to a thread pool, with a configurable timeout (default 300s). Handle `KeyboardInterrupt` gracefully and show a "scanning" state in the menu.

## Requirements

### REQ-ASYNC-SCAN — Scanner.scan() no bloquea el event loop

The orchestrator MUST execute `Scanner.scan()` via `loop.run_in_executor()` instead of calling it directly.
- Default timeout: 300 seconds.
- If timeout is reached, SHALL cancel the future and log a warning.
- The interactive menu SHALL show a "scanning" state during execution.
- `KeyboardInterrupt` during scanning SHALL be caught gracefully (no partial state corruption).
- The scan results (`_last_scan_results`, `_scan_history`) SHALL be fully written on success.

#### Scenario: Scanner.scan() ejecutado con loop.run_in_executor()

- GIVEN the orchestrator legacy loop decides to scan
- WHEN `Scanner.scan()` is about to run
- THEN it is called via `loop.run_in_executor(None, self._scanner.scan)`
- AND the main event loop is not blocked during execution

#### Scenario: Timeout de scan (default 300s) cancela ejecución

- GIVEN `Scanner.scan()` takes longer than 300s
- WHEN the `asyncio.wait_for()` wrapper raises `TimeoutError`
- THEN a warning is logged: `"Scanner timeout tras 300s — cancelando escaneo"`
- AND any partial results from the scan are discarded
- AND the legacy loop continues normally with SPY

#### Scenario: Estado "scanneando" visible durante ejecución

- GIVEN a scan is in progress
- WHEN the orchestrator status is published
- THEN the scanner status section shows `"scanneando"`
- AND the dashboard KPI reflects this state

#### Scenario: KeyboardInterrupt durante scan en executor

- GIVEN the user presses Ctrl+C while `Scanner.scan()` is running in the executor
- WHEN the legacy loop catches `KeyboardInterrupt`
- THEN the executor task is cancelled
- AND no partial scan data is written to `scanner_results.json`
- AND the bot continues to the next loop iteration

#### Scenario: Scan completado — resultados disponibles post-ejecución

- GIVEN `Scanner.scan()` completes successfully
- WHEN `await` on the executor future returns
- THEN `self._scanner._last_scan_results` contains valid data
- AND `self._scanner._scan_history` is updated with the new entry

#### Scenario: Error dentro del executor — no crashea el menú

- GIVEN `Scanner.scan()` raises an exception inside `run_in_executor`
- WHEN the exception propagates to the orchestrator
- THEN the exception is caught and logged: `"Scanner error: {error}"`
- AND the legacy loop continues with SPY instead of crashing

#### Scenario: Múltiples scans consecutivos — no hay race conditions

- GIVEN a scan finishes and immediately another one is triggered (SCANNER_INTERVAL_MINUTES=0)
- WHEN the second `run_in_executor()` call is made
- THEN a new future is created
- AND the previous scan's results are safely replaced
- AND no shared state corruption occurs

#### Scenario: Timeout alcanzado — scan parcial descartado

- GIVEN timeout is set to 60s and scan takes 90s
- WHEN `asyncio.wait_for` raises TimeoutError at 60s
- THEN `_publish_scanner_results()` is NOT called for the partial scan
- AND `_last_scan_results` retains the previous scan's data
