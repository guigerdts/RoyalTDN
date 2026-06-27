"""Unit tests for TelegramAlerts rejection formatting and batch buffer.

Covers:
- _fmt_rejected() includes the detail string verbatim
- Missing detail uses default "risk_rejected"
- _fmt_single() with rejection events
- Event accumulation in _pending_events (4.1)
- Event filtering by type (4.2)
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def telegram():
    """Return a TelegramAlerts instance with minimal setup."""
    from royaltdn.monitoring.telegram_alerts import TelegramAlerts

    bus = type("FakeBus", (), {"subscribe": lambda self: __import__("asyncio").Queue()})()
    return TelegramAlerts(bus, bot_token="test", chat_id="test")


# ── _fmt_rejected ────────────────────────────────────────────────────────


def test_fmt_rejected_includes_detail(telegram):
    """_fmt_rejected should include the detail string verbatim."""
    event = {"type": "rejected", "reason": "Límite de 5 posiciones alcanzado"}
    pending = {"symbol": "BTCUSDT", "action": "BUY", "strategy": "swing_1"}
    result = telegram._fmt_rejected(event, pending)

    assert "Límite de 5 posiciones alcanzado" in result
    assert "BTCUSDT" in result
    assert "swing_1" in result


def test_fmt_rejected_detail_with_special_chars(telegram):
    """_fmt_rejected should handle detail with special characters."""
    event = {"type": "rejected", "reason": "Drawdown 15.2% supera límite 10%"}
    pending = {"symbol": "BTCUSDT", "action": "BUY"}
    result = telegram._fmt_rejected(event, pending)

    assert "Drawdown 15.2%" in result
    assert "BTCUSDT" in result


def test_fmt_rejected_missing_detail(telegram):
    """_fmt_rejected with missing detail should default to 'risk_rejected'."""
    event = {"type": "rejected"}
    pending = {"symbol": "BTCUSDT", "action": "SELL"}
    result = telegram._fmt_rejected(event, pending)

    assert "risk_rejected" in result
    assert "BTCUSDT" in result


def test_fmt_rejected_no_pending(telegram):
    """_fmt_rejected should fall back to event fields when pending is empty."""
    event = {"type": "rejected", "symbol": "ETHUSDT", "action": "BUY",
             "reason": "max_positions"}
    pending = {}
    result = telegram._fmt_rejected(event, pending)

    assert "max_positions" in result
    assert "ETHUSDT" in result


# ── _fmt_single ──────────────────────────────────────────────────────────


def test_fmt_single_rejection(telegram):
    """_fmt_single with rejected event should include detail."""
    event = {"type": "rejected", "symbol": "BTCUSDT", "action": "BUY",
             "reason": "Drawdown 5% supera límite 3%"}
    result = telegram._fmt_single(event)

    assert result is not None
    assert "Drawdown 5%" in result
    assert "BTCUSDT" in result


def test_fmt_single_rejection_default_reason(telegram):
    """_fmt_single with rejected event but missing reason → 'risk_rejected'."""
    event = {"type": "rejected", "symbol": "BTCUSDT", "action": "BUY"}
    result = telegram._fmt_single(event)

    assert result is not None
    assert "risk_rejected" in result


def test_fmt_single_other_types_work(telegram):
    """_fmt_single should still format non-rejected events."""
    event = {"type": "signal", "symbol": "BTCUSDT", "action": "BUY",
             "price": 50000.0, "strategy": "swing_1"}
    result = telegram._fmt_single(event)

    assert result is not None
    assert "BTCUSDT" in result


# ── Batch buffer — accumulation (spec 4.1) ──────────────────────────────


def _run_handle(telegram, event):
    """Helper: run _handle_event synchronously via asyncio.run."""
    client = type("FakeClient", (), {"post": lambda *a, **kw: None})()
    asyncio.run(telegram._handle_event(client, event))


def test_accumulates_executed(telegram):
    """executed events should go to _pending_events, not send immediately."""
    event = {"type": "executed", "trade_id": "t1",
             "symbol": "BTCUSDT", "action": "BUY", "qty": 0.5, "price": 50000}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 1
    assert telegram._pending_events[0] is event


def test_accumulates_rejected(telegram):
    """rejected events should go to _pending_events, not send immediately."""
    event = {"type": "rejected", "trade_id": "t1",
             "symbol": "BTCUSDT", "action": "BUY", "reason": "max_positions"}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 1
    assert telegram._pending_events[0] is event


def test_accumulates_position_closed(telegram):
    """position.closed events should go to _pending_events."""
    event = {"type": "position", "status": "closed",
             "symbol": "BTCUSDT", "pnl": 100.0}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 1
    assert telegram._pending_events[0] is event


def test_accumulates_multiple_events(telegram):
    """Multiple qualifying events accumulate in order."""
    ev1 = {"type": "executed", "trade_id": "t1",
           "symbol": "BTCUSDT", "action": "BUY"}
    ev2 = {"type": "rejected", "trade_id": "t2",
           "symbol": "ETHUSDT", "action": "SELL", "reason": "risk"}
    ev3 = {"type": "position", "status": "closed",
           "symbol": "BTCUSDT", "pnl": 50.0}

    _run_handle(telegram, ev1)
    _run_handle(telegram, ev2)
    _run_handle(telegram, ev3)

    assert len(telegram._pending_events) == 3
    assert telegram._pending_events[0] is ev1
    assert telegram._pending_events[1] is ev2
    assert telegram._pending_events[2] is ev3


def test_accumulates_rejected_without_trade_id(telegram):
    """rejected without trade_id still routes to buffer."""
    event = {"type": "rejected", "symbol": "BTCUSDT",
             "action": "BUY", "reason": "no_trade"}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 1


def test_accumulates_executed_without_trade_id(telegram):
    """executed without trade_id still routes to buffer."""
    event = {"type": "executed", "symbol": "BTCUSDT",
             "action": "BUY", "qty": 0.5, "price": 50000}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 1


# ── Batch buffer — filtering (spec 4.2) ─────────────────────────────────


def test_filters_signal(telegram):
    """signal events should NOT appear in _pending_events."""
    event = {"type": "signal", "trade_id": "t1", "symbol": "BTCUSDT"}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 0


def test_filters_approved(telegram):
    """approved events should NOT appear in _pending_events."""
    telegram._pending["t1"] = {"symbol": "BTCUSDT", "action": "BUY"}
    event = {"type": "approved", "trade_id": "t1"}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 0


def test_filters_position_opened(telegram):
    """position.opened events should NOT appear in _pending_events."""
    telegram._pending["t1"] = {"symbol": "BTCUSDT", "action": "BUY"}
    event = {"type": "position", "status": "opened", "trade_id": "t1"}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 0


def test_filters_unknown_event_type(telegram):
    """Unrecognised event types should be ignored entirely."""
    event = {"type": "unknown", "trade_id": "t1"}
    _run_handle(telegram, event)

    assert len(telegram._pending_events) == 0


def test_pending_cleanup_on_position_opened(telegram):
    """position.opened should remove trade_id from _pending."""
    telegram._pending["t1"] = {"symbol": "BTCUSDT", "action": "BUY"}
    event = {"type": "position", "status": "opened", "trade_id": "t1"}
    _run_handle(telegram, event)

    assert "t1" not in telegram._pending
    assert len(telegram._pending_events) == 0


def test_pending_cleanup_on_rejected(telegram):
    """rejected should remove trade_id from _pending."""
    telegram._pending["t1"] = {"symbol": "BTCUSDT", "action": "BUY"}
    event = {"type": "rejected", "trade_id": "t1", "reason": "risk"}
    _run_handle(telegram, event)

    assert "t1" not in telegram._pending
    assert len(telegram._pending_events) == 1


# ── Batch message grouping (spec 4.3) ────────────────────────────────


def test_grouping_merges_same_type_symbol(telegram):
    """Same type+symbol+reason events merge with Nx prefix (spec 4.3)."""
    ev1 = {"type": "rejected", "symbol": "LINKUSDT",
           "action": "BUY", "reason": "max_positions"}
    ev2 = {"type": "rejected", "symbol": "LINKUSDT",
           "action": "BUY", "reason": "max_positions"}
    ev3 = {"type": "rejected", "symbol": "LINKUSDT",
           "action": "BUY", "reason": "max_positions"}
    telegram._pending_events = [ev1, ev2, ev3]
    msg = telegram._build_batch_message()

    assert "3x" in msg
    assert "LINKUSDT" in msg
    assert "max_positions" in msg
    # Single events without count prefix
    assert "1x" not in msg


def test_single_event_no_count_prefix(telegram):
    """A single event renders without '1x' prefix (spec 4.3)."""
    ev = {"type": "rejected", "symbol": "BTCUSDT",
          "action": "SELL", "reason": "risk_check"}
    telegram._pending_events = [ev]
    msg = telegram._build_batch_message()

    assert "1x" not in msg
    assert "BTCUSDT" in msg
    assert "risk_check" in msg


def test_grouping_different_symbols_separate(telegram):
    """Events with different symbols produce separate lines."""
    ev1 = {"type": "rejected", "symbol": "BTCUSDT",
           "action": "BUY", "reason": "max_positions"}
    ev2 = {"type": "rejected", "symbol": "ETHUSDT",
           "action": "BUY", "reason": "max_positions"}
    telegram._pending_events = [ev1, ev2]
    msg = telegram._build_batch_message()

    assert "BTCUSDT" in msg
    assert "ETHUSDT" in msg
    assert "2x" not in msg  # different symbols, not merged


# ── Message format sections (spec 4.4) ───────────────────────────────


def test_message_format_sections(telegram):
    """Full batched message has header, sections, separator, footer (spec 4.4)."""
    telegram._pending_events = [
        {"type": "executed", "symbol": "BTCUSDT",
         "action": "BUY", "qty": 0.5, "price": 50000},
        {"type": "rejected", "symbol": "ETHUSDT",
         "action": "SELL", "reason": "risk"},
        {"type": "position", "status": "closed",
         "symbol": "BTCUSDT", "pnl": 100.0},
    ]
    msg = telegram._build_batch_message()

    assert "RESUMEN DEL \u00daLTIMO MINUTO" in msg
    assert "\u2705 Ejecuciones:" in msg
    assert "\u274c Rechazos:" in msg
    assert "\U0001f534 Cierres:" in msg
    assert "\u2014\u2014\u2014" in msg  # separator
    assert "Capital:" in msg
    # Drawdown not present: fixture has no portfolio


def test_message_format_single_type_only(telegram):
    """Only one event type → only that section appears."""
    telegram._pending_events = [
        {"type": "rejected", "symbol": "BTCUSDT",
         "action": "BUY", "reason": "max_positions"},
        {"type": "rejected", "symbol": "ETHUSDT",
         "action": "BUY", "reason": "risk"},
    ]
    msg = telegram._build_batch_message()

    assert "\u274c Rechazos:" in msg
    assert "\u2705 Ejecuciones:" not in msg
    assert "\U0001f534 Cierres:" not in msg


def test_single_event_shorter_format(telegram):
    """Exactly one event → shorter format without section headers."""
    ev = {"type": "executed", "symbol": "BTCUSDT",
          "action": "BUY", "qty": 0.5, "price": 50000}
    telegram._pending_events = [ev]
    msg = telegram._build_batch_message()

    # No section headers for single event
    assert "\u2705 Ejecuciones:" not in msg
    assert "RESUMEN DEL \u00daLTIMO MINUTO" not in msg
    # But has the event detail
    assert "BUY" in msg
    assert "BTCUSDT" in msg
    # And footer
    assert "\u2014\u2014\u2014" in msg


# ── Message length guard (spec 4.5) ──────────────────────────────────


def test_split_message_noop_small(telegram):
    """_split_message returns single chunk when under limit."""
    text = "Hello world"
    chunks = telegram._split_message(text, max_len=100)
    assert chunks == [text]


def test_split_message_splits_at_newlines(telegram):
    """_split_message splits at newline boundaries when over limit."""
    lines = [f"Line {i} " + "x" * 80 for i in range(100)]
    text = "\n".join(lines)
    chunks = telegram._split_message(text, max_len=500)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 500


def test_split_message_all_chunks_under_limit(telegram):
    """Every chunk from _split_message is <= max_len."""
    lines = [f"Line {i} " + "data" * 30 for i in range(200)]
    text = "\n".join(lines)
    max_len = 4000
    chunks = telegram._split_message(text, max_len=max_len)

    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert len(chunk) <= max_len, (
            f"Chunk {i} is {len(chunk)} chars (max {max_len})"
        )


def test_split_message_preserves_lines(telegram):
    """_split_message preserves original lines in order."""
    lines = [f"LINE_{i:04d}" for i in range(100)]
    text = "\n".join(lines)
    max_len = 500
    chunks = telegram._split_message(text, max_len=max_len)

    reconstructed = "\n".join(chunks)
    assert reconstructed == text


# ── Empty flush (spec 4.6) ───────────────────────────────────────────


def test_empty_flush_sends_nothing(telegram):
    """_flush with empty buffer does not call _send (spec 4.6)."""
    from unittest.mock import AsyncMock

    client = AsyncMock()
    asyncio.run(telegram._flush(client))
    client.post.assert_not_called()


# ── Shutdown flush (spec 4.7) ────────────────────────────────────────


def test_shutdown_flush_sends_remaining(telegram):
    """stop() flushes remaining events before cancelling (spec 4.7)."""
    from unittest.mock import AsyncMock, patch

    async def _run():
        telegram._pending_events = [
            {"type": "executed", "symbol": "BTCUSDT",
             "action": "BUY", "qty": 0.5, "price": 50000},
        ]
        telegram._flush_task = asyncio.create_task(asyncio.sleep(9999))

        with patch.object(telegram, "_send", new=AsyncMock()) as mock_send:
            await telegram.stop()
            mock_send.assert_called_once()
        assert len(telegram._pending_events) == 0

    asyncio.run(_run())


def test_shutdown_flush_empty_buffer(telegram):
    """stop() with empty buffer sends nothing (spec 4.7)."""
    from unittest.mock import AsyncMock, patch

    async def _run():
        telegram._flush_task = asyncio.create_task(asyncio.sleep(9999))

        with patch.object(telegram, "_send", new=AsyncMock()) as mock_send:
            await telegram.stop()
            mock_send.assert_not_called()

    asyncio.run(_run())
