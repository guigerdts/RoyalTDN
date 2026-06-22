"""Portfolio tracker for the CellMesh risk module.

Tracks cash balance, open positions, total portfolio value, and drawdown
for risk management decision-making.
"""

from __future__ import annotations

from typing import Any


class Portfolio:
    """Portfolio tracker.

    Maintains a cash balance and a dict of open positions. Total value
    = cash + positions valued at entry price (simplified mark-to-model).
    """

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        """Initialise the portfolio.

        Args:
            initial_capital: Starting cash balance.
        """
        self.initial_capital: float = initial_capital
        self.capital: float = initial_capital
        self.positions: dict[str, float] = {}  # symbol -> qty
        self._position_costs: dict[str, float] = {}  # symbol -> entry_price

    def get_total_value(self) -> float:
        """Return the current portfolio value (cash + positions at cost).

        Returns:
            Total portfolio value in cash-equivalent units.
        """
        total = self.capital
        for sym, qty in self.positions.items():
            cost = self._position_costs.get(sym, 0.0)
            total += qty * cost
        return total

    def get_drawdown(self) -> float:
        """Return the current drawdown as a fraction of initial capital.

        Drawdown = max(0, (initial - total_value) / initial)

        Uses total value (cash + positions at cost) so that buying
        a position doesn't artificially create a drawdown.

        Returns:
            Drawdown ratio between 0.0 and 1.0.
        """
        if self.initial_capital == 0.0:
            return 0.0
        total = self.get_total_value()
        return max(0.0, (self.initial_capital - total) / self.initial_capital)

    def update(self, trade: dict[str, Any]) -> None:
        """Update portfolio state from an executed trade.

        Args:
            trade: Trade dict with ``action``, ``symbol``, ``qty``, ``price``.
        """
        action = trade.get("action", "")
        qty = float(trade.get("qty", 0))
        price = float(trade.get("price", 0))
        symbol = trade.get("symbol", "")

        if action == "BUY":
            self.capital -= qty * price
            self.positions[symbol] = self.positions.get(symbol, 0.0) + qty
            self._position_costs[symbol] = price
        elif action == "SELL":
            self.capital += qty * price
            self.positions[symbol] = self.positions.get(symbol, 0.0) - qty
            if self.positions.get(symbol, 0.0) <= 0.0:
                self.positions.pop(symbol, None)
                self._position_costs.pop(symbol, None)
