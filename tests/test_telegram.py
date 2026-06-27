"""Unit tests for TelegramAlerts rejection formatting.

Covers:
- _fmt_rejected() includes the detail string verbatim
- Missing detail uses default "risk_rejected"
- _fmt_single() with rejection events
"""

from __future__ import annotations

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
