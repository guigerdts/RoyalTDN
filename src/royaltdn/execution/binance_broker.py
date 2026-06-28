"""Live Binance broker for the CellMesh architecture.

Executes market orders directly on Binance via the python-binance
client. Falls back to PaperBroker if the client library is unavailable.

Rate limiting (M7)
------------------
REST calls are gated by an :class:`asyncio.Semaphore` (max concurrent)
*and* a weight-based throttle that tracks the ``x-mbx-used-weight-1m``
response header to stay under Binance's 1200 weight/min limit.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from royaltdn.core.bus import EventBus
from royaltdn.execution.paper_broker import PaperBroker

try:
    from binance.client import Client
    from binance.enums import Side, OrderType

    _BINANCE_AVAILABLE = True
except ImportError:
    _BINANCE_AVAILABLE = False
    logger.warning(
        "python-binance not installed. BinanceBroker will emit "
        "a critical warning and return an error."
    )


_WEIGHT_LIMIT: int = 1200
"""Binance standard account weight limit per rolling 1-minute window."""


class BinanceBroker:
    """Live broker that submits market orders to Binance.

    Wraps python-binance's ``Client`` for authenticated order execution.
    Supports both mainnet and testnet environments.

    Rate limiting is two-tier:
    * An ``asyncio.Semaphore`` limits concurrent in-flight requests.
    * A weight-based throttle delays calls when ``x-mbx-used-weight-1m``
      exceeds 80 % of ``_WEIGHT_LIMIT``.

    The broker should be attached to an EventBus via :meth:`set_bus` to
    optionally emit execution events.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        max_concurrent: int = 10,
        order_manager: Any = None,
    ) -> None:
        """Initialise the Binance broker.

        Args:
            api_key: Binance API key.
            api_secret: Binance API secret.
            testnet: If True (default), connect to Binance testnet.
            max_concurrent: Max concurrent REST requests (default 10).
                Binance standard accounts allow ~1200 weight/min; each
                call typically costs 1–10 weight.
            order_manager: Optional :class:`OrderManager` for lifecycle
                tracking.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.order_manager = order_manager
        self._bus: EventBus | None = None
        self._rate_limiter: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)

        # Weight-based rate tracking
        self._weight_used: int = 0
        self._last_weight_reset: float = time.monotonic()

        if _BINANCE_AVAILABLE:
            self._client = Client(api_key, api_secret, testnet=testnet)
            logger.info("BinanceBroker initialised (testnet={})", testnet)
        else:
            self._client = None
            logger.critical(
                "python-binance is not installed. Install it with: "
                "pip install python-binance"
            )

    def set_bus(self, bus: EventBus) -> None:
        """Attach an EventBus for optional event emission.

        Args:
            bus: Shared EventBus instance.
        """
        self._bus = bus

    # ── Weight management ─────────────────────────────────────────────

    async def _manage_weight(self) -> None:
        """Check weight usage from the last API response and back off.

        Reads the ``x-mbx-used-weight-1m`` header that ``python-binance``
        stores on ``self._client.response`` after every call.  When usage
        exceeds 80 % of the limit, sleeps for a delay proportional to how
        close we are to the ceiling.
        """
        if not _BINANCE_AVAILABLE or self._client is None:
            return

        response = getattr(self._client, "response", None)
        if response is None:
            return

        weight_str: str | None = response.headers.get("x-mbx-used-weight-1m")
        if weight_str is None:
            weight_str = response.headers.get("x-mbx-used-weight")

        if not weight_str:
            return

        try:
            self._weight_used = int(weight_str)
        except (ValueError, TypeError):
            return

        usage_ratio: float = self._weight_used / _WEIGHT_LIMIT
        if usage_ratio <= 0.8:
            return

        # Proportional backoff: the closer to the limit, the longer we wait.
        # At 80 % → 0.5 s, at 95 % → 2.0 s, at 100 % → 5.0 s.
        extra: float = (usage_ratio - 0.8) / 0.2  # 0.0 at 80 %, 1.0 at 100 %
        delay: float = min(5.0, 0.5 + extra * 4.5)

        logger.warning(
            "Binance weight {}% usado ({} / {}), esperando {:.1f}s",
            round(usage_ratio * 100, 1),
            self._weight_used,
            _WEIGHT_LIMIT,
            delay,
        )
        await asyncio.sleep(delay)

    # ── Order execution ───────────────────────────────────────────────

    async def submit_order(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Submit a market order to Binance based on a cell signal.

        Args:
            signal: Dict with ``symbol`` (e.g. ``"BTCUSDT"``),
                ``action`` (``"BUY"`` / ``"SELL"``), ``price``,
                and ``sizing`` (fraction of capital).

        Returns:
            Order result dict with ``order_id``, ``status``, ``price``,
            ``qty``, or error details on failure.

        Raises:
            RuntimeError: If python-binance is not installed.
        """
        if not _BINANCE_AVAILABLE or self._client is None:
            logger.critical("python-binance unavailable — cannot execute live order")
            return {
                "status": "error",
                "reason": "python-binance not installed. Use PaperBroker or install python-binance.",
            }

        symbol: str = signal["symbol"]
        action: str = signal["action"]
        price: float = signal["price"]
        sizing: float = signal.get("sizing", 0.01)

        # Map action to Binance enum
        if action == "BUY":
            side = Side.BUY
        elif action in ("SELL", "SHORT"):
            side = Side.SELL
        else:
            logger.warning("Unknown action '{}' in signal", action)
            return {"status": "error", "reason": f"Unknown action: {action}"}

        # Estimate quantity from capital (simplified — user should
        # pass a pre-calculated qty via signal for production)
        # Here we use the signal's price as a rough quote
        qty = await self._estimate_qty(symbol, side, sizing, price)
        if qty <= 0:
            return {"status": "error", "reason": f"Estimated qty <= 0 for {symbol}"}

        # ── OrderManager integration ─────────────────────────────────────
        _om_client_id: str | None = None
        if self.order_manager is not None:
            from royaltdn.execution.order_manager import OrderState

            order = self.order_manager.create_order(
                symbol=symbol,
                side=action,
                qty=qty,
                price=price,
                order_type="MARKET",
            )
            _om_client_id = order.client_order_id
            self.order_manager.transition_to(_om_client_id, OrderState.PENDING_SUBMIT)
            self.order_manager.transition_to(_om_client_id, OrderState.SUBMITTED)

        try:
            async with self._rate_limiter:
                kwargs: dict[str, Any] = {
                    "symbol": symbol,
                    "side": side,
                    "type": OrderType.MARKET,
                    "quantity": qty,
                }
                if _om_client_id is not None:
                    kwargs["newClientOrderId"] = _om_client_id
                result = self._client.create_order(**kwargs)
                await self._manage_weight()

            exchange_order_id: str = str(result.get("orderId", "unknown"))

            # Update order manager with exchange_order_id and fill
            if self.order_manager is not None and _om_client_id is not None:
                self.order_manager._orders[_om_client_id].exchange_order_id = (
                    exchange_order_id
                )
                # Binance fills are usually immediate for MARKET orders
                fill_price_val: float = float(
                    result.get("fills", [{"price": price}])[0]["price"]
                )
                fill_commission: float = sum(
                    float(f.get("commission", 0))
                    for f in result.get("fills", [])
                )
                self.order_manager.on_fill(
                    _om_client_id,
                    qty,
                    fill_price_val,
                    commission=fill_commission,
                )

            logger.info(
                "Live {} {} {} — order_id={}",
                side, qty, symbol, exchange_order_id,
            )

            return {
                "order_id": exchange_order_id,
                "client_order_id": _om_client_id or "",
                "status": result.get("status", "filled"),
                "price": float(result.get("fills", [{"price": price}])[0]["price"]),
                "qty": qty,
                "pnl": 0.0,
            }

        except Exception as exc:
            # Mark order as rejected in order manager
            if self.order_manager is not None and _om_client_id is not None:
                self.order_manager.on_reject(_om_client_id, str(exc))
            logger.warning("Binance order failed: {}", exc)
            return {
                "status": "error",
                "reason": str(exc),
            }

    # ── Order management (KillSwitch / OrderManager integration) ─────────

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel a single order on Binance.

        Args:
            symbol: Trading pair symbol.
            order_id: Exchange order ID or client order ID.

        Returns:
            Cancel result dict.
        """
        if not _BINANCE_AVAILABLE or self._client is None:
            logger.warning("python-binance no disponible — no se puede cancelar orden")
            return {"status": "error", "reason": "python-binance not available"}

        try:
            result = self._client.cancel_order(symbol=symbol, orderId=order_id)
            logger.info("Orden cancelada en Binance: {} {}", symbol, order_id)

            # Update order manager if available
            if self.order_manager is not None:
                self.order_manager.on_cancel(order_id)

            return {"status": "cancelled", "order_id": order_id}
        except Exception as exc:
            logger.warning("Error cancelando orden {} {}: {}", symbol, order_id, exc)
            return {"status": "error", "reason": str(exc)}

    def cancel_all_orders(self) -> list[dict[str, Any]]:
        """Cancel all open orders on Binance.

        Returns:
            List of cancel result dicts.
        """
        if not _BINANCE_AVAILABLE or self._client is None:
            logger.warning("python-binance no disponible — no se pueden cancelar ordenes")
            return []

        results: list[dict[str, Any]] = []
        try:
            open_orders = self._client.get_open_orders()
            for order in open_orders:
                sym: str = order["symbol"]
                oid: str = str(order["orderId"])
                result = self._client.cancel_order(symbol=sym, orderId=oid)
                results.append(result)

                if self.order_manager is not None:
                    # Try matching by exchange_order_id
                    client_id = order.get("clientOrderId", "")
                    if client_id and self.order_manager.get_order(client_id):
                        self.order_manager.on_cancel(client_id)

                logger.info("Orden cancelada: {} {} ({})", sym, oid, order.get("status"))
            logger.info(
                "Todas las ordenes canceladas en Binance ({} total)",
                len(open_orders),
            )
        except Exception as exc:
            logger.warning("Error cancelando ordenes en Binance: {}", exc)

        return results

    def reconcile_orders(self) -> list[str]:
        """Reconcile local OrderManager state with exchange open orders.

        Returns:
            List of orphan ``client_order_id`` values.
        """
        if self.order_manager is None:
            logger.warning("No hay OrderManager — no se puede reconciliar")
            return []

        if not _BINANCE_AVAILABLE or self._client is None:
            logger.warning("python-binance no disponible — no se puede reconciliar")
            return []

        try:
            exchange_orders: list[dict[str, Any]] = self._client.get_open_orders()
            orphans = self.order_manager.reconcile(exchange_orders)
            if orphans:
                logger.warning(
                    "Reconciliacion: {} ordenes huerfanas detectadas",
                    len(orphans),
                )
            else:
                logger.info("Reconciliacion: todas las ordenes coinciden")
            return orphans
        except Exception as exc:
            logger.warning("Error durante reconciliacion: {}", exc)
            return []

    @staticmethod
    def _parse_symbol(symbol: str) -> tuple[str, str]:
        """Split a Binance trading pair into (base, quote) asset.

        Binance symbols are concatenated base+quote (e.g. ``"BTCUSDT"``,
        ``"ETHBTC"``). This method strips known quote-asset suffixes to
        extract each side.

        Args:
            symbol: Trading pair, e.g. ``"BTCUSDT"``, ``"ETHBTC"``.

        Returns:
            Tuple of ``(base_asset, quote_asset)``.

        Raises:
            ValueError: If no known quote suffix is found.
        """
        # Known quote assets — longest first to avoid partial matches
        known_quotes = [
            "BUSD", "USDC", "USDT", "PAX", "TUSD", "USDS",
            "BTC", "ETH", "BNB", "XRP",
            "BRL", "EUR", "TRY", "GBP",
            "DAI", "FDUSD",
        ]

        for quote in known_quotes:
            if symbol.endswith(quote) and len(symbol) > len(quote):
                base = symbol[: -len(quote)]
                return base, quote

        raise ValueError(
            f"Cannot parse symbol '{symbol}': no known quote suffix found"
        )

    async def _estimate_qty(
        self,
        symbol: str,
        side: Any,
        sizing: float,
        price: float,
    ) -> float:
        """Estimate order quantity from available balance.

        Rate-limited via ``self._rate_limiter`` and weight-managed via
        ``_manage_weight`` after each API call.

        Args:
            symbol: Trading pair.
            side: Binance Side enum (BUY/SELL).
            sizing: Fraction of available balance to use.
            price: Estimated execution price.

        Returns:
            Estimated quantity, floored to a safe value.
        """
        try:
            base_asset, quote_asset = self._parse_symbol(symbol)
            if side == Side.BUY:
                # Use quote asset balance (e.g. USDT)
                async with self._rate_limiter:
                    balance = self._client.get_asset_balance(asset=quote_asset)
                    await self._manage_weight()
                available = float(balance["free"]) if balance else 0.0
                qty = (available * sizing) / price
            else:
                # Use base asset balance (e.g. BTC)
                async with self._rate_limiter:
                    balance = self._client.get_asset_balance(asset=base_asset)
                    await self._manage_weight()
                available = float(balance["free"]) if balance else 0.0
                qty = available * sizing

            # Round down to avoid insufficient balance errors
            return max(0.0, round(qty, 6))

        except Exception as exc:
            logger.warning("Failed to estimate qty for {}: {}", symbol, exc)
            return 0.0
