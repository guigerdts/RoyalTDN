# FASE 12 — Trades: Rediseño de Visualización

## Purpose

Enrich the trade history screen with professional summary metrics (Sharpe, Avg Trade, Max Drawdown, Expectancy), an expanded trade table (Fecha, Duración, Slippage, Retorno%, Estrategia), single-key cumulative filters (S/E/F/T/X/V), and ANSI color semantics.

## Requirements

### RQ-TR-01 — Summary metrics

SHALL add to the existing summary Panel:
- **Sharpe Ratio**: computed from trade P&L returns. "N/A" if < 2 trades.
- **Average Trade**: mean(P&L). Green (>0), red (<0), white (=0).
- **Max Drawdown**: from cumulative P&L series, formatted as "X.XX%".
- **Expectancy**: (WR × avg_win) − ((1−WR) × |avg_loss|)

**Panel title:** `"📊  Resumen de Trades"` (existing)

#### Scenarios

##### Enriched summary with new metrics
- GIVEN a set of 10 trades with varying P&Ls
- WHEN the summary Panel renders
- THEN it SHALL include four additional rows:
  - Sharpe Ratio (from trade P&L list of returns, or "N/A" if < 2 trades)
  - Average Trade (mean of P&Ls, green if > 0, red if < 0, white if 0)
  - Max Drawdown (from cumulative P&L, formatted as "X.XX%")
  - Expectancy (computed using formula)

##### Sharpe Ratio N/A with 0 or 1 trades
- GIVEN 0 trades or exactly 1 trade
- WHEN the summary Panel renders
- THEN Sharpe Ratio shows "N/A"

### RQ-TR-02 — Rich trade table

SHALL display these columns: `#`, `Fecha`, `Símbolo`, `Lado`, `Qty`, `Entry`, `Exit`, `P&L`, `Retorno%`, `Duración`, `Slippage`, `Estrategia`.

- Fecha: `entry_at` formatted as `YYYY-MM-DD HH:MM`
- Duración: `exit_at − entry_at` as `"Xd Xh"` or `"< 1h"`
- Slippage: `slippage_bps` field as `"{bps} bps"`
- Entry/Exit: `{price:.2f}`
- P&L colored green/red/white as per RQ-TR-04
- No trades: `"No hay trades para mostrar con los filtros actuales."` (gray italic)

#### Scenarios

##### Enriched trade table with all new columns
- GIVEN a trade with entry_at="2026-06-15T09:30:00", exit_at="2026-06-17T14:45:00", slippage_bps=5
- WHEN the table is rendered
- THEN Fecha shows "2026-06-15 09:30" (entry_at date formatted)
- AND Duración shows "2d 5h" (approx 2 days 5 hours)
- AND Slippage shows "5 bps"
- AND Entry shows "$XXX.XX" with 2 decimal places
- AND Exit shows "$XXX.XX" with 2 decimal places
- AND Estrategia shows the strategy field value

##### Duration for sub-day trade
- GIVEN a trade with entry_at and exit_at less than 1 hour apart
- WHEN the duration is rendered
- THEN it shows `"< 1h"`

##### Duration for multi-day trade
- GIVEN a trade with entry_at = "2026-06-01T10:00:00" and exit_at = "2026-06-07T15:30:00"
- WHEN the duration is rendered
- THEN it shows "6d 5h"

##### No trades message
- GIVEN all filters result in an empty trade list
- WHEN the screen renders
- THEN `"No hay trades para mostrar con los filtros actuales."` is shown in gray italic
- AND no trade table is rendered

### RQ-TR-03 — Single-key filters

SHALL replace the current prompt-based filter flow with key commands:
- `S` → symbol filter prompt
- `E` → strategy filter prompt
- `F` → date filter submenu (1=Today, 2=Week, 3=Month, 4=All, 5=Custom)
- `T` → reset ALL filters
- `X` → export filtered trades (CSV/JSON)
- `V` → advanced statistics (`_show_advanced_stats()`)

Filters are cumulative (AND). Active filters shown as `"Filtros activos: Símbolo=X, Estrategia=Y"` in blue italic. No active filters → show nothing.

#### Scenarios

##### Press S to filter by symbol
- GIVEN the trades screen is showing all trades
- WHEN the user presses `S`
- THEN the system prompts `"Ingrese símbolo (ENTER para cancelar):"`
- WHEN the user enters "AAPL"
- THEN only trades with `symbol == "AAPL"` are shown (case-insensitive)

##### Press E to filter by strategy
- GIVEN the trades screen is showing all trades
- WHEN the user presses `E`
- THEN the system prompts `"Ingrese estrategia (ENTER para cancelar):"`
- WHEN the user enters "EMA_Crossover"
- THEN only trades with `strategy == "EMA_Crossover"` are shown

##### Press F for date range filter
- GIVEN the trades screen
- WHEN the user presses `F`
- THEN the date filter submenu is shown: `1=Today, 2=Week, 3=Month, 4=All, 5=Custom`
- WHEN the user selects "1"
- THEN only trades from today are shown

##### Press T to reset all filters
- GIVEN trades are filtered by symbol="AAPL" AND strategy="EMA_Crossover"
- WHEN the user presses `T`
- THEN ALL filters are cleared
- AND all trades from `state_loader.load_trades()` are shown

##### Press X to export
- GIVEN the trades screen with active filters
- WHEN the user presses `X`
- THEN the existing export dialog is displayed (CSV or JSON format choice + filename prompt)
- AND only the currently filtered trades are exported

##### Press V for advanced statistics
- GIVEN the trades screen
- WHEN the user presses `V`
- THEN `_show_advanced_stats()` is called with the currently filtered trades list

##### Cumulative filters
- GIVEN trades across 3 symbols and 2 strategies over 1 month
- WHEN the user applies symbol filter "AAPL" AND date filter "Month"
- THEN only AAPL trades from the last month are shown (filters ANDed together)
- AND the header shows `"Filtros activos: Símbolo=AAPL"` in blue italic

##### Reset then re-filter
- GIVEN all filters were reset with `T`
- WHEN the user applies a new filter after reset
- THEN only the new filter applies (old filters were cleared)

##### Cancel symbol filter with Enter
- GIVEN the user pressed S and sees `"Ingrese símbolo (ENTER para cancelar):"`
- WHEN the user presses Enter without typing anything
- THEN the symbol filter is not applied
- AND the current filter state is preserved

##### Filter state not shown when no filters active
- GIVEN no filters are active (after pressing T or initial load)
- WHEN the trades screen renders
- THEN no filter indicator line is shown

##### Active filter indicator shown in blue italic
- GIVEN symbol="AAPL" AND strategy="EMA_Crossover" filters are active
- WHEN the trades screen renders
- THEN the header shows `"Filtros activos: Símbolo=AAPL, Estrategia=EMA_Crossover"` in blue italic

##### Existing submenu preserved
- GIVEN the trades screen
- WHEN the user sees the submenu
- THEN the existing options (Rendimiento por estrategia, Exportar, Estadísticas) remain accessible
- AND the single-key filters (S, E, F, T, X, V) are integrated into the same submenu line

### RQ-TR-04 — ANSI colors

SHALL use 16-color ANSI only:
- P&L ≥ 0: `green` (ANSI 32)
- P&L < 0: `red` (ANSI 31)
- P&L = 0: `white` (default)
- Win Rate > 60%: `green` (ANSI 32)
- Win Rate ≤ 60%: default white
- Active filters indicator: `italic blue`

#### Scenarios

##### Positive P&L in green
- GIVEN a trade with pnl = +150.00
- WHEN the P&L cell is rendered in the trade table
- THEN it uses Rich style `"green"` or ANSI code 32 (bold green preferred)

##### Negative P&L in red
- GIVEN a trade with pnl = -75.50
- WHEN the P&L cell is rendered
- THEN it uses Rich style `"red"` or ANSI code 31 (bold red preferred)

##### Zero P&L in white
- GIVEN a trade with pnl = 0.00
- WHEN the P&L cell is rendered
- THEN it uses Rich style `"white"` or default

##### Win Rate > 60% in green
- GIVEN the filtered trade set has win_rate = 65%
- WHEN the Win Rate value is displayed in the summary panel
- THEN it uses ANSI code 32 (green)

##### Win Rate ≤ 60% in default white
- GIVEN the filtered trade set has win_rate = 55%
- WHEN the Win Rate value is displayed
- THEN it uses default white color (no special style)

##### No hex codes or 24-bit colors
- GIVEN any trade rendering code path
- WHEN colors are applied
- THEN only 16-color ANSI names are used (green, red, yellow, cyan, magenta, blue, white, bold, dim)
- AND no `#rrggbb` hex codes appear in any Rich style strings

## Color/Style Contract

| Element | Style |
|---------|-------|
| P&L positive | `bold green` (ANSI 32) |
| P&L negative | `bold red` (ANSI 31) |
| P&L zero | `white` (default) |
| Win Rate > 60% | `green` (ANSI 32) |
| Win Rate ≤ 60% | default white |
| Active filters | `italic blue` |
| No trades message | `dim` / `italic` (gray) |
| Summary Panel title | `bold white` |
| Metric labels | `bold cyan` |

## UI Text Contract

| Context | Spanish String |
|---------|---------------|
| Symbol filter prompt | `"Ingrese símbolo (ENTER para cancelar):"` |
| Strategy filter prompt | `"Ingrese estrategia (ENTER para cancelar):"` |
| Active filters header | `"Filtros activos: Símbolo={s}, Estrategia={e}"` |
| No trades | `"No hay trades para mostrar con los filtros actuales."` |
| Date menu | `"1=Today, 2=Week, 3=Month, 4=All, 5=Custom"` (existing) |
| Sharpe N/A | `"N/A"` |
| Day-hour separator | `"d "` and `"h"` (e.g. `"2d 5h"`, `"< 1h"`) |
