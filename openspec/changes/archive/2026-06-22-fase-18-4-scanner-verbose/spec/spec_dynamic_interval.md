# Dynamic Interval Specification

## Purpose

Replace the fixed 60-minute scanner interval with a category-based auto-adjustment: the orchestrator calculates the minimum recommended interval from all active strategies' categories and applies it, with an env var override option.

## Requirements

### Requirement 1: Interval calculation from active strategy categories

The orchestrator SHALL calculate a recommended interval at the start of each scan cycle from all active strategies' `category` attributes.

The mapping SHALL be:
- If any active strategy has `category="scalping"` → 2 minutes
- Else if any active strategy has `category="intraday"` → 15 minutes
- Else if any active strategy has `category="swing"` → 240 minutes
- Else (no active strategies) → 60 minutes

The calculation SHALL use the minimum interval across all active strategies (e.g. active scalping + swing = 2 minutes).

#### Scenario: scalping active triggers 2min
- GIVEN an active strategy with `category="scalping"` and another with `category="swing"`
- WHEN orchestrator calculates interval
- THEN the result is 2 minutes

#### Scenario: only swing strategies active
- GIVEN all active strategies have `category="swing"`
- WHEN orchestrator calculates interval
- THEN the result is 240 minutes

#### Scenario: no active strategies
- GIVEN no strategies have `active=true`
- WHEN orchestrator calculates interval
- THEN the result is 60 minutes

### Requirement 2: Env var override

The system MUST respect `SCANNER_INTERVAL_MINUTES` environment variable. When set to a positive integer, the orchestrator SHALL use that value instead of the calculated dynamic interval.

#### Scenario: env var takes priority
- GIVEN `SCANNER_INTERVAL_MINUTES=30` and an active scalping strategy
- WHEN orchestrator calculates interval
- THEN the interval is 30 minutes (env var overrides 2min calculation)

#### Scenario: env var is invalid
- GIVEN `SCANNER_INTERVAL_MINUTES=abc` or set to `0` or negative
- WHEN orchestrator reads the env var
- THEN the env var is ignored AND the calculated dynamic interval is used AND a warning is logged

### Requirement 3: Interval published in status.json

The orchestrator SHALL publish the current scan interval in `status.json` under the key `"scanner_interval_minutes"` after each scan cycle.

#### Scenario: interval in status.json
- GIVEN calculated interval is 15 minutes
- WHEN scan cycle completes
- THEN `status.json["scanner_interval_minutes"]` equals 15

### Requirement 4: Dashboard KPI interval display

The Dashboard SHALL show `"Scan: cada Xmin"` in the KPI section, where X is the current interval from `status.json`. When `SCANNER_INTERVAL_MINUTES` is active, SHALL show as `"Scan: cada Xmin (env)"`.

#### Scenario: default interval in KPI
- GIVEN `status.json` has `scanner_interval_minutes: 240`
- WHEN Dashboard renders KPIs
- THEN one KPI reads `"Scan: cada 240min"`

#### Scenario: env override in KPI
- GIVEN `SCANNER_INTERVAL_MINUTES=30` is active
- WHEN Dashboard renders KPIs
- THEN KPI reads `"Scan: cada 30min (env)"`

### Requirement 5: Scanner results interval display

The Scanner results screen SHALL show the current interval as `"Intervalo: X min"` in the header or summary area.

#### Scenario: interval in scanner header
- GIVEN current interval is 15 minutes
- WHEN Scanner screen renders
- THEN the header includes `"Intervalo: 15 min"`

### Requirement 6: Interval mismatch warning

When the calculated recommended interval differs from the actual interval (due to env var override or configuration), the system SHALL display a warning listing each active strategy with its category and recommended interval.

The warning format SHALL list strategies whose recommended interval is lower than the current actual interval.

#### Scenario: mismatch warning with env override
- GIVEN `SCANNER_INTERVAL_MINUTES=60` with an active scalping strategy (recommended 2min)
- WHEN Dashboard renders
- THEN a warning lists the scalping strategy with text indicating it needs 2min but interval is 60min
