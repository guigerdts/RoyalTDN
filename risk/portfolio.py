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
        self._peak_value: float = initial_capital  # peak tracked for drawdown
        self._mtm_prices: dict[str, float] = {}  # symbol -> last market price
        self._short_positions: dict[str, float] = {}  # symbol -> qty (negative liability)
        self._short_position_costs: dict[str, float] = {}  # symbol -> entry_price

    def get_total_value(self) -> float:
        """Return the current portfolio value (cash + positions at market).

        Uses mark-to-market prices when available, falls back to entry cost.

        Returns:
            Total portfolio value in cash-equivalent units.
        """
        total = self.capital
        for sym, qty in self.positions.items():
            price = self._mtm_prices.get(sym, self._position_costs.get(sym, 0.0))
            total += qty * price
        # Short liability: we owe the shares back if we close the short
        short_liability = sum(
            self._short_positions.get(sym, 0) * self._mtm_prices.get(sym, 0)
            for sym in self._short_positions
        )
        total -= short_liability
        # Update peak-equity tracker (side effect for drawdown calculation)
        self._peak_value = max(self._peak_value, total)
        return total

    def get_drawdown(self) -> float:
        """Return the current drawdown as a fraction of peak value.

        Drawdown = max(0, (peak - total_value) / peak)

        Uses peak-equity tracking so that growth resets the baseline,
        unlike the old initial-capital formula.

        Returns:
            Drawdown ratio between 0.0 and 1.0.
        """
        if self._peak_value == 0.0:
            return 0.0
        total = self.get_total_value()
        return max(0.0, (self._peak_value - total) / self._peak_value)

    def update_price(self, symbol: str, price: float) -> None:
        """Update mark-to-market price for an open position.

        Stores the current market price so get_total_value() reflects
        unrealized P&L. Updates peak-equity tracking after the change.

        Args:
            symbol: Trading pair symbol.
            price: Current market price.
        """
        if symbol in self.positions:
            self._mtm_prices[symbol] = price
        elif hasattr(self, '_short_positions') and symbol in self._short_positions:
            self._mtm_prices[symbol] = price
        # Update peak after the MTM adjustment
        self._peak_value = max(self._peak_value, self.get_total_value())

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
            # BUY could be long entry or short close (buy-to-cover)
            if symbol in self._short_positions and self._short_positions[symbol] > 0:
                # Close short position
                entry = self._short_position_costs.get(symbol, price)
                pnl = (entry - price) * qty
                self.capital -= qty * price
                self._short_positions[symbol] -= qty
                if self._short_positions[symbol] <= 0:
                    del self._short_positions[symbol]
                    if symbol in self._short_position_costs:
                        del self._short_position_costs[symbol]
                return pnl
            else:
                # Normal BUY entry
                self.capital -= qty * price
                self.positions[symbol] = self.positions.get(symbol, 0.0) + qty
                self._position_costs[symbol] = price
        elif action == "SHORT":
            # Short entry — you receive cash from selling borrowed shares
            self.capital += qty * price
            self._short_positions[symbol] = self._short_positions.get(symbol, 0.0) + qty
            self._short_position_costs[symbol] = price
        elif action == "SELL":
            self.capital += qty * price
            self.positions[symbol] = self.positions.get(symbol, 0.0) - qty
            if self.positions.get(symbol, 0.0) <= 0.0:
                self.positions.pop(symbol, None)
                self._position_costs.pop(symbol, None)
