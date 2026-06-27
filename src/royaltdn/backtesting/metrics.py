"""Stand-alone backtesting metrics.

Computes performance metrics from a list of closed trades and an
optional equity curve.  No dependencies beyond ``numpy``.

Every edge case is guarded: empty/single trades, flat equity curve,
zero losses, single negative return — all produce ``0.0`` instead of
``NaN`` or an exception.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Annualisation factor used when returns are daily (252 trading days
# per year for crypto / equities).
_BARS_PER_YEAR: int = 252


def compute_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[float] | None = None,
    rf: float = 0.0,
) -> dict[str, float]:
    """Compute a standard set of performance metrics.

    Args:
        trades: List of trade dicts.  Each must have at least a
            ``pnl`` (or ``commission`` + ``fill_price`` + ``qty``)
            key for trade-level metrics.  If ``pnl`` is absent the
            trade is treated as having zero PnL.
        equity_curve: Optional list of portfolio values recorded at
            regular intervals (e.g. after each bar).  When provided
            and at least 2 elements long, it enables Sharpe, Sortino,
            Calmar, and Max Drawdown.
        rf: Risk-free rate (annualised, e.g. ``0.05`` for 5 %).
            Defaults to ``0.0``.

    Returns:
        Dict with keys ``sharpe``, ``sortino``, ``calmar``,
        ``max_drawdown``, ``win_rate``, ``profit_factor``,
        ``expectancy``.  Metrics that could not be computed are
        ``0.0``.
    """
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

        max_dd = _compute_max_drawdown(curve)

        sharpe = _compute_sharpe(returns, rf)
        sortino = _compute_sortino(returns, rf)

        total_return = (curve[-1] - curve[0]) / curve[0]
        annualized_return = total_return * _BARS_PER_YEAR / len(returns)
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


# ── Internal helpers ────────────────────────────────────────────────────────


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


def _compute_max_drawdown(curve: np.ndarray) -> float:
    """Maximum peak-to-trough drawdown as a fraction of peak value.

    Args:
        curve: 1-D numpy array of portfolio values.

    Returns:
        Drawdown ratio between 0.0 and 1.0.
    """
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / peak
    return float(np.max(drawdown))


def _compute_sharpe(returns: np.ndarray, rf: float = 0.0) -> float:
    """Annualised Sharpe ratio from a series of daily returns.

    Returns ``0.0`` when there are fewer than 2 returns or the
    standard deviation is zero.
    """
    if len(returns) < 2:
        return 0.0
    daily_rf = rf / _BARS_PER_YEAR
    excess = returns - daily_rf
    std = float(np.std(excess, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(excess)) / std * np.sqrt(_BARS_PER_YEAR)


def _compute_sortino(returns: np.ndarray, rf: float = 0.0) -> float:
    """Annualised Sortino ratio (downside deviation only).

    Returns ``0.0`` when there are fewer than 2 returns or the
    downside deviation is zero.
    """
    if len(returns) < 2:
        return 0.0
    daily_rf = rf / _BARS_PER_YEAR
    excess = returns - daily_rf
    neg = excess[excess < 0]
    if len(neg) == 0:
        return 0.0
    downside_std = float(np.std(neg, ddof=1))
    if downside_std == 0.0:
        return 0.0
    return float(np.mean(excess)) / downside_std * np.sqrt(_BARS_PER_YEAR)
