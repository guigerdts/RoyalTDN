"""Unit tests for BinanceFeed kline message parsing.

Tests cover the kline message parser in ``_handle_message()``:
correct field extraction, non-kline message skipping, combined
stream format support, and open candle filtering.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def bus():
    """Create a mocked EventBus with an async emit method."""
    from unittest.mock import AsyncMock, MagicMock
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def feed(bus):
    """Create a BinanceFeed instance configured for testing."""
    from royaltdn.data.binance_feed import BinanceFeed
    return BinanceFeed(symbols=["BTC/USDT"], bus=bus)


SAMPLE_KLINE = {
    "stream": "btcusdt@kline_1m",
    "data": {
        "e": "kline",
        "E": 1719676800000,
        "s": "BTCUSDT",
        "k": {
            "t": 1719676800000,
            "T": 1719676859999,
            "o": "59300.00",
            "c": "59350.00",
            "h": "59400.00",
            "l": "59250.00",
            "v": "100.5",
            "q": "5960000",
            "n": 150,
            "x": False,
        },
    },
}


@pytest.mark.asyncio
async def test_kline_message_parses_correctly(bus) -> None:
    """Verify all fields are correctly extracted from a kline message."""
    import json
    from royaltdn.data.binance_feed import BinanceFeed

    feed = BinanceFeed(symbols=["BTC/USDT"], bus=bus)
    raw = json.dumps(SAMPLE_KLINE)
    await feed._handle_message(raw)

    bus.emit.assert_awaited_once()
    event = bus.emit.await_args[0][0]

    assert event["type"] == "tick"
    assert event["symbol"] == "BTCUSDT"
    assert event["price"] == 59350.00
    assert event["volume"] == 100.5
    assert event["timestamp"] is not None

    data = event["data"]
    assert data["high"] == 59400.00
    assert data["low"] == 59250.00
    assert data["open"] == 59300.00
    assert data["close"] == 59350.00
    assert data["volume"] == 100.5
    assert data["quote_volume"] == 5960000.0
    assert data["count"] == 150
    assert data["_kline_start"] == 1719676800000


@pytest.mark.asyncio
async def test_non_kline_message_skipped(bus) -> None:
    """Verify messages without a ``k`` key are silently skipped."""
    import json
    from royaltdn.data.binance_feed import BinanceFeed

    feed = BinanceFeed(symbols=["BTC/USDT"], bus=bus)
    raw = json.dumps({
        "stream": "btcusdt@kline_1m",
        "data": {"e": "kline", "E": 1719676800000, "s": "BTCUSDT"},
    })
    await feed._handle_message(raw)
    bus.emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_combined_stream_format(bus) -> None:
    """Verify combined stream ``data`` wrapper is handled."""
    import json
    from royaltdn.data.binance_feed import BinanceFeed

    feed = BinanceFeed(symbols=["BTC/USDT"], bus=bus)
    raw = json.dumps(SAMPLE_KLINE)
    await feed._handle_message(raw)
    bus.emit.assert_awaited_once()
    event = bus.emit.await_args[0][0]
    assert event["symbol"] == "BTCUSDT"
    assert event["price"] == 59350.00


@pytest.mark.asyncio
async def test_all_candle_updates_processed(bus) -> None:
    """Verify open candles (``x: false``) are NOT filtered out."""
    import json
    from royaltdn.data.binance_feed import BinanceFeed

    feed = BinanceFeed(symbols=["BTC/USDT"], bus=bus)
    raw = json.dumps(SAMPLE_KLINE)
    await feed._handle_message(raw)
    bus.emit.assert_awaited_once()
