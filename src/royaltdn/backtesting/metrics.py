"""Stand-alone backtesting metrics.

Computes performance metrics from a list of closed trades and an
optional equity curve.

Every edge case is guarded: empty/single trades, flat equity curve,
zero losses, single negative return — all produce ``0.0`` instead of
``NaN`` or an exception.
"""

from __future__ import annotations

from typing import Any

# numpy is imported lazily inside functions that need it (it is broken
# on some platforms — Termux, etc. — and should not block module load).

# Annualisation factors per timeframe.  Crypto trades 24/7/365, so
# the calendar-year convention is used instead of 252 trading days.
_BARS_PER_YEAR_MAP: dict[str, int] = {
    "1m": 525_600,
    "3m": 175_200,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "2h": 4_380,
    "4h": 2_190,
    "6h": 1_460,
    "8h": 1_095,
    "12h": 730,
    "1d": 365,
    "3d": 122,
    "1w": 52,
    "1M": 12,
}


def bars_per_year(timeframe: str = "1d") -> int:
    """Return the annualisation factor (bars per year) for *timeframe*.

    Args:
        timeframe: Kline interval string (e.g. ``"1h"``, ``"30m"``).

    Returns:
        Integer number of bars in one calendar year for the given
        interval.
    """
    return _BARS_PER_YEAR_MAP.get(timeframe, 365)


def compute_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[float] | None = None,
    rf: float = 0.0,
    timeframe: str = "1d",
) -> dict[str, float]:
    """Compute a standard set of performance metrics.

    Args:
        trades: List of trade dicts.  Each must have at least a
            ``pnl`` key for trade-level metrics.
        equity_curve: Optional list of portfolio values recorded at
            regular intervals (e.g. after each bar).  When provided
            and at least 2 elements long, it enables Sharpe, Sortino,
            Calmar, and Max Drawdown.
        rf: Risk-free rate (annualised, e.g. ``0.05`` for 5 %).
            Defaults to ``0.0``.
        timeframe: Kline interval used for annualisation
            (e.g ``"1h"``, ``"30m"``).  Defaults to ``"1d"``.

    Returns:
        Dict with keys ``sharpe``, ``sortino``, ``calmar``,
        ``max_drawdown``, ``win_rate``, ``profit_factor``,
        ``expectancy``.  Metrics that could not be computed are
        ``0.0``.
    """
    import numpy as np

    # -- Trade-level metrics ------------------------------------------------
    pnls = _extract_pnls(trades)
    n_trades = len(pnls)

    if n_trades == 0:
        return _zero_metrics()

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / n_trades if n_trades > 0 else 0.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = _safe_div(gross_profit, gross_loss)

    expectancy = float(np.mean(pnls))

    # -- Curve-based metrics ------------------------------------------------
    if equity_curve is not None and len(equity_curve) >= 2:
        curve = np.array(equity_curve, dtype=float)
        returns = np.diff(curve) / curve[:-1]

        bpy = bars_per_year(timeframe)

        max_dd = _compute_max_drawdown(curve)

        sharpe = _compute_sharpe(returns, rf, bpy)
        sortino = _compute_sortino(returns, rf, bpy)

        total_return = (curve[-1] - curve[0]) / curve[0]
        annualized_return = total_return * bpy / len(returns)
        calmar = _safe_div(annualized_return, max_dd) if max_dd != 0.0 else 0.0
    else:
        sharpe = sortino = calmar = max_dd = 0.0

    return {
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
    }


# ---------------------------------------------------------------------------
# Benchmark comparison
# ---------------------------------------------------------------------------


def compute_benchmark(
    equity_curve: list[float],
    benchmark_equity_curve: list[float],
    timeframe: str = "1d",
) -> dict[str, float]:
    """Compare strategy performance to a buy-and-hold benchmark.

    Args:
        equity_curve: Per-bar portfolio values of the strategy.
        benchmark_equity_curve: Per-bar values of a buy-and-hold
            position in the benchmark asset (e.g. BTCUSDT) over the
            *same* bars.  Must be the same length as
            *equity_curve*.
        timeframe: Kline interval (used for annualisation).

    Returns:
        Dict with keys:

        - ``alpha`` — strategy excess return over benchmark
          (annualised).
        - ``beta`` — strategy return correlation to benchmark
          returns (Pearson).
        - ``benchmark_return`` — total return of the benchmark
          buy-and-hold over the period.
        - ``strategy_return`` — total return of the strategy.
        - ``strategy_outperformed`` — ``True`` if strategy total
          return > benchmark total return.
    """
    import numpy as np

    empty: dict[str, float] = {
        "alpha": 0.0,
        "beta": 0.0,
        "benchmark_return": 0.0,
        "strategy_return": 0.0,
        "strategy_outperformed": False,
    }

    if len(equity_curve) < 2 or len(benchmark_equity_curve) < 2:
        return empty

    n = min(len(equity_curve), len(benchmark_equity_curve))
    strat_arr = np.array(equity_curve[:n], dtype=float)
    bench_arr = np.array(benchmark_equity_curve[:n], dtype=float)

    strat_returns = np.diff(strat_arr) / strat_arr[:-1]
    bench_returns = np.diff(bench_arr) / bench_arr[:-1]

    if len(strat_returns) < 2 or len(bench_returns) < 2:
        return empty

    strat_total = (strat_arr[-1] - strat_arr[0]) / strat_arr[0]
    bench_total = (bench_arr[-1] - bench_arr[0]) / bench_arr[0]

    # Alpha = strategy_annualised_return - benchmark_annualised_return
    bpy = bars_per_year(timeframe)
    strat_annual = strat_total * bpy / len(strat_returns)
    bench_annual = bench_total * bpy / len(bench_returns)
    alpha = strat_annual - bench_annual

    # Beta = covariance(strat_returns, bench_returns) / var(bench_returns)
    cov = float(np.cov(strat_returns, bench_returns)[0, 1])
    var_bench = float(np.var(bench_returns, ddof=1))
    beta = _safe_div(cov, var_bench)

    return {
        "alpha": alpha,
        "beta": beta,
        "benchmark_return": bench_total,
        "strategy_return": strat_total,
        "strategy_outperformed": strat_total > bench_total,
    }


# ---------------------------------------------------------------------------
# Overfitting detection  (Monte Carlo Sharpe shuffle)
# ---------------------------------------------------------------------------


def detect_overfitting(
    trade_pnls: list[float],
    n_shuffles: int = 1000,
    seed: int = 42,
) -> dict[str, float]:
    """Detect potential overfitting via Monte Carlo Sharpe permutation.

    Shuffles the trade PnLs, re-computes the Sharpe ratio for each
    shuffled sequence, and returns the percentile of the actual Sharpe
    within the shuffled distribution.

    Args:
        trade_pnls: List of realised PnL values from the backtest.
        n_shuffles: Number of Monte Carlo shuffles (default 1000).
        seed: RNG seed for reproducibility (default 42).

    Returns:
        Dict with keys:

        - ``actual_sharpe`` — Sharpe of the original (unshuffled)
          trade PnL sequence.
        - ``shuffled_mean_sharpe`` — mean Sharpe across all shuffles.
        - ``shuffled_std_sharpe`` — std dev of shuffled Sharpes.
        - ``shuffled_p50`` / ``shuffled_p95`` — percentiles.
        - ``actual_percentile`` — percentile of actual Sharpe within
          the shuffled distribution (0-100).
        - ``overfit_flag`` — ``True`` if actual Sharpe < 95th
          percentile of shuffled (likely overfitted).
    """
    import numpy as np

    empty: dict[str, float] = {
        "actual_sharpe": 0.0,
        "shuffled_mean_sharpe": 0.0,
        "shuffled_std_sharpe": 0.0,
        "shuffled_p50": 0.0,
        "shuffled_p95": 0.0,
        "actual_percentile": 0.0,
        "overfit_flag": False,
    }

    # Need at least 3 trades for a meaningful shuffle test
    if len(trade_pnls) < 3:
        return empty

    pnls = np.array(trade_pnls, dtype=float)
    rng = np.random.default_rng(seed)

    # Actual Sharpe from the raw PnL sequence
    actual_sharpe = _sharpe_from_pnls(pnls)

    shuffled_sharpes: list[float] = []
    for _ in range(n_shuffles):
        shuffled = rng.permutation(pnls)
        s = _sharpe_from_pnls(shuffled)
        shuffled_sharpes.append(s)

    sh_arr = np.array(shuffled_sharpes)
    p50 = float(np.percentile(sh_arr, 50))
    p95 = float(np.percentile(sh_arr, 95))

    # Percentile of actual Sharpe within shuffled distribution
    count_below = int(np.sum(sh_arr < actual_sharpe))
    percentile = (count_below / n_shuffles) * 100.0

    overfit_flag = actual_sharpe < p95

    return {
        "actual_sharpe": actual_sharpe,
        "shuffled_mean_sharpe": float(np.mean(sh_arr)),
        "shuffled_std_sharpe": float(np.std(sh_arr, ddof=1)),
        "shuffled_p50": p50,
        "shuffled_p95": p95,
        "actual_percentile": percentile,
        "overfit_flag": bool(overfit_flag),
    }


# ---------------------------------------------------------------------------
# Survivorship bias warning
# ---------------------------------------------------------------------------

# Approximate Binance listing dates for common symbols (YYYY-MM-DD).
# Source: Binance announcements.  Used to warn about survivorship bias
# when backtesting data before a symbol was listed.
_KNOWN_LISTING_DATES: dict[str, str] = {
    "BTCUSDT": "2017-08-17",
    "ETHUSDT": "2017-08-17",
    "BNBUSDT": "2017-08-17",
    "ADAUSDT": "2019-09-09",
    "SOLUSDT": "2020-09-11",
    "XRPUSDT": "2019-09-11",
    "DOTUSDT": "2020-08-19",
    "LINKUSDT": "2019-09-09",
    "AVAXUSDT": "2020-09-22",
    "DOGEUSDT": "2019-07-05",
    "MATICUSDT": "2020-07-21",
    "ATOMUSDT": "2019-09-09",
    "LTCUSDT": "2017-08-17",
    "BCHUSDT": "2019-09-09",
    "UNIUSDT": "2020-09-17",
    "FILUSDT": "2021-02-08",
    "NEARUSDT": "2021-06-11",
    "APTUSDT": "2022-10-19",
    "ARBUSDT": "2023-03-23",
    "SUIUSDT": "2023-05-03",
    "PEPEUSDT": "2023-04-17",
    "INJUSDT": "2021-10-26",
    "SEIUSDT": "2023-08-15",
    "TIAUSDT": "2023-10-31",
}


def check_survivorship_bias(
    symbols: list[str],
    data_start_date: str,
) -> list[str]:
    """Check if backtest data precedes the listing date of any symbol.

    Args:
        symbols: List of trading symbol strings (e.g.
            ``["BTCUSDT", "SOLUSDT"]``).
        data_start_date: ISO-format date string representing the
            start of the backtest data (e.g. ``"2020-01-01"``).

    Returns:
        List of warning message strings.  Empty when no warnings
        are triggered.
    """
    from datetime import date

    warnings: list[str] = []
    try:
        data_start = date.fromisoformat(data_start_date)
    except (ValueError, TypeError):
        warnings.append(
            f"Could not parse data_start_date: {data_start_date!r}"
        )
        return warnings

    for sym in symbols:
        clean = sym.upper().replace("/", "")
        listing_str = _KNOWN_LISTING_DATES.get(clean)
        if listing_str is not None:
            listing_date = date.fromisoformat(listing_str)
            if data_start < listing_date:
                warnings.append(
                    f"{clean}: data starts {data_start_date} but "
                    f"Binance listing was {listing_str} — data before "
                    f"listing may be synthetic or from another venue."
                )

    return warnings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _zero_metrics() -> dict[str, float]:
    """Return a metrics dict with all values set to 0.0."""
    return {
        "sharpe": 0.0,
        "sortino": 0.0,
        "calmar": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "expectancy": 0.0,
    }


def _extract_pnls(trades: list[dict[str, Any]]) -> list[float]:
    """Extract realised PnL from each trade dict.

    Prefers the ``pnl`` key; falls back to computing a rough PnL from
    ``fill_price``, ``qty``, and ``commission`` if available.
    """
    pnls: list[float] = []
    for t in trades:
        pnl = t.get("pnl")
        if pnl is not None:
            pnls.append(float(pnl))
        elif "fill_price" in t and "qty" in t:
            entry = t.get("entry_price", t.get("price", 0.0))
            pnl_rough = (float(t["fill_price"]) - float(entry)) * float(t["qty"])
            pnls.append(pnl_rough - float(t.get("commission", 0.0)))
        else:
            pnls.append(0.0)
    return pnls


def _safe_div(a: float, b: float) -> float:
    """Return ``a / b``, or ``0.0`` when *b* is zero."""
    return a / b if b != 0.0 else 0.0


def _compute_max_drawdown(curve: Any) -> float:
    """Maximum peak-to-trough drawdown as a fraction of peak value.

    Args:
        curve: 1-D numpy array of portfolio values.

    Returns:
        Drawdown ratio between 0.0 and 1.0.
    """
    import numpy as np

    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / peak
    return float(np.max(drawdown))


def _compute_sharpe(
    returns: Any,
    rf: float = 0.0,
    bpy: int = 365,
) -> float:
    """Annualised Sharpe ratio from a series of returns.

    Returns ``0.0`` when there are fewer than 2 returns or the
    standard deviation is zero.
    """
    import numpy as np

    if len(returns) < 2:
        return 0.0
    daily_rf = rf / bpy
    excess = returns - daily_rf
    std = float(np.std(excess, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(excess)) / std * np.sqrt(bpy)


def _compute_sortino(
    returns: Any,
    rf: float = 0.0,
    bpy: int = 365,
) -> float:
    """Annualised Sortino ratio (downside deviation only).

    Returns ``0.0`` when there are fewer than 2 returns or the
    downside deviation is zero.
    """
    import numpy as np

    if len(returns) < 2:
        return 0.0
    daily_rf = rf / bpy
    excess = returns - daily_rf
    neg = excess[excess < 0]
    if len(neg) == 0:
        return 0.0
    downside_std = float(np.std(neg, ddof=1))
    if downside_std == 0.0:
        return 0.0
    return float(np.mean(excess)) / downside_std * np.sqrt(bpy)


def _sharpe_from_pnls(pnls: Any) -> float:
    """Compute a simplified Sharpe-like ratio from a PnL array.

    This is ``mean(pnls) / std(pnls)`` — it is NOT annualised and is
    used *only* for the Monte Carlo overfitting comparison where the
    relative ranking across shuffles matters, not the absolute value.

    Returns ``0.0`` when std is zero or fewer than 3 elements.
    """
    import numpy as np

    if len(pnls) < 3:
        return 0.0
    std = float(np.std(pnls, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(pnls)) / std
