"""Real-time Binance WebSocket feed for the CellMesh architecture.

Subscribes to ticker streams via Binance WebSocket API and emits
structured tick events onto the shared EventBus.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import websockets
from loguru import logger

from core.bus import EventBus


class BinanceFeed:
    """WebSocket feed that streams real-time ticker data from Binance.

    Connects to Binance's combined stream endpoint, parses 24hr ticker
    updates, and emits them as structured events on the EventBus.
    Supports both mainnet and testnet endpoints.
    """

    def __init__(
        self,
        symbols: list[str],
        bus: EventBus,
        testnet: bool = False,
    ) -> None:
        """Initialise the feed.

        Args:
            symbols: List of trading pair symbols (e.g. ``["BTC/USDT"]``).
            bus: Shared EventBus instance to emit tick events onto.
            testnet: If True, connect to Binance testnet instead of mainnet.
        """
        self.symbols = symbols
        self.bus = bus
        self.testnet = testnet
        self._running = False
        self._ws: Any = None  # websocket connection handle

    def _build_url(self) -> str:
        """Build the combined WebSocket stream URL.

        Returns:
            Full WebSocket URL for the configured symbols.
        """
        streams = "/".join(
            f"{s.lower().replace('/', '')}@ticker" for s in self.symbols
        )
        if self.testnet:
            return f"wss://testnet.binance.vision/stream?streams={streams}"
        return f"wss://stream.binance.com:9443/stream?streams={streams}"

    async def start(self) -> None:
        """Connect to Binance and stream ticker data indefinitely.

        Runs an infinite receive loop, parsing messages and emitting
        events onto the bus. Reconnects with exponential backoff on
        disconnection. Handles KeyboardInterrupt gracefully.
        """
        self._running = True
        retry_delays = [3, 10, 30]
        attempt = 0

        url = self._build_url()
        logger.info("Connecting to Binance WebSocket: {}", url)

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws = ws
                    attempt = 0  # reset on successful connection
                    logger.info("WebSocket connected for symbols: {}", self.symbols)

                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_message(raw)

            except asyncio.CancelledError:
                logger.info("WebSocket task cancelled")
                break
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt received, stopping feed")
                self._running = False
                break
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed")
            except Exception:
                logger.exception("Unexpected WebSocket error")

            if not self._running:
                break

            delay = retry_delays[min(attempt, len(retry_delays) - 1)]
            logger.info("Reconnecting in {}s (attempt {})", delay, attempt + 1)
            await asyncio.sleep(delay)
            attempt += 1

    async def _handle_message(self, raw: str) -> None:
        """Parse a raw WS message and emit a tick event to the bus.

        Args:
            raw: Raw JSON string from the WebSocket.
        """
        try:
            data = json.loads(raw)

            # Binance combined streams wrap payload in a "data" key
            ticker = data.get("data", data)
            event = {
                "type": "tick",
                "symbol": ticker["s"],
                "price": float(ticker["c"]),
                "volume": float(ticker["v"]),
                "timestamp": datetime.fromtimestamp(
                    ticker["E"] / 1000, tz=timezone.utc
                ),
                "data": {
                    "high": float(ticker["h"]),
                    "low": float(ticker["l"]),
                    "open": float(ticker["o"]),
                    "close": float(ticker["c"]),
                    "volume": float(ticker["v"]),
                    "quote_volume": float(ticker["q"]),
                    "count": ticker["n"],
                },
            }
            await self.bus.emit(event)

        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Failed to parse ticker message: {} — {}", exc, raw[:200])

    async def stop(self) -> None:
        """Gracefully stop the feed and close the WebSocket."""
        logger.info("Stopping Binance feed")
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
