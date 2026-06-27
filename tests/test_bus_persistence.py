"""Unit tests for the bus persistence subscriber.

Covers:
- ``run_persistence_subscriber`` calls ``save_signal`` for signal events
- ``run_persistence_subscriber`` calls ``save_event`` for non-signal events
- Graceful cancellation does not raise
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_subscriber_persists_signal_on_emit():
    """Signal bus events should trigger repo.save_signal()."""
    from royaltdn.core.bus import EventBus, run_persistence_subscriber

    bus = EventBus()
    repo = AsyncMock()
    repo.save_signal = AsyncMock()
    repo.save_event = AsyncMock()

    task = asyncio.create_task(run_persistence_subscriber(bus, repo))
    await asyncio.sleep(0.02)

    await bus.emit({
        "type": "signal",
        "symbol": "BTCUSDT",
        "action": "BUY",
        "price": 50000.0,
        "qty": 0.01,
        "timestamp": "2025-01-01T00:00:00",
    })
    await asyncio.sleep(0.02)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    repo.save_signal.assert_awaited_once()
    repo.save_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscriber_persists_tick_event():
    """Tick bus events should trigger repo.save_event()."""
    from royaltdn.core.bus import EventBus, run_persistence_subscriber

    bus = EventBus()
    repo = AsyncMock()
    repo.save_signal = AsyncMock()
    repo.save_event = AsyncMock()

    task = asyncio.create_task(run_persistence_subscriber(bus, repo))
    await asyncio.sleep(0.02)

    await bus.emit({
        "type": "tick",
        "symbol": "BTCUSDT",
        "price": 50000.0,
        "volume": 1.5,
        "timestamp": "2025-01-01T00:00:00",
    })
    await asyncio.sleep(0.02)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    repo.save_event.assert_awaited_once()
    repo.save_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscriber_persists_multiple_events():
    """Multiple events should each be persisted to the correct repo method."""
    from royaltdn.core.bus import EventBus, run_persistence_subscriber

    bus = EventBus()
    repo = AsyncMock()
    repo.save_signal = AsyncMock()
    repo.save_event = AsyncMock()

    task = asyncio.create_task(run_persistence_subscriber(bus, repo))
    await asyncio.sleep(0.02)

    # Emit a tick event
    await bus.emit({
        "type": "tick",
        "symbol": "ETHUSDT",
        "price": 3000.0,
        "timestamp": "2025-01-01T00:00:01",
    })
    # Emit a signal event
    await bus.emit({
        "type": "signal",
        "symbol": "BTCUSDT",
        "action": "SELL",
        "price": 51000.0,
        "qty": 0.02,
        "timestamp": "2025-01-01T00:00:02",
    })
    # Emit a trade event
    await bus.emit({
        "type": "trade",
        "symbol": "BTCUSDT",
        "action": "SELL",
        "price": 51000.0,
        "qty": 0.02,
        "order_id": "ord_123",
        "timestamp": "2025-01-01T00:00:03",
    })
    await asyncio.sleep(0.02)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert repo.save_signal.await_count == 1  # only the signal event
    assert repo.save_event.await_count == 2   # tick + trade


@pytest.mark.asyncio
async def test_subscriber_defaults_to_get_repository():
    """When repo is not provided, uses get_repository() singleton."""
    import royaltdn.db
    from royaltdn.core.bus import EventBus, run_persistence_subscriber

    bus = EventBus()
    original = royaltdn.db.get_repository()
    assert not original.is_connected  # NullDBRepository by default

    # Should not crash even with NullDBRepository
    task = asyncio.create_task(run_persistence_subscriber(bus))
    await asyncio.sleep(0.02)

    await bus.emit({"type": "tick", "symbol": "BTCUSDT", "price": 50000})
    await asyncio.sleep(0.02)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # No exception = pass


@pytest.mark.asyncio
async def test_subscriber_cancellation_graceful():
    """Cancelling the subscriber task should not raise outside CancelledError."""
    from royaltdn.core.bus import EventBus, run_persistence_subscriber

    bus = EventBus()
    repo = AsyncMock()
    repo.save_signal = AsyncMock()
    repo.save_event = AsyncMock()

    task = asyncio.create_task(run_persistence_subscriber(bus, repo))
    await asyncio.sleep(0.02)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
