# FASE 12 — Backtesting: Profesionalización

## Purpose

Professionalize the backtesting output with tqdm progress bars, new performance metrics (Sortino, Calmar, Expectancy, Avg Trade Duration), statistical validity warnings, individual trade tables, and Buy & Hold comparison.

## Requirements

### RQ-BT-01 — Progress bar (tqdm) during backtest

SHALL display tqdm progress bars during `run_backtest()`. One bar for the signal generation loop, another for the portfolio simulation loop.

**Format:** `"{symbol} {timeframe} ({period}) — {n}/{total} bars"`

### RQ-BT-02 — ETA during execution

SHALL use tqdm auto-ETA after the first few iterations. Display as `~{X}s restante` or `~{X}min {Y}s restante`.

### RQ-BT-03 — New metrics in return dict

SHALL add to the `metrics` dict:
- `sortino_ratio`: (mean(r) − rf) / std_neg(r), annualized × sqrt(252)
- `calmar_ratio`: CAGR / |MaxDD|. If MaxDD = 0, Calmar = CAGR
- `expectancy`: (WR × avg_win) − ((1−WR) × |avg_loss|)
- `avg_trade_duration`: mean days (exit − entry). 0.0 if no trades.

### RQ-BT-04 — Warning < 30 trades

SHALL display non-blocking bold yellow warning when `num_trades < 30`.

**Text:** `"⚠️ ⚠️  ADVERTENCIA: Solo {num_trades} trades generados. Mínimo recomendado: 30. Resultados no estadísticamente significativos."`

**Style:** `bold yellow`

### RQ-BT-05 — Trade table in backtest output

SHALL render a Rich Table after metrics with columns: `#`, `Entry Date`, `Exit Date`, `Entry Price`, `Exit Price`, `P&L`, `Return %`, `Duration`, `Fees`.

- P&L: green (≥0), red (<0), white (=0)
- No trades: yellow text `"⚠️  No se generaron trades en este período."`

### RQ-BT-06 — Buy & Hold comparison

SHALL render a Rich Panel titled `"📊  Comparación: Estrategia vs Buy & Hold"` showing:
- Buy & Hold Total Return %
- Buy & Hold CAGR
- Strategy vs Buy & Hold (difference)

Empty/None B&H data → gray `"No disponible"`.

## Color/Style Contract

| Element | Style |
|---------|-------|
| Warning text | `bold yellow` |
| P&L positive | `green` (ANSI 32) |
| P&L negative | `red` (ANSI 31) |
| P&L zero | `white` (default) |
| No trades message | `yellow` |
| B&H unavailable | `gray` / `dim` |
| Panel title | `bold white` |
| Table header | `bold white` |
| Metric column | `bold cyan` |
| Border | `white` |

## UI Text Contract

| Context | Spanish String |
|---------|---------------|
| Warning < 30 trades | `"⚠️ ⚠️  ADVERTENCIA: Solo {num_trades} trades generados. Mínimo recomendado: 30. Resultados no estadísticamente significativos."` |
| No trades in period | `"⚠️  No se generaron trades en este período."` |
| B&H unavailable | `"No disponible"` |
| B&H Panel title | `"📊  Comparación: Estrategia vs Buy & Hold"` |
