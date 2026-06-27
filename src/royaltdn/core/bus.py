"""Central event bus for the CellMesh architecture.

Provides asynchronous event communication between autonomous cells
using an asyncio.Queue as the backbone.
"""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    """Async event bus for publish-subscribe communication.

    Events are dicts with a standard set of fields. Multiple consumers
    can subscribe independently via ``subscribe()``; every event emitted
    is broadcast to all registered queues.

    Backward-compatible: existing ``get()`` uses the primary subscriber
    queue.
    """

    def __init__(self) -> None:
        """Initialise the bus with a primary subscriber queue."""
        self._queues: list[asyncio.Queue[dict[str, Any]]] = [
            asyncio.Queue()
        ]

    async def emit(self, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        Args:
            event: Dict with standard fields:
                type: Event type string (e.g. 'tick', 'signal', 'order').
                symbol: Trading pair symbol (e.g. 'BTC/USD').
                price: Current price.
                volume: Current volume.
                timestamp: ISO-format or datetime timestamp.
                data: Optional dict for extra payload.
        """
        for q in self._queues:
            await q.put(event)

    async def get(self) -> dict[str, Any]:
        """Retrieve the next event from the primary queue.

        Returns:
            The next event dict from the primary queue.
        """
        return await self._queues[0].get()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register a new subscriber queue.

        The caller receives a dedicated ``asyncio.Queue`` that will
        receive every event emitted after subscription.

        Returns:
            A new asyncio.Queue attached to the broadcast.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.append(q)
        return q
