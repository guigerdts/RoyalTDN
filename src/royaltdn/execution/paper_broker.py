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
        commission_pct: float = 0.001,
        slippage_pct: float = 0.0005,
        order_manager: Any = None,
    ) -> None:
        """Initialise the paper broker.

        Args:
            initial_capital: Starting cash balance. Used to create an
                internal portfolio when none is provided.
            portfolio: An optional :class:`~royaltdn.risk.portfolio.Portfolio`
                instance. When ``None``, an internal portfolio is created.
            commission_pct: Commission as a fraction of notional value
                (e.g. 0.001 = 0.1 %). Default matches Binance spot taker fee.
            slippage_pct: Slippage as a fraction of signal price
                (e.g. 0.0005 = 0.05 %). Applied asymmetrically: BUY fills
                worsen, SELL/SHORT fills improve.
            order_manager: Optional :class:`~royaltdn.execution.order_manager.OrderManager`
                for lifecycle tracking.
        """
        self.initial_capital: float = initial_capital
        self._portfolio: Portfolio = portfolio or Portfolio(
            initial_capital=initial_capital,
        )
        self.order_manager: Any = order_manager
        self.commission_pct: float = commission_pct
        self.slippage_pct: float = slippage_pct
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

        Applies slippage to the fill price and deducts commission from
        portfolio capital.  The returned ``price`` is the effective
        price including commission (used by ``Portfolio.update`` for
        cost basis), while ``fill_price`` is the raw execution price
        after slippage only (used for reporting).

        Args:
            signal: Signal dict with ``action``, ``symbol``, ``price``,
                ``qty``.

        Returns:
            Trade result dict with ``order_id``, ``status``,
            ``price`` (effective price including commission),
            ``fill_price`` (slippage-adjusted), ``commission``,
            and ``slippage``.
        """
        self._order_counter += 1
        order_id = f"paper_{self._order_counter:06d}"

        price: float = float(signal.get("price", 0))
        qty: float = float(signal.get("qty", 0))
        action: str = signal.get("action", "")

        # ── OrderManager lifecycle ───────────────────────────────────────
        _om_client_id: str | None = None
        if self.order_manager is not None:
            from royaltdn.execution.order_manager import OrderState

            order = self.order_manager.create_order(
                symbol=signal.get("symbol", ""),
                side=action,
                qty=qty,
                price=price,
                order_type="MARKET",
            )
            _om_client_id = order.client_order_id
            self.order_manager.transition_to(_om_client_id, OrderState.PENDING_SUBMIT)
            self.order_manager.transition_to(_om_client_id, OrderState.SUBMITTED)

        # -- Slippage ----------------------------------------------------
        if action == "BUY":
            fill_price: float = price * (1.0 + self.slippage_pct)
        else:  # SELL, SHORT
            fill_price = price * (1.0 - self.slippage_pct)

        # -- Commission --------------------------------------------------
        commission_cost: float = fill_price * qty * self.commission_pct

        # Effective price includes commission for cost basis.
        # For BUY the buyer pays more; for SELL/SHORT the seller keeps less.
        if action == "BUY":
            effective_price: float = fill_price * (1.0 + self.commission_pct)
        else:
            effective_price = fill_price * (1.0 - self.commission_pct)

        # Record fill in OrderManager (paper fills are immediate)
        if self.order_manager is not None and _om_client_id is not None:
            self.order_manager.on_fill(
                _om_client_id,
                qty,
                fill_price,
                commission=commission_cost,
            )
            order_id = _om_client_id  # use OM-generated ID for traceability

        trade: dict[str, Any] = {
            "order_id": order_id,
            "client_order_id": _om_client_id or order_id,
            "symbol": signal.get("symbol", ""),
            "action": action,
            "qty": qty,
            "price": effective_price,
            "fill_price": fill_price,
            "commission": commission_cost,
            "slippage": self.slippage_pct,
            "status": "filled",
        }

        self.trades.append(trade)
        logger.info(
            "PAPER: {} {} {} @ ${:.2f} (fill ${:.2f}, slippage {:.4f}, "
            "comision {:.6f}) — {}",
            action,
            trade["symbol"],
            qty,
            effective_price,
            fill_price,
            self.slippage_pct,
            commission_cost,
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
