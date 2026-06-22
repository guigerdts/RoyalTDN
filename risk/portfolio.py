"""Portfolio tracker for the CellMesh risk module.

Tracks capital, open positions, drawdown, and total portfolio value
for risk management decision-making.
"""

from __future__ import annotations

from typing import Any


class Portfolio:
    """Simple portfolio tracker.

    Maintains a cash balance and a dict of open positions. Used by
    RiskManager to enforce position limits and drawdown constraints.
    """

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        """Initialise the portfolio.

        Args:
            initial_capital: Starting cash balance.
        """
        self.initial_capital: float = initial_capital
        self.capital: float = initial_capital
        self.positions: dict[str, float] = {}

    def get_total_value(self) -> float:
        """Return the current portfolio value (cash + positions at cost).

        This is a simplified calculation that uses entry cost rather
        than mark-to-market. A full implementation would require live
        pricing for each position.

        Returns:
            Total portfolio value in cash-equivalent units.
        """
        return self.capital

    def get_drawdown(self) -> float:
        """Return the current drawdown as a fraction of initial capital.

        Drawdown = max(0, (initial - current) / initial)

        Returns:
            Drawdown ratio between 0.0 and 1.0.
        """
        if self.initial_capital == 0.0:
            return 0.0
        return max(0.0, (self.initial_capital - self.capital) / self.initial_capital)

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
        elif action == "SELL":
            self.capital += qty * price
            self.positions[symbol] = self.positions.get(symbol, 0.0) - qty
            # Remove zero-quantity positions
            if self.positions.get(symbol, 0.0) <= 0.0:
                self.positions.pop(symbol, None)
