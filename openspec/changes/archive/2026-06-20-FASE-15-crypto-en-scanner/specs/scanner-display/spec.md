# Delta for scanner-display

## Context

Existing display spec at `openspec/specs/fase13-scanner-universo-real/display.md` defines `REQ-DISPLAY-FIX` for the scanner table and metrics panel. The `_show_scanner()` function in `app.py` renders a `universe_label` dict. This delta adds the crypto entry.

## ADDED Requirements

### REQ-DISPLAY-CRYPTO — Crypto universe label in scanner screen

`_show_scanner()` MUST include `"crypto": "Crypto (10 pairs)"` in the `universe_label` dictionary so that `SCANNER_UNIVERSE=crypto` renders `"Universo: Crypto (10 pairs)"`.

#### Scenario: crypto universe label renders correctly

- GIVEN `SCANNER_UNIVERSE=crypto`
- WHEN `_show_scanner()` renders the universe info panel
- THEN the label `"Crypto (10 pairs)"` is displayed
- AND the text `"Universo: Crypto (10 pairs)"` appears in the panel

#### Scenario: Other universe labels unchanged

- GIVEN `SCANNER_UNIVERSE=sp500`
- WHEN `_show_scanner()` renders
- THEN the label shows `"S&P 500"` (unchanged from existing behavior)
- AND `"etfs"` and `"all"` labels are also unchanged
