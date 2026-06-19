# What-If Simulation Specification

## Purpose

Interactive risk parameter experimentation for strategies with historical trade data. Users modify stop loss, take profit, or position size, then compare original vs simulated performance.

## Requirements

### Requirement: Simulation Selector

SHALL show list of strategies that have ≥1 trade in trades.json. User selects by number. GIVEN 0 trades for a strategy → "[dim]No hay trades históricos para simular[/]".

#### Scenario: No trades
- GIVEN strategy has 0 historical trades
- WHEN user selects it for simulation
- THEN "[dim]No hay trades históricos para simular[/]" shown

### Requirement: Parameter Configuration

SHALL present 3 modifiable risk params: 1. Stop Loss (ATR multiplier), 2. Take Profit (ratio), 3. Position Size (% of capital). User selects by number and enters new value. Validation: non-numeric → error + retry, negative → error + retry.

| Scenario | WHEN | THEN |
|----------|------|------|
| Valid input | enters "2.5" for stop loss | param accepted |
| Non-numeric | enters "abc" | error + re-prompt |
| Negative | enters "-1" | error + re-prompt |

### Requirement: Simulation Execution

`_simulate_trades(trades: list[dict], param: str, new_value: float) -> dict` SHALL clone strategy config, apply new param, recalculate P&L for each trade adjusting stops and position sizing. Return dict: `{total_pnl, max_drawdown, win_rate, num_trades}`.

#### Scenario: Basic simulation
- GIVEN 10 historical trades with known P&L
- WHEN simulation runs with tighter stop loss
- THEN returned metrics differ from original

### Requirement: Comparison Display

SHALL render comparison table: P&L original vs simulated, Drawdown original vs simulated, Win Rate original vs simulated. `_log_activity()` MUST be called on simulation run.

#### Scenario: Full comparison
- GIVEN simulation completes
- THEN table shows 3 metrics side-by-side (original vs simulated)
