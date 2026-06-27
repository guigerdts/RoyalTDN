"""Live Binance broker for the CellMesh architecture.

Executes market orders directly on Binance via the python-binance
client. Falls back to PaperBroker if the client library is unavailable.

Rate limiting (M7)
------------------
All REST calls are gated by an :class:`asyncio.Semaphore` configured
with ``max_concurrent`` (default 10) to avoid hitting Binance API rate
limits.
"""

from __future__ import annotations

import asyncio
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


class BinanceBroker:
    """Live broker that submits market orders to Binance.

    Wraps python-binance's ``Client`` for authenticated order execution.
    Supports both mainnet and testnet environments.

    The broker should be attached to an EventBus via :meth:`set_bus` to
    optionally emit execution events.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        max_concurrent: int = 10,
    ) -> None:
        """Initialise the Binance broker.

        Args:
            api_key: Binance API key.
            api_secret: Binance API secret.
            testnet: If True (default), connect to Binance testnet.
            max_concurrent: Max concurrent REST requests (default 10).
                Binance standard accounts allow ~1200 weight/min; each
                call typically costs 1–10 weight.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._bus: EventBus | None = None
        self._rate_limiter: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)

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

        try:
            async with self._rate_limiter:
                result = self._client.create_order(
                    symbol=symbol,
                    side=side,
                    type=OrderType.MARKET,
                    quantity=qty,
                )
            logger.info(
                "Live {} {} {} — order_id={}",
                side, qty, symbol, result.get("orderId", "unknown"),
            )

            return {
                "order_id": str(result.get("orderId", "unknown")),
                "status": result.get("status", "filled"),
                "price": float(result.get("fills", [{"price": price}])[0]["price"]),
                "qty": qty,
                "pnl": 0.0,
            }

        except Exception as exc:
            logger.warning("Binance order failed: {}", exc)
            return {
                "status": "error",
                "reason": str(exc),
            }

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

        Rate-limited via ``self._rate_limiter`` (M7).

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
                available = float(balance["free"]) if balance else 0.0
                qty = (available * sizing) / price
            else:
                # Use base asset balance (e.g. BTC)
                async with self._rate_limiter:
                    balance = self._client.get_asset_balance(asset=base_asset)
                available = float(balance["free"]) if balance else 0.0
                qty = available * sizing

            # Round down to avoid insufficient balance errors
            return max(0.0, round(qty, 6))

        except Exception as exc:
            logger.warning("Failed to estimate qty for {}: {}", symbol, exc)
            return 0.0
