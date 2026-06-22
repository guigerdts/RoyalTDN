# Delta for Interactive Menu — Orchestrator Category Fix

## MODIFIED Requirements

### Requirement: \_build_strategies_list() — Category field

`Orchestrator._build_strategies_list()` MUST include `"category"` in every strategy dict it produces. The fix SHALL apply at three insertion points within the method: scanner strategies loop, fallback single-strategy entry, and user strategies loop.

For scanner strategies: `"category": getattr(strategy, 'category', 'swing')`. The fallback entry SHALL default to `"swing"`. For user strategies (DynamicStrategy): `"category": getattr(strat, 'category', 'swing')` — dynamic strategies MAY not have `category` so getattr with fallback is required.

(Previously: `_build_strategies_list()` omitted `category` entirely, causing all strategies to render without category grouping in the menu.)

#### Scenario: Scanner strategy includes category

- GIVEN a scanner with a `momentum_atr` strategy where `strategy.category == "swing"`
- WHEN `_build_strategies_list()` is called
- THEN the momentum_atr entry in the returned list has `"category": "swing"`

#### Scenario: Scanner strategy without category attr falls back

- GIVEN a strategy instance missing the `category` attribute
- WHEN `_build_strategies_list()` iterates over it
- THEN the entry has `"category": "swing"` via getattr fallback

#### Scenario: Fallback single-strategy entry

- GIVEN the scanner is None and fallback dict is built
- WHEN `_build_strategies_list()` returns the list
- THEN the fallback entry includes `"category": "swing"`

#### Scenario: User strategy includes category

- GIVEN a user DynamicStrategy with `category="swing"`
- WHEN `_build_strategies_list()` appends it
- THEN the entry has `"category": "swing"`

#### Scenario: User strategy without category attr

- GIVEN a user strategy that does not define `category`
- WHEN `_build_strategies_list()` processes it
- THEN the entry has `"category": "swing"` without raising AttributeError

## Out of Scope

- Refactoring the method structure — only adding the `"category"` key
- Changing how user strategies resolve their category — getattr fallback is sufficient

## Test Considerations

- Unit test: patch strategies with known category values, assert category in output
- Unit test: strategy without `category` attribute, assert fallback to `"swing"`
- Integration: verify strategies.json in logs/ contains `"category"` after orchestrator publishes status
