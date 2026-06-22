# Delta for Interactive Menu

## MODIFIED Requirements

### Requirement: Estrategias & Builder

SHALL display strategies grouped by `category` in Rich Table sections with colored category headers: **Swing** (blue, `bmagenta`/`bold blue`). Scalping (green) and Intradía (yellow) sections SHALL render as empty placeholders with `"[dim]No hay estrategias[/]"`. Each section header SHALL show the category emoji + name (e.g., `"🔵 Swing"`).

Each strategy row SHALL display: #, Nombre, Tipo, Activa, Categoría, Parámetros. The `get_parameters()` output SHALL be parsed to show relevant profile. Predefined strategies show `is_crypto_symbol`-based parameters; user strategies show their configured params.

Submenu: `[N]` select → Toggle/Editar(user)/Eliminar(user)/Backtest, `[B]` Builder, `[C]` Cargar, `[0]` Volver. All ops call `_log_activity()`. Toggle writes `active` field to strategies.json. Eliminar: confirm → `StrategyStore.delete()`. Predefined strategies: no Delete.

Builder unchanged: 10-step wizard with Name → Pick indicator → Param values → Loop → Entry rule → Exit rule → Symbol/timeframe → validate → backtest → Save. Editing preloads values with "Valor actual: X. Enter para mantener".

(Previously: flat table sorted by name, no categories, no section headers, no category column)

| Scenario | WHEN | THEN |
|----------|------|-------|
| Swing section has strategies | screen renders | strategies grouped under 🔵 Swing header |
| Scalping section empty | screen renders | "[dim]No hay estrategias[/]" in green section |
| Intradía section empty | screen renders | "[dim]No hay estrategias[/]" in yellow section |
| Category column shows value | screen renders | each row shows category name |
| Full flow | user completes 10 steps | strategy saved to user_strategies/ |
| Invalid indicator | enters "99" at pick | error + re-prompt |
| Param type error | enters "abc" for numeric | error + re-prompt |
| Toggle | select + Toggle | `active` field updated |
| Delete user | Eliminar + "s" | StrategyStore.delete() |
| Edit | builder with config | preloaded values |
| Quick backtest | Backtest + Enter | metrics table |

### Requirement: Main Menu Loop

SHALL display ASCII-box header + PAUSADO status (bold yellow when paused) + current universe filter + 8 numbered options + 'U' universe toggle + notification badges + 0 exit. The universe filter SHALL be displayed in the header as `"[cyan]Universe: {name}[/]"` where name is all/etfs/crypto/sp500.

Input via `input(">> ")`, strip. 'U'/'u' toggles universe. Invalid: error + re-prompt. Ctrl+C: "¿Salir? (s/n):", break on 's', call `orch.stop()`.

(Previously: no 'U' key, no universe filter display in header)

| Scenario | WHEN | THEN |
|----------|------|------|
| Navigate | "1" | Dashboard |
| Option 7 | "7" | What-If |
| Option 8 | "8" | Activity Log |
| U key toggle | "U" | universe cycles + header updates |
| Invalid | "9" | error + re-prompt |
| Ctrl+C exit | Ctrl+C+"s" | orch.stop() |

## ADDED Requirements

### Requirement: Universe filter display in header

The `_print_header()` function SHALL show the current universe filter value below the subtitle. The value SHALL be read from a `MenuState` in-memory variable (no persistent state file).

#### Scenario: Default universe shown
- GIVEN no universe toggle has been used
- WHEN the header renders
- THEN it shows `"[cyan]Universe: all[/]"`

#### Scenario: Universe updated after toggle
- GIVEN user pressed 'U' to cycle to crypto
- WHEN the header renders
- THEN it shows `"[cyan]Universe: crypto[/]"`

## Out of Scope

- Scalping and Intradía strategy implementations (FASE 18.3)
- User strategy categories (always shown as "Personalizadas")
- Category editing from the menu

## Test Considerations

- Test strategies grouped by category in sections
- Test section headers render with correct colors
- Test empty sections show placeholder text
- Test 'U' key cycles universe options
- Test universe filter displays in header after toggle
- Test all existing interactions (toggle, edit, delete, backtest) still work
