# Scalping Disable Specification

## Purpose

Auto-disable scalping-category strategies when the universe is not crypto, preventing incompatible strategy execution. Provide clear notification and a manual override path with explicit warnings.

## Requirements

### Requirement 1: Auto-disable on universe change to non-crypto

When the universe changes to a non-crypto value (`etfs`, `sp500`, or `all`), the system MUST iterate all strategies in `strategies.json`, and for every strategy where `category="scalping"`, set `active=false`.

This SHALL happen inside the `_cycle_universe()` handler before the strategy list is persisted.

#### Scenario: universe changes from crypto to sp500
- GIVEN 3 active scalping strategies and 2 swing strategies in `strategies.json` with universe=`crypto`
- WHEN `_cycle_universe()` is called to change universe to `sp500`
- THEN all 3 scalping strategies have `active=false` in `strategies.json` AND swing strategies remain unchanged

#### Scenario: universe changes from crypto to crypto (no change)
- GIVEN universe is already `crypto`
- WHEN `_cycle_universe()` is called to change to `crypto` (no-op or re-set)
- THEN scalping strategies are NOT modified

#### Scenario: universe changes to crypto
- GIVEN universe is `sp500` with scalping strategies `active=false`
- WHEN `_cycle_universe()` is called to change to `crypto`
- THEN scalping strategies are NOT auto-enabled (user must manually enable)

### Requirement 2: Notification in main menu

When the current universe is not `crypto` AND there are scalping strategies present, the main menu SHALL display a notification line: `"🔴 Scalping desactivado: no compatible con el mercado actual."`

The notification SHALL appear below the header and above the numbered options, using a Rich `Text` with `style="bold red"`.

#### Scenario: notification shows on non-crypto universe with scalping
- GIVEN universe=`sp500` and at least one scalping strategy exists
- WHEN main menu renders
- THEN the notification `"🔴 Scalping desactivado: no compatible con el mercado actual."` is visible

#### Scenario: notification hidden on crypto universe
- GIVEN universe=`crypto`
- WHEN main menu renders
- THEN the scalping notification is NOT shown

### Requirement 3: Estrategias submenu warning before manual override

When the user is on the Estrategias screen and the universe is not `crypto`, if they attempt to manually activate a scalping-category strategy (toggle from inactive to active), the system SHALL display a confirmation prompt with warning text: `"⚠️ Scalping no recomendado en {universe}. ¿Activar de todas formas? (s/n):"`.

#### Scenario: warning on manual activation in non-crypto
- GIVEN universe=`sp500` and user selects an inactive scalping strategy and presses Toggle
- WHEN the system detects non-crypto universe
- THEN a confirmation prompt with warning text is shown

#### Scenario: activation proceeds after confirmation
- GIVEN user sees the warning prompt
- WHEN user enters "s" at the prompt
- THEN the strategy is set to `active=true` in `strategies.json`

#### Scenario: activation cancelled
- GIVEN user sees the warning prompt
- WHEN user enters "n" at the prompt
- THEN the strategy remains `active=false`

#### Scenario: no warning on crypto universe
- GIVEN universe=`crypto` and user activates a scalping strategy
- WHEN Toggle is pressed
- THEN the strategy is activated immediately without any warning prompt

### Requirement 4: Logging when scalping is auto-disabled

When the system auto-disables scalping strategies due to a universe change, it SHALL log at `warning` level: `"Scalping desactivado por cambio de universo a {universe}"`.

#### Scenario: log written on auto-disable
- GIVEN universe changes from `crypto` to `etfs`
- WHEN auto-disable runs and disables 3 scalping strategies
- THEN `bot.log` contains `"Scalping desactivado por cambio de universo a etfs"` at WARNING level
