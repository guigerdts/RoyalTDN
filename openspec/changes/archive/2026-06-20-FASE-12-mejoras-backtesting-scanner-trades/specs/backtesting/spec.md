# Backtesting — Delta Specification

## ADDED Requirements

### Requirement: RQ-BT-01 — Progress bar during backtest execution

SHALL display a `tqdm` progress bar during `run_backtest()` signal generation loop.
SHALL display a second `tqdm` bar during the portfolio simulation loop (if it runs).

#### Scenario: Progress bar shows during signal generation

- GIVEN `run_backtest()` is executing with 252 bars of daily data for symbol "SPY"
- WHEN the signal generation loop iterates over each bar
- THEN a tqdm progress bar is displayed with format `"{symbol} {timeframe} ({period}) — {n}/{total} bars"` where total = 252
- AND tqdm auto-ETA shows seconds remaining after the first few iterations

#### Scenario: No progress bar when backtest errors before signal loop

- GIVEN `_download_data()` returns None for symbol "INVALID"
- WHEN `run_backtest()` returns an error
- THEN no tqdm progress bar is displayed

#### Scenario: Portfolio simulation loop also shows progress

- GIVEN signals were generated for 252 bars
- WHEN the portfolio simulation loop (lines 231–261 of backtesting.py) runs
- THEN a second tqdm progress bar is displayed for the simulation iteration

#### Scenario: KeyboardInterrupt during progress bar

- GIVEN a backtest is running with a tqdm progress bar active
- WHEN the user presses Ctrl+C
- THEN the backtest stops gracefully
- AND no orphaned tqdm output remains on screen


### Requirement: RQ-BT-02 — ETA format during execution

SHALL display tqdm auto-ETA in human-readable format after the first few iterations.

#### Scenario: ETA shows seconds

- GIVEN a backtest with fewer than 60 bars
- WHEN the progress bar has run for at least 3 iterations
- THEN the ETA shows as `~{X}s restante`

#### Scenario: ETA shows minutes and seconds

- GIVEN a backtest with more than 600 bars
- WHEN the progress bar has run for at least 10 iterations
- THEN the ETA shows as `~{X}min {Y}s restante`

#### Scenario: ETA shows on portfolio loop too

- GIVEN a backtest with both signal and portfolio simulation loops
- WHEN the portfolio simulation loop has run at least 3 iterations
- THEN the portfolio loop bar also shows auto-ETA

#### Scenario: ETA not shown on first iteration

- GIVEN a backtest just started
- WHEN the first bar is being processed
- THEN tqdm displays `?` or no ETA (tqdm default behavior — not enough samples)


### Requirement: RQ-BT-03 — New metrics in return dict

SHALL add four new keys to the `metrics` dict returned by `_compute_metrics()`:
- `sortino_ratio`: (mean(returns) - rf) / std_neg(returns), annualized * sqrt(252)
- `calmar_ratio`: CAGR / |Max Drawdown|. If MaxDD = 0, Calmar = CAGR
- `expectancy`: (Win Rate × Avg Win) − (Loss Rate × |Avg Loss|)
- `avg_trade_duration`: mean of (exit_date − entry_date) across all trades in hours (float). If no trades, return 0.0

#### Scenario: New metrics computed with valid trades

- GIVEN `_compute_metrics()` receives an equity series with positive returns and a trades DataFrame with 3 entries
- WHEN the function returns
- THEN the metrics dict contains `sortino_ratio`, `calmar_ratio`, `expectancy`, and `avg_trade_duration`
- AND `sortino_ratio` ≤ `sharpe` (downside deviation ≥ total deviation)
- AND `calmar_ratio` is a positive float

#### Scenario: Calmar ratio when Max Drawdown is zero

- GIVEN `_compute_metrics()` with a flat equity series (no drawdown)
- WHEN the function returns
- THEN `calmar_ratio` equals `cagr` (because |MaxDD| = 0, CAGR / 0 = CAGR by convention)

#### Scenario: Avg trade duration with no trades

- GIVEN `_compute_metrics()` with trades_df = None
- WHEN the function returns
- THEN `avg_trade_duration` is 0.0

#### Scenario: Expectancy formula correctness

- GIVEN trades_df with 7 wins (avg win = $100) and 3 losses (avg loss = -$50)
- WHEN `_compute_metrics()` computes expectancy
- THEN expectancy = (0.7 × 100) − (0.3 × 50) = 70 − 15 = 55.0

#### Scenario: All zero trades

- GIVEN trades_df has 5 entries all with pnl = 0.0
- WHEN `_compute_metrics()` runs
- THEN `expectancy` = 0.0
- AND `avg_trade_duration` = 0.0 (no entry/exit date diffs — returns 0.0 for zero-duration trades too)


### Requirement: RQ-BT-04 — Warning when fewer than 30 trades

SHALL display a non-blocking warning in bold yellow when `num_trades < 30`.

#### Scenario: Warning shown for 15 trades

- GIVEN a backtest result with 15 trades generated
- WHEN the backtest output is rendered
- THEN a bold yellow warning is displayed: `"⚠️ ⚠️  ADVERTENCIA: Solo 15 trades generados. Mínimo recomendado: 30. Resultados no estadísticamente significativos."`
- AND the metrics table is still shown (non-blocking)

#### Scenario: No warning for 30+ trades

- GIVEN a backtest result with exactly 30 trades
- WHEN the backtest output is rendered
- THEN no warning is displayed

#### Scenario: No warning for 0 trades

- GIVEN a backtest result with 0 trades (error case)
- WHEN the error message is shown
- THEN no trade-count warning is displayed (the error takes precedence)

#### Scenario: Edge case — exactly 29 trades

- GIVEN a backtest result with 29 trades
- WHEN the backtest output is rendered
- THEN the warning IS displayed (strictly less than 30)


### Requirement: RQ-BT-05 — Trade detail table in backtest output

SHALL render a Rich Table of individual trades after the metrics summary.

#### Scenario: Table rendered with 5 trades

- GIVEN a backtest result with 5 trades
- WHEN the backtest output is rendered
- THEN a table is shown with columns in this exact order: `#`, `Entry Date`, `Exit Date`, `Entry Price`, `Exit Price`, `P&L`, `Return %`, `Duration`, `Fees`
- AND P&L values ≥ 0 are colored green
- AND P&L values < 0 are colored red
- AND P&L = 0 is colored white

#### Scenario: No trades — empty state message

- GIVEN a backtest result with an empty trades list
- WHEN the backtest output is rendered
- THEN `"⚠️  No se generaron trades en este período."` is displayed in yellow
- AND no table is rendered

#### Scenario: Table with single trade

- GIVEN a backtest result with exactly 1 trade
- WHEN the table is rendered
- THEN the table has exactly one data row
- AND Duration shows the difference between Exit Date and Entry Date in days or hours

#### Scenario: Fee column shows zero when no fees field

- GIVEN a trade dict without a `fees` field
- WHEN the trade table is rendered
- THEN the Fees column shows "$0.00"

#### Scenario: Return % formatting

- GIVEN a trade with return_pct = 12.3456
- WHEN the return column is rendered
- THEN it shows "12.35%" (2 decimal places)


### Requirement: RQ-BT-06 — Buy & Hold comparison

SHALL render a Rich Panel comparing strategy vs Buy & Hold performance.

#### Scenario: B&H comparison with valid equity data

- GIVEN a backtest result with non-empty `buy_hold_equity` series
- WHEN the backtest output is rendered
- THEN a Panel titled `"📊  Comparación: Estrategia vs Buy & Hold"` is displayed
- AND it shows three metrics: Buy & Hold Total Return %, Buy & Hold CAGR, Strategy vs Buy & Hold (difference)
- AND Strategy vs Buy & Hold = Strategy total return − Buy & Hold total return

#### Scenario: B&H data not available

- GIVEN a backtest result where `buy_hold_equity` is None or empty
- WHEN the backtest output is rendered
- THEN the comparison shows `"No disponible"` in gray

#### Scenario: Buy & Hold returns match expected calculation

- GIVEN `buy_hold_equity` = [10000, 11000, 12100] (1st value = 10000, last = 12100)
- WHEN the comparison is rendered
- THEN Buy & Hold Total Return % = ((12100 / 10000) − 1) × 100 = 21.00%
