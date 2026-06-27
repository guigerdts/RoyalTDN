"""Paper broker for paper-trading in the CellMesh architecture.

Simulates order execution without real capital. Maintains an internal
order book, tracks positions, and reports fills synchronously.

Portfolio integration (M2)
--------------------------
PaperBroker delegates **all portfolio state** (capital, positions,
drawdown) to a :class:`~royaltdn.risk.portfolio.Portfolio` instance.
The broker only handles order lifecycle, ticketing, and fill reporting
— it is **not** a second source of truth for the account.

When no explicit ``portfolio`` is passed, PaperBroker creates one
internally so that ``update_portfolio()`` always goes through the
unified code path.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from royaltdn.risk.portfolio import Portfolio


class PaperBroker:
    """Paper trading broker.

    Simulates trade execution: all orders are immediately filled at
    the requested price. All capital and position tracking is delegated
    to a :class:`~royaltdn.risk.portfolio.Portfolio` instance.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        portfolio: Portfolio | None = None,
    ) -> None:
        """Initialise the paper broker.

        Args:
            initial_capital: Starting cash balance. Used to create an
                internal portfolio when none is provided.
            portfolio: An optional :class:`~royaltdn.risk.portfolio.Portfolio`
                instance. When ``None``, an internal portfolio is created.
        """
        self.initial_capital: float = initial_capital
        self._portfolio: Portfolio = portfolio or Portfolio(
            initial_capital=initial_capital,
        )
        self.trades: list[dict[str, Any]] = []
        self._order_counter: int = 0
        self.bus: Any = None

    # ── Portfolio attribute access (read-through) ────────────────────────

    @property
    def capital(self) -> float:
        """Current cash balance, proxied from the portfolio."""
        return self._portfolio.capital

    @capital.setter
    def capital(self, value: float) -> None:
        self._portfolio.capital = value

    @property
    def positions(self) -> dict[str, float]:
        """Open long positions, proxied from the portfolio."""
        return self._portfolio.positions

    @positions.setter
    def positions(self, value: dict[str, float]) -> None:
        self._portfolio.positions = value

    @property
    def _short_positions(self) -> dict[str, float]:
        return self._portfolio._short_positions

    @_short_positions.setter
    def _short_positions(self, value: dict[str, float]) -> None:
        self._portfolio._short_positions = value

    @property
    def _peak_equity(self) -> float:
        return self._portfolio._peak_value

    @_peak_equity.setter
    def _peak_equity(self, value: float) -> None:
        self._portfolio._peak_value = value

    # ── Public API ───────────────────────────────────────────────────────

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
        """Update portfolio state after a filled trade.

        Always delegates to ``self._portfolio.update()`` (M2).

        Args:
            trade: Trade dict with ``action``, ``symbol``, ``qty``,
                ``price``.
        """
        self._portfolio.update(trade)

    def get_total_value(self) -> float:
        """Return the current account value.

        Delegates to ``portfolio.get_total_value()``.

        Returns:
            Current account value in cash-equivalent units.
        """
        return self._portfolio.get_total_value()

    def get_drawdown(self) -> float:
        """Return the current drawdown from peak equity.

        Delegates to ``portfolio.get_drawdown()``.

        Returns:
            Drawdown ratio between 0.0 and 1.0.
        """
        return self._portfolio.get_drawdown()
