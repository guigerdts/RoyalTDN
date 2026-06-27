"""In-memory closed-trade accumulator with computed performance metrics.

Tracks every closed trade via a ``Trade`` dataclass and a ``TradeTracker``
with a ring-buffer eviction policy (max 100 trades by default). Exposes
computed properties (win rate, profit factor, Sharpe ratio, etc.) for
real-time dashboard consumption without database persistence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Any


@dataclass
class Trade:
    """A single closed trade record.

    Attributes:
        symbol: Trading pair symbol (e.g. ``"BTCUSDT"``).
        direction: Trade direction — ``"long"`` or ``"short"``.
        entry_price: Price at which the position was opened.
        exit_price: Price at which the position was closed.
        qty: Quantity traded (positive for both long and short entries).
        pnl: Realised profit/loss in quote currency.
        pnl_pct: Realised P&L as a percentage of the trade's cost basis.
        strategy_name: Name of the cell / strategy that generated the trade.
        entry_time: ISO-format timestamp when the position was opened.
        exit_time: ISO-format timestamp when the position was closed.
        duration_seconds: Wall-clock duration of the trade in seconds.
        exit_reason: Reason for the exit (e.g. ``"signal"``, ``"stop_loss"``).
    """

    symbol: str
    direction: str = "long"
    entry_price: float = 0.0
    exit_price: float = 0.0
    qty: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    strategy_name: str = ""
    entry_time: str | None = None
    exit_time: str | None = None
    duration_seconds: float = 0.0
    exit_reason: str = "signal"


class TradeTracker:
    """In-memory accumulator of closed trades with computed metrics.

    Stores up to *max_trades* trades in a ring buffer (oldest discarded
    when capacity is reached). All computed properties derive from the
    internal trade list and require no external state.

    Args:
        max_trades: Maximum number of trades to retain (default 100).
    """

    def __init__(self, max_trades: int = 100) -> None:
        self.max_trades: int = max_trades
        self._trades: list[Trade] = []

    # -- Trade recording ---------------------------------------------------

    def record_trade(self, **kwargs: Any) -> Trade:
        """Record a closed trade and enforce the ring-buffer capacity.

        Accepts all ``Trade`` dataclass fields as keyword arguments.
        If the number of stored trades already equals *max_trades*, the
        oldest trade is removed before appending the new one.

        Returns:
            The newly created ``Trade`` instance.
        """
        # Compute pnl_pct from pnl and cost basis when pnl_pct is not
        # explicitly provided and we have enough data to calculate it.
        if "pnl_pct" not in kwargs and kwargs.get("pnl") is not None:
            entry_price = kwargs.get("entry_price", 0.0)
            qty = kwargs.get("qty", 0.0)
            cost_basis = entry_price * qty
            if cost_basis != 0.0:
                kwargs["pnl_pct"] = (kwargs["pnl"] / cost_basis) * 100.0

        trade = Trade(**kwargs)

        if len(self._trades) >= self.max_trades:
            self._trades.pop(0)  # discard oldest

        self._trades.append(trade)
        return trade

    # -- Computed properties -----------------------------------------------

    @property
    def total_trades(self) -> int:
        """Total number of trades currently stored."""
        return len(self._trades)

    @property
    def trades(self) -> list[Trade]:
        """Read-only access to the internal trade list."""
        return list(self._trades)

    @property
    def win_rate(self) -> float:
        """Fraction of trades with positive P&L (0.0 .. 1.0).

        Returns 0.0 when there are no trades.
        """
        if not self._trades:
            return 0.0
        wins = sum(1 for t in self._trades if t.pnl > 0.0)
        return wins / len(self._trades)

    @property
    def profit_factor(self) -> float:
        """Ratio of gross profits to gross losses.

        Returns ``float('inf')`` when there are no losing trades.
        Returns 0.0 when there are no winning trades.
        """
        gross_profit = sum(t.pnl for t in self._trades if t.pnl > 0.0)
        gross_loss = abs(sum(t.pnl for t in self._trades if t.pnl < 0.0))

        if gross_loss == 0.0:
            return float("inf") if gross_profit > 0.0 else 0.0
        return gross_profit / gross_loss

    @property
    def expectancy(self) -> float:
        """Average P&L per trade.

        Returns 0.0 when there are no trades.
        """
        if not self._trades:
            return 0.0
        return sum(t.pnl for t in self._trades) / len(self._trades)

    @property
    def best_trade(self) -> Trade | None:
        """Trade with the highest P&L, or ``None`` if no trades."""
        if not self._trades:
            return None
        return max(self._trades, key=lambda t: t.pnl)

    @property
    def worst_trade(self) -> Trade | None:
        """Trade with the lowest P&L, or ``None`` if no trades."""
        if not self._trades:
            return None
        return min(self._trades, key=lambda t: t.pnl)

    @property
    def total_pnl(self) -> float:
        """Sum of P&L across all stored trades."""
        return sum(t.pnl for t in self._trades)

    @property
    def sharpe_ratio(self) -> float:
        """Annualised Sharpe ratio based on trade P&L.

        Formula: ``mean(pnl) / stdev(pnl) * sqrt(252)``.

        Returns 0.0 when fewer than 2 trades are stored (standard
        deviation is undefined for a single data point).
        """
        if len(self._trades) < 2:
            return 0.0

        pnls = [t.pnl for t in self._trades]
        _mean = mean(pnls)
        _stdev = stdev(pnls)

        if _stdev == 0.0:
            return 0.0

        return (_mean / _stdev) * math.sqrt(252)

    @property
    def avg_holding_time(self) -> float:
        """Average trade duration in seconds.

        Returns 0.0 when there are no trades or no trades have
        duration data.
        """
        if not self._trades:
            return 0.0
        durations = [t.duration_seconds for t in self._trades if t.duration_seconds > 0.0]
        if not durations:
            return 0.0
        return mean(durations)

    def per_cell_stats(self) -> dict[str, dict[str, float]]:
        """Per-cell performance summary for cell prioritisation.

        Returns a dict keyed by ``strategy_name`` with:
        ``win_rate``, ``total_trades``, ``total_pnl``, ``avg_pnl``.
        """
        from collections import defaultdict
        by_cell: dict[str, list[Trade]] = defaultdict(list)
        for t in self._trades:
            by_cell[t.strategy_name].append(t)

        result: dict[str, dict[str, float]] = {}
        for cell, trades in by_cell.items():
            wins = sum(1 for t in trades if t.pnl > 0.0)
            pnls = [t.pnl for t in trades]
            result[cell] = {
                "win_rate": wins / len(trades) if trades else 0.0,
                "total_trades": float(len(trades)),
                "total_pnl": sum(pnls),
                "avg_pnl": mean(pnls) if pnls else 0.0,
            }
        return result
