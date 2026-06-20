# Interactive Menu — Delta Specification

## ADDED Requirements

### Requirement: RQ-TR-03 — Single-key filters for trades screen

SHALL replace the current prompt-based symbol filter and date filter flow with single-key commands in the trade table submenu.

#### Scenario: Press S to filter by symbol

- GIVEN the trades screen is showing all trades
- WHEN the user presses `S`
- THEN the system prompts `"Ingrese símbolo (ENTER para cancelar):"`
- WHEN the user enters "AAPL"
- THEN only trades with `symbol == "AAPL"` are shown (case-insensitive)

#### Scenario: Press E to filter by strategy

- GIVEN the trades screen is showing all trades
- WHEN the user presses `E`
- THEN the system prompts `"Ingrese estrategia (ENTER para cancelar):"`
- WHEN the user enters "EMA_Crossover"
- THEN only trades with `strategy == "EMA_Crossover"` are shown

#### Scenario: Press F for date range filter

- GIVEN the trades screen
- WHEN the user presses `F`
- THEN the date filter submenu is shown: `1=Today, 2=Week, 3=Month, 4=All, 5=Custom`
- WHEN the user selects "1"
- THEN only trades from today are shown

#### Scenario: Press T to reset all filters

- GIVEN trades are filtered by symbol="AAPL" AND strategy="EMA_Crossover"
- WHEN the user presses `T`
- THEN ALL filters are cleared
- AND all trades from `state_loader.load_trades()` are shown

#### Scenario: Press X to export

- GIVEN the trades screen with active filters
- WHEN the user presses `X`
- THEN the existing export dialog is displayed (CSV or JSON format choice + filename prompt)
- AND only the currently filtered trades are exported

#### Scenario: Press V for advanced statistics

- GIVEN the trades screen
- WHEN the user presses `V`
- THEN `_show_advanced_stats()` is called with the currently filtered trades list

#### Scenario: Cumulative filters

- GIVEN trades across 3 symbols and 2 strategies over 1 month
- WHEN the user applies symbol filter "AAPL" AND date filter "Month"
- THEN only AAPL trades from the last month are shown (filters ANDed together)
- AND the header shows `"Filtros activos: Símbolo=AAPL"` in blue italic

#### Scenario: Reset then re-filter

- GIVEN all filters were reset with `T`
- WHEN the user applies a new filter after reset
- THEN only the new filter applies (old filters were cleared)

#### Scenario: Cancel symbol filter with Enter

- GIVEN the user pressed S and sees `"Ingrese símbolo (ENTER para cancelar):"`
- WHEN the user presses Enter without typing anything
- THEN the symbol filter is not applied
- AND the current filter state is preserved


### Requirement: RQ-TR-04 — ANSI color contract for trades screen

SHALL apply 16-color ANSI styles to P&L and Win Rate values using `Console(color_system="standard")`.

#### Scenario: Positive P&L in green

- GIVEN a trade with pnl = +150.00
- WHEN the P&L cell is rendered in the trade table
- THEN it uses Rich style `"green"` or ANSI code 32 (bold green preferred)

#### Scenario: Negative P&L in red

- GIVEN a trade with pnl = -75.50
- WHEN the P&L cell is rendered
- THEN it uses Rich style `"red"` or ANSI code 31 (bold red preferred)

#### Scenario: Zero P&L in white

- GIVEN a trade with pnl = 0.00
- WHEN the P&L cell is rendered
- THEN it uses Rich style `"white"` or default

#### Scenario: Win Rate > 60% in green

- GIVEN the filtered trade set has win_rate = 65%
- WHEN the Win Rate value is displayed in the summary panel
- THEN it uses ANSI code 32 (green)

#### Scenario: Win Rate ≤ 60% in default white

- GIVEN the filtered trade set has win_rate = 55%
- WHEN the Win Rate value is displayed
- THEN it uses default white color (no special style)

#### Scenario: No hex codes or 24-bit colors

- GIVEN any trade rendering code path
- WHEN colors are applied
- THEN only 16-color ANSI names are used (green, red, yellow, cyan, magenta, blue, white, bold, dim)
- AND no `#rrggbb` hex codes appear in any Rich style strings


## MODIFIED Requirements

### Requirement: Trades (Previously: trade table with Symbol, Side, Qty, Entry, Exit, P&L + summary with Total, Win Rate, Profit Factor, Total P&L)

SHOW `state["trades"]` with enriched trade table and enhanced summary metrics. Summary Panel SHALL additionally show Sharpe Ratio, Average Trade (P&L promedio), Max Drawdown (percentage), Expectancy. Trade table columns: `#`, `Fecha` (YYYY-MM-DD HH:MM), `Símbolo`, `Lado`, `Qty`, `Entry`, `Exit`, `P&L`, `Retorno%`, `Duración`, `Slippage`, `Estrategia`. Single-key filter submenu replaces current symbol+period prompts.
(Previously: trade table with 5 columns (Symbol, Side, Qty, Entry, Exit, P&L) + summary with Total, Win Rate, Profit Factor, Total P&L + separate symbol and period prompt + separate submenu)

#### Scenario: Enriched trade table with all new columns (RQ-TR-02)

- GIVEN a trade with entry_at="2026-06-15T09:30:00", exit_at="2026-06-17T14:45:00", slippage_bps=5
- WHEN the table is rendered
- THEN Fecha shows "2026-06-15 09:30" (entry_at date formatted)
- AND Duración shows "2d 5h" (approx 2 days 5 hours)
- AND Slippage shows "5 bps"
- AND Entry shows "$XXX.XX" with 2 decimal places
- AND Exit shows "$XXX.XX" with 2 decimal places
- AND Estrategia shows the strategy field value

#### Scenario: Duration for sub-day trade

- GIVEN a trade with entry_at and exit_at less than 1 hour apart
- WHEN the duration is rendered
- THEN it shows `"< 1h"`

#### Scenario: Duration for multi-day trade

- GIVEN a trade with entry_at = "2026-06-01T10:00:00" and exit_at = "2026-06-07T15:30:00"
- WHEN the duration is rendered
- THEN it shows "6d 5h"

#### Scenario: No trades message (RQ-TR-02)

- GIVEN all filters result in an empty trade list
- WHEN the screen renders
- THEN `"No hay trades para mostrar con los filtros actuales."` is shown in gray italic
- AND no trade table is rendered

#### Scenario: Enriched summary with new metrics (RQ-TR-01)

- GIVEN a set of 10 trades with varying P&Ls
- WHEN the summary Panel renders
- THEN it SHALL include four additional rows:
  - Sharpe Ratio (from trade P&L list of returns, or "N/A" if < 2 trades)
  - Average Trade (mean of P&Ls, green if > 0, red if < 0, white if 0)
  - Max Drawdown (from cumulative P&L, formatted as "X.XX%")
  - Expectancy (computed using formula)

#### Scenario: Sharpe Ratio N/A with 0 or 1 trades

- GIVEN 0 trades or exactly 1 trade
- WHEN the summary Panel renders
- THEN Sharpe Ratio shows "N/A"

#### Scenario: Filter state not shown when no filters active (RQ-TR-03)

- GIVEN no filters are active (after pressing T or initial load)
- WHEN the trades screen renders
- THEN no filter indicator line is shown

#### Scenario: Active filter indicator shown in blue italic (RQ-TR-03)

- GIVEN symbol="AAPL" AND strategy="EMA_Crossover" filters are active
- WHEN the trades screen renders
- THEN the header shows `"Filtros activos: Símbolo=AAPL, Estrategia=EMA_Crossover"` in blue italic

#### Scenario: Existing submenu preserved (RQ-TR-03)

- GIVEN the trades screen
- WHEN the user sees the submenu
- THEN the existing options (Rendimiento por estrategia, Exportar, Estadísticas) remain accessible
- AND the single-key filters (S, E, F, T, X, V) are integrated into the same submenu line
