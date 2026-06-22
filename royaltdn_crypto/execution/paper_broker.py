"""Paper broker for paper-trading in the CellMesh architecture.

Simulates order execution without real capital. Maintains an internal
order book, tracks positions, and reports fills synchronously.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class PaperBroker:
    """Paper trading broker.

    Simulates trade execution: all orders are immediately filled at
    the requested price. Tracks capital, positions, and trade history
    for reporting and analysis.
    """

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        """Initialise the paper broker.

        Args:
            initial_capital: Starting cash balance for the paper account.
        """
        self.initial_capital: float = initial_capital
        self.capital: float = initial_capital
        self.positions: dict[str, float] = {}
        self.trades: list[dict[str, Any]] = []
        self._order_counter: int = 0
        self.bus: Any = None

    def set_bus(self, bus: Any) -> None:
        """Attach an EventBus to the broker for status broadcasts.

        Args:
            bus: EventBus instance.
        """
        self.bus = bus

    async def submit_order(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Execute an order immediately (paper fill).

        Args:
            signal: Signal dict with ``action``, ``symbol``, ``price``,
                ``qty``.

        Returns:
            Trade result dict with ``order_id``, ``status``, and
            execution details.
        """
        self._order_counter += 1
        order_id = f"paper_{self._order_counter:06d}"

        trade: dict[str, Any] = {
            "order_id": order_id,
            "symbol": signal.get("symbol", ""),
            "action": signal.get("action", ""),
            "qty": float(signal.get("qty", 0)),
            "price": float(signal.get("price", 0)),
            "status": "filled",
        }

        self.trades.append(trade)
        logger.info(
            "PAPER: {} {} {} @ ${:.2f} — {}",
            trade["action"],
            trade["symbol"],
            trade["qty"],
            trade["price"],
            order_id,
        )

        return trade

    def update_portfolio(self, trade: dict[str, Any]) -> None:
        """Update internal capital and positions after a filled trade.

        Args:
            trade: Trade dict with ``action``, ``symbol``, ``qty``,
                ``price``.
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
            if self.positions.get(symbol, 0.0) <= 0.0:
                self.positions.pop(symbol, None)

    def get_total_value(self) -> float:
        """Return the current account value.

        Returns:
            Cash balance (positions are not marked-to-market in this
            simplified implementation).
        """
        return self.capital

    def get_drawdown(self) -> float:
        """Return the current drawdown from initial capital.

        Returns:
            Drawdown ratio between 0.0 and 1.0.
        """
        if self.initial_capital == 0.0:
            return 0.0
        return max(0.0, (self.initial_capital - self.capital) / self.initial_capital)
