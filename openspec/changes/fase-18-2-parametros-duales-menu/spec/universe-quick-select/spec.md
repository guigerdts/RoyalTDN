# Universe Quick-Select Specification

## Purpose

Provides a single-key shortcut ('U') from the main menu to cycle the scanner universe filter without navigating submenus. The state lives in memory — no new files or DB migrations.

## Requirements

### Requirement: U key binding on main menu

The main menu SHALL bind the 'U' key (case-insensitive) to cycle the active universe filter. Pressing 'U' SHALL call a function that advances the universe through the cycle: `all` → `etfs` → `crypto` → `sp500` → back to `all`.

#### Scenario: Cycle forward
- GIVEN current universe is `"all"`
- WHEN user presses 'U'
- THEN the active universe becomes `"etfs"`

#### Scenario: Cycle wraps around
- GIVEN current universe is `"sp500"`
- WHEN user presses 'U'
- THEN the active universe becomes `"all"`

#### Scenario: Case insensitive
- GIVEN the main menu prompt
- WHEN user enters lowercase "u"
- THEN the universe cycles identically to uppercase "U"

### Requirement: In-memory state

The current universe filter SHALL be stored in a `MenuState` variable (e.g., `_current_universe` module-level or a simple dict). No files, no DB, no state.json changes. The state SHALL persist for the duration of the menu session.

#### Scenario: State lost on restart
- GIVEN user toggled universe to `"crypto"`
- WHEN the menu restarts
- THEN the universe resets to default (`"all"`)

### Requirement: Header display

The `_print_header()` function SHALL display the current universe filter below the subtitle line as `"[cyan]Universe: {name}[/]"`. The display SHALL update immediately after a 'U' toggle.

#### Scenario: Toggle updates header
- GIVEN header showing `"Universe: all"`
- WHEN user presses 'U'
- THEN header updates to show `"Universe: etfs"` on next render

### Requirement: Scanner integration

The selected universe SHALL be communicated to the scanner. When universe changes, the scanner's `AssetUniverse.invalidate_cache()` SHALL be called so the next scan fetches fresh symbols for the new universe.

#### Scenario: Cache invalidated on toggle
- GIVEN the scanner has cached universe data
- WHEN user toggles universe
- THEN `AssetUniverse.invalidate_cache()` is called
- AND the next scan uses the new universe filter

### Requirement: No persistence

The universe filter SHALL NOT be persisted to disk. No new JSON files, no env var changes, no state file mutations. The toggle is ephemeral — lost on menu exit.

#### Scenario: No files written
- GIVEN user toggles universe 5 times
- WHEN checking disk state
- THEN no files in `logs/` or `data/` are created or modified by the toggle

## Out of Scope

- Persistence of universe choice across restarts
- Per-strategy universe filtering
- Universe toggle from submenus (Dashboard, Scanner, etc.)
- Real-time re-scanning on toggle (next scan picks up new universe)

## Test Considerations

- Test 'U' cycles through all 4 states correctly (all → etfs → crypto → sp500 → all)
- Test lowercase 'u' works same as 'U'
- Test invalid input (non-U, non-number) still shows error
- Test universe display updates in header after toggle
- Test cache invalidation is called on toggle
- Test no files written during toggle sequence
