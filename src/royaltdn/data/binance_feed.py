"""Real-time Binance WebSocket feed for the CellMesh architecture.

Subscribes to kline streams via Binance WebSocket API and emits
structured tick events (with OHLCV data) onto the shared EventBus.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from royaltdn.core.bus import EventBus


class BinanceFeed:
    """WebSocket feed that streams real-time kline data from Binance.

    Connects to Binance's combined stream endpoint, parses kline
    updates (``@kline_<interval>``), and emits them as structured
    events on the EventBus with OHLCV data.
    Supports both mainnet and testnet endpoints.
    """

    def __init__(
        self,
        symbols: list[str],
        bus: EventBus,
        testnet: bool = False,
        interval: str = "1m",
    ) -> None:
        """Initialise the feed.

        Args:
            symbols: List of trading pair symbols (e.g. ``["BTC/USDT"]``).
            bus: Shared EventBus instance to emit tick events onto.
            testnet: If True, connect to Binance testnet instead of mainnet.
            interval: Kline interval (e.g. ``"1m"``, ``"5m"``, ``"1h"``).
        """
        self.symbols = symbols
        self.bus = bus
        self.testnet = testnet
        self.interval = interval
        self._running = False
        self._ws: Any = None  # websocket connection handle

    def _build_url(self) -> str:
        """Build the combined WebSocket stream URL.

        Binance testnet does NOT support the combined ``/stream`` endpoint,
        only single-stream ``/ws``. Since the bot runs in paper mode with
        no real orders, we always use mainnet for market data — it's read-
        only and more reliable. The ``testnet`` flag controls the *broker*
        endpoint, not the data feed.

        Returns:
            Full WebSocket URL for the configured symbols.
        """
        streams = "/".join(
            f"{s.lower().replace('/', '')}@kline_{self.interval}" for s in self.symbols
        )
        return f"wss://stream.binance.com:9443/stream?streams={streams}"

    async def start(self) -> None:
        """Connect to Binance and stream ticker data indefinitely.

        Runs an infinite receive loop, parsing messages and emitting
        events onto the bus. Reconnects with exponential backoff on
        disconnection. Handles KeyboardInterrupt gracefully.

        Backoff starts at 1 s, doubles each attempt up to 60 s max.
        After 5 consecutive attempts at max backoff, logs CRITICAL
        and propagates the exception so the caller can react.
        """
        self._running = True

        import websockets

        base_delay: float = 1.0
        max_delay: float = 60.0
        multiplier: float = 2.0
        attempt: int = 0
        max_retries: int = 5

        url = self._build_url()
        logger.info("Conectando a Binance WebSocket: {}", url)

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws = ws
                    attempt = 0  # reset on successful connection
                    logger.info(
                        "WebSocket conectado para simbolos: {}", self.symbols,
                    )

                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_message(raw)

            except asyncio.CancelledError:
                logger.info("Tarea WebSocket cancelada")
                break
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt recibido, deteniendo feed")
                self._running = False
                break
            except websockets.ConnectionClosed:
                logger.warning("Conexion WebSocket cerrada")
            except Exception:
                logger.exception("Error inesperado en WebSocket")

            if not self._running:
                break

            # Exponential backoff
            delay: float = min(base_delay * (multiplier**attempt), max_delay)
            attempt += 1

            logger.info(
                "Reconectando en {:.1f}s (intento {})", delay, attempt,
            )

            # Permanent failure: 5+ consecutive attempts at max delay
            if attempt >= max_retries and delay >= max_delay:
                logger.critical(
                    "WebSocket sin conexion tras {} intentos — abortando",
                    attempt,
                )
                raise ConnectionError(
                    f"BinanceFeed no pudo reconectarse tras {attempt} intentos"
                )

            await asyncio.sleep(delay)

    async def _handle_message(self, raw: str) -> None:
        """Parse a raw WS message and emit a tick event to the bus.

        Expects kline messages from Binance combined streams:
        ``{"stream":"btcusdt@kline_1m","data":{"e":"kline","E":...,"s":"BTCUSDT","k":{...}}}``

        Args:
            raw: Raw JSON string from the WebSocket.
        """
        try:
            import json
            from datetime import datetime, timezone
            data = json.loads(raw)

            # Binance combined streams wrap payload in a "data" key
            payload = data.get("data", data)

            # Only process kline messages (skip subscription confirmations, etc.)
            if "k" not in payload:
                return

            k = payload["k"]
            event = {
                "type": "tick",
                "symbol": payload["s"],
                "price": float(k["c"]),
                "volume": float(k["v"]),
                "timestamp": datetime.fromtimestamp(
                    payload["E"] / 1000, tz=timezone.utc
                ),
                "data": {
                    "high": float(k["h"]),
                    "low": float(k["l"]),
                    "open": float(k["o"]),
                    "close": float(k["c"]),
                    "volume": float(k["v"]),
                    "quote_volume": float(k["q"]),
                    "count": k["n"],
                    "_kline_start": k["t"],
                },
            }
            await self.bus.emit(event)

        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Failed to parse kline message: {} — {}", exc, raw[:200])

    async def stop(self) -> None:
        """Gracefully stop the feed and close the WebSocket."""
        logger.info("Stopping Binance feed")
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
