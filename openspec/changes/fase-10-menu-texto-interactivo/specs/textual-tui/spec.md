# Delta for textual-tui

## MODIFIED Requirements

### Requirement: Screen Navigation

MUST preserve Textual TUI as optional alternative. main.py SHALL import `run_menu` by default; Textual SHALL be gated behind `textual` extras flag in pyproject.toml. BINDINGS-based navigation SHALL remain when Textual is launched explicitly via `--tui` flag.
(Previously: Textual is the default TUI, imported and launched directly from main.py on `python -m royaltdn run`)

#### Scenario: Quick switch
- GIVEN DashboardScreen is active (Textual mode)
- WHEN user presses `3`
- THEN EstrategiasScreen pushes immediately

#### Scenario: Textual as optional dep
- GIVEN pyproject.toml has textual in optional-dependencies
- WHEN Textual is not installed
- THEN `from textual.app import App` raises ImportError, main.py catches it gracefully

#### Scenario: Default entry launches interactive-menu
- GIVEN `python -m royaltdn run` called without --tui
- THEN `run_menu()` launches (not RoyalTDNApp)
- AND Orchestrator thread starts in background

### Requirement: Termux Compatibility

Textual TUI MAY be incompatible with Termux. When Textual fails to initialize (curses/fg terminal error), main.py SHALL catch the exception and fall back to interactive-menu.
(Previously: Textual MUST work with TEXTUAL_COLORS=16 on Termux with minimum 80×24 terminal)

#### Scenario: Textual fallback in Termux
- GIVEN Terminal is Termux without proper terminal features
- WHEN Textual TUI fails to initialize
- THEN main.py catches the error AND launches interactive-menu via `run_menu()`
- AND user sees no crash — only the text menu

### Requirement: Live Polling

Textual screens SHALL still use `set_interval()` when launched via `--tui`. interactive-menu SHALL use `input()`-based refresh loops instead.

| Screen | Textual Timer | Menu Refresh |
|--------|--------------|--------------|
| Dashboard | 2s set_interval | Enter/s/N key prompt |
| Scanner | 2s set_interval | Manual trigger |
| Estrategias | 5s set_interval | Static (reload on Enter) |
| Trades | 3s set_interval | Static (filter on Enter) |
| Logs | 1s set_interval | 2s auto-refresh loop |

(Previously: All screens use set_interval timers)

#### Scenario: Timer update (Textual mode)
- GIVEN DashboardScreen is visible (via --tui)
- WHEN 2s elapse
- THEN refresh_data() called with fresh state

#### Scenario: Menu refresh loop
- GIVEN Dashboard on interactive-menu
- WHEN user enters "5" at refresh prompt
- THEN screen redraws every 5 seconds until keypress

### Requirement: Main entry

main.py SHALL attempt interactive-menu first. Textual TUI SHALL launch only when `--tui` flag is passed. Orchestrator thread SHALL be shared regardless of UI choice.
(Previously: main.py imports RoyalTDNApp and launches it directly on `python -m royaltdn run`)

#### Scenario: --tui flag
- GIVEN `python -m royaltdn run --tui` called
- THEN Textual TUI launches (if textual extras installed)
- AND Orchestrator thread runs in background

## REMOVED Requirements

### Requirement: Custom Widgets

(Reason: RoyalTDNHeader, RoyalTDNFooter, MetricsGrid, LogPanel were Textual-specific `compose()` components. All rendering is now inline Rich Console calls in each screen function.)
(Migration: Remove from textual/ tree; interactive-menu uses Table.grid and Text.assemble() directly.)

### Requirement: Live Polling — Textual set_interval

(Reason: Textual's `set_interval()` framework timer replaced by `input()`-based refresh loops in interactive-menu.)
(Migration: Dashboard and Logs screens provide inline refresh mini-loops with configurable N-second intervals via prompt.)

## Acceptance Criteria

- [ ] `python -m royaltdn run` launches interactive-menu (not Textual)
- [ ] `python -m royaltdn run --tui` launches Textual (if installed)
- [ ] Textual TUI preserved as optional: `pip install royaltdn[textual]`
- [ ] Textual fallback to menu on initialization failure
- [ ] All existing textual/ tests pass (unchanged)
- [ ] pyproject.toml marks textual as optional
