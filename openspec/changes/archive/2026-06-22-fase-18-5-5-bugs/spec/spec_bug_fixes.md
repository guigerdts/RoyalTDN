# Bug Fixes — FASE 18.5

## Purpose

Corregir 3 bugs confirmados de FASE 18.4: universo incorrecto en menú, falta de scan inicial con `--verbose`, y ausencia de toggle verbose en vivo.

## Requirements

### R1: SCANNER_UNIVERSE env var must be respected

`_current_universe` MUST reflect `SCANNER_UNIVERSE` from `.env` at startup — not a hardcoded `"all"`.

#### Scenario: crypto universe from env

- GIVEN `.env` has `SCANNER_UNIVERSE=crypto` (single, no duplicates)
- WHEN the menu app initializes
- THEN `_current_universe == "crypto"` AND header shows `"Universe: crypto"`

#### Scenario: etfs universe from env

- GIVEN `.env` has `SCANNER_UNIVERSE=etfs`
- WHEN the menu app initializes
- THEN `_current_universe == "etfs"`

### R2: _current_universe synced from scanner at startup

Menu MUST read `scanner.universe.universe_type` at init, not hardcode it.

#### Scenario: scanner reports crypto

- GIVEN `scanner.universe.universe_type == "crypto"`
- WHEN menu header renders
- THEN `_current_universe == "crypto"`

### R3: Initial scan after startup with --verbose

When `--verbose` is active, system MUST start a non-blocking scan daemon to populate `_last_explanations`.

#### Scenario: verbose runs background scan

- GIVEN `--verbose` is set
- WHEN `main.py` initializes
- THEN `threading.Thread(target=scanner.scan, kwargs={"verbose": True}, daemon=True)` starts
- AND startup proceeds without blocking (no `.join()`)

#### Scenario: verbose inactive skips scan

- GIVEN `--verbose` is NOT set
- WHEN `main.py` initializes
- THEN no background scan thread is started

### R4: 'v' key toggles verbose in _show_scanner()

Scanner screen MUST toggle `scanner.verbose` when `'v'` is pressed.

#### Scenario: toggle on

- GIVEN user on scanner screen, verbose OFF
- WHEN user presses `'v'`
- THEN `self._scanner.verbose` toggles to `True` AND screen re-renders with verbose dashboard

#### Scenario: toggle off

- GIVEN user on scanner screen, verbose ON
- WHEN user presses `'v'`
- THEN `self._scanner.verbose` toggles to `False` AND screen re-renders without verbose dashboard

### R5: 'v' key must NOT trigger main menu dispatcher

`'v'` handler SHALL be consumed within `_show_scanner()` — shall NOT bubble to menu dispatch.

#### Scenario: 'v' consumed by scanner

- GIVEN user on scanner screen
- WHEN user presses `'v'`
- THEN no main menu option is triggered AND scanner screen remains active

### R6: _render_verbose_dashboard() shows data mid-session

When verbose is toggled ON mid-session, dashboard MUST show explanations or a loading state.

#### Scenario: explanations available

- GIVEN `_last_explanations` is populated
- WHEN `_render_verbose_dashboard()` renders
- THEN strategy tables with indicator values and closeness bars are shown

#### Scenario: explanations empty

- GIVEN `_last_explanations` is empty (no scan yet)
- WHEN `_render_verbose_dashboard()` renders
- THEN message `"No hay datos verbose aún — presiona 's' para escanear"` is displayed

### R7: All existing tests pass

All existing tests MUST pass after fixes are applied.

#### Scenario: full suite

- GIVEN all bug fixes are applied
- WHEN `pytest` runs
- THEN exit code is 0 AND all tests pass
