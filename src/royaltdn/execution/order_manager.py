"""Order lifecycle state machine for the CellMesh architecture.

Manages order creation, state transitions, fill accumulation, and
reconciliation with exchange state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

from loguru import logger


class OrderState(Enum):
    """Valid order states in the lifecycle state machine."""

    CREATED = auto()
    PENDING_SUBMIT = auto()
    SUBMITTED = auto()
    PARTIAL_FILLED = auto()
    FILLED = auto()
    CANCELLED = auto()
    REJECTED = auto()
    EXPIRED = auto()


# ── Valid state transitions (irreversible) ──────────────────────────────────
# Mapping: from_state -> set of allowed to_state
_VALID_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.CREATED: {OrderState.PENDING_SUBMIT},
    OrderState.PENDING_SUBMIT: {OrderState.SUBMITTED},
    OrderState.SUBMITTED: {
        OrderState.PARTIAL_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    },
    OrderState.PARTIAL_FILLED: {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
    },
}

# Once an order reaches a terminal state, no further transitions are valid.
_TERMINAL_STATES: set[OrderState] = {
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
}


@dataclass
class Fill:
    """A single fill (partial or full) against an order."""

    qty: float
    price: float
    commission: float = 0.0
    timestamp: str = ""


@dataclass
class Order:
    """An order tracked by the OrderManager state machine."""

    client_order_id: str
    symbol: str
    side: str  # "BUY", "SELL", "SHORT"
    order_type: str  # "MARKET", "LIMIT"
    qty: float
    price: float = 0.0
    state: OrderState = OrderState.CREATED
    exchange_order_id: str = ""
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    fills: list[Fill] = field(default_factory=list)
    reject_reason: str = ""
    created_at: str = ""
    updated_at: str = ""


class OrderManager:
    """In-memory order lifecycle manager.

    Maintains a dict of :class:`Order` instances keyed by
    ``client_order_id``, enforces valid state transitions, and
    accumulates fill data.
    """

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._nonce: int = 0

    # ── Order creation ─────────────────────────────────────────────────────

    def create_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = 0.0,
        order_type: str = "MARKET",
    ) -> Order:
        """Create a new order and store it.

        The ``client_order_id`` is auto-generated as
        ``{symbol}-{timestamp_ms}-{nonce}``.

        Returns:
            The newly created :class:`Order` in state ``CREATED``.
        """
        now = datetime.now(timezone.utc)
        client_order_id = self._next_client_order_id(symbol)
        order = Order(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            price=price,
            state=OrderState.CREATED,
            created_at=str(now),
            updated_at=str(now),
        )
        self._orders[client_order_id] = order
        logger.debug("Orden creada: {} {} {} qty={}", client_order_id, side, symbol, qty)
        return order

    def _next_client_order_id(self, symbol: str) -> str:
        """Generate a unique client order ID.

        Format: ``{symbol}-{timestamp_ms}-{nonce}``
        """
        self._nonce += 1
        ts_ms: int = time.time_ns() // 1_000_000
        return f"{symbol}-{ts_ms}-{self._nonce}"

    # ── State transitions ──────────────────────────────────────────────────

    def transition_to(self, client_order_id: str, new_state: OrderState) -> None:
        """Transition an order to *new_state*.

        Raises:
            ValueError: If the transition is invalid.
            KeyError: If the order does not exist.
        """
        order = self._get_order_or_raise(client_order_id)
        self._transition(order, new_state)

    def _transition(self, order: Order, new_state: OrderState) -> None:
        """Internal transition that updates the order in place."""
        if not self._validate_transition(order.state, new_state):
            raise ValueError(
                f"Transicion invalida: {order.state.name} -> {new_state.name} "
                f"para orden {order.client_order_id}"
            )
        order.state = new_state
        order.updated_at = str(datetime.now(timezone.utc))

    def _validate_transition(self, from_state: OrderState, to_state: OrderState) -> bool:
        """Check if *to_state* is reachable from *from_state*."""
        if from_state in _TERMINAL_STATES:
            return False
        allowed = _VALID_TRANSITIONS.get(from_state, set())
        return to_state in allowed

    # ── Fill / reject / cancel helpers ─────────────────────────────────────

    def on_fill(
        self,
        client_order_id: str,
        qty: float,
        price: float,
        commission: float = 0.0,
    ) -> Order:
        """Record a fill against an open order.

        Accumulates ``filled_qty``, recalculates ``avg_fill_price``,
        and transitions to ``PARTIAL_FILLED`` or ``FILLED`` as appropriate.

        Returns:
            The updated :class:`Order`.
        """
        order = self._get_order_or_raise(client_order_id)
        now = str(datetime.now(timezone.utc))

        fill = Fill(qty=qty, price=price, commission=commission, timestamp=now)
        order.fills.append(fill)
        order.filled_qty += qty

        # Weighted average fill price
        total_cost = sum(f.qty * f.price for f in order.fills)
        order.avg_fill_price = total_cost / order.filled_qty
        order.updated_at = now

        # Determine state transition based on cumulative quantity
        if order.filled_qty >= order.qty - 1e-10:  # float tolerance
            self._transition(order, OrderState.FILLED)
            logger.info(
                "Orden {} completamente llenada: {} {} @ ${:.2f}",
                order.client_order_id,
                order.filled_qty,
                order.symbol,
                order.avg_fill_price,
            )
        elif order.state == OrderState.SUBMITTED:
            self._transition(order, OrderState.PARTIAL_FILLED)
            logger.info(
                "Orden {} parcialmente llenada: {}/{} {} @ ${:.2f}",
                order.client_order_id,
                order.filled_qty,
                order.qty,
                order.symbol,
                order.avg_fill_price,
            )
        # If already PARTIAL_FILLED and still not fully filled → just accumulate

        return order

    def on_reject(self, client_order_id: str, reason: str) -> None:
        """Mark an order as rejected."""
        order = self._get_order_or_raise(client_order_id)
        order.reject_reason = reason
        self._transition(order, OrderState.REJECTED)
        logger.warning("Orden {} rechazada: {}", client_order_id, reason)

    def on_cancel(self, client_order_id: str) -> None:
        """Mark an order as cancelled."""
        order = self._get_order_or_raise(client_order_id)
        self._transition(order, OrderState.CANCELLED)
        logger.info("Orden {} cancelada", client_order_id)

    # ── Reconciliation ─────────────────────────────────────────────────────

    def reconcile(self, exchange_orders: list[dict[str, Any]]) -> list[str]:
        """Compare local open orders against exchange open-order list.

        For each local order in ``SUBMITTED`` or ``PARTIAL_FILLED`` state,
        checks whether it appears in *exchange_orders* (matched by either
        ``client_order_id``, ``clientOrderId``, or ``exchange_order_id`` /
        ``orderId``).

        Args:
            exchange_orders: List of order dicts from the exchange API.
                Each dict may contain ``client_order_id``, ``clientOrderId``,
                ``exchange_order_id``, ``orderId``, or ``symbol``.

        Returns:
            List of ``client_order_id`` values that are orphans (open in
            local state but absent from the exchange).
        """
        # Build a set of known IDs from the exchange response
        exchange_ids: set[str] = set()
        for eo in exchange_orders:
            cid: str | None = (
                eo.get("client_order_id")
                or eo.get("clientOrderId")
                or eo.get("exchange_order_id")
                or eo.get("orderId")
                or eo.get("id")
            )
            if cid is not None:
                exchange_ids.add(str(cid))

        orphans: list[str] = []
        for oid, order in self._orders.items():
            if order.state not in (OrderState.SUBMITTED, OrderState.PARTIAL_FILLED):
                continue
            # Check both client_order_id and exchange_order_id
            if oid in exchange_ids or order.exchange_order_id in exchange_ids:
                continue
            orphans.append(oid)
            logger.warning("Orden huérfana detectada: {}", oid)

        return orphans

    # ── Queries ────────────────────────────────────────────────────────────

    def get_open_orders(self) -> list[Order]:
        """Return all orders in non-terminal states."""
        return [
            o for o in self._orders.values()
            if o.state not in _TERMINAL_STATES
        ]

    def get_order(self, client_order_id: str) -> Order | None:
        """Look up an order by client_order_id."""
        return self._orders.get(client_order_id)

    def get_orders_by_symbol(self, symbol: str) -> list[Order]:
        """Return all orders for a given symbol (any state)."""
        return [o for o in self._orders.values() if o.symbol == symbol]

    # ── Internal helpers ───────────────────────────────────────────────────

    def _get_order_or_raise(self, client_order_id: str) -> Order:
        """Fetch order or raise ``KeyError``."""
        order = self._orders.get(client_order_id)
        if order is None:
            raise KeyError(f"Orden no encontrada: {client_order_id}")
        return order
