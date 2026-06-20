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

### RQ-TR-02 — Rich trade table

SHALL display these columns: `#`, `Fecha`, `Símbolo`, `Lado`, `Qty`, `Entry`, `Exit`, `P&L`, `Retorno%`, `Duración`, `Slippage`, `Estrategia`.

- Fecha: `entry_at` formatted as `YYYY-MM-DD HH:MM`
- Duración: `exit_at − entry_at` as `"Xd Xh"` or `"< 1h"`
- Slippage: `slippage_bps` field as `"{bps} bps"`
- Entry/Exit: `{price:.2f}`
- P&L colored green/red/white as per RQ-TR-04
- No trades: `"No hay trades para mostrar con los filtros actuales."` (gray italic)

### RQ-TR-03 — Single-key filters

SHALL replace the current prompt-based filter flow with key commands:
- `S` → symbol filter prompt
- `E` → strategy filter prompt
- `F` → date filter submenu (1=Today, 2=Week, 3=Month, 4=All, 5=Custom)
- `T` → reset ALL filters
- `X` → export filtered trades (CSV/JSON)
- `V` → advanced statistics (`_show_advanced_stats()`)

Filters are cumulative (AND). Active filters shown as `"Filtros activos: Símbolo=X, Estrategia=Y"` in blue italic. No active filters → show nothing.

### RQ-TR-04 — ANSI colors

SHALL use 16-color ANSI only:
- P&L ≥ 0: `green` (ANSI 32)
- P&L < 0: `red` (ANSI 31)
- P&L = 0: `white` (default)
- Win Rate > 60%: `green` (ANSI 32)
- Win Rate ≤ 60%: default white
- Active filters indicator: `italic blue`

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
