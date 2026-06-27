"""Unit tests for RiskManager: structured rejection paths, SHORT approve, and BUY-to-close.

Covers:
- All 6 structured rejection paths return correct reason strings
- SHORT signal approval when capacity available
- SHORT at max_positions rejected
- BUY-to-close recognition (closes short, returns approved)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def portfolio():
    """Return a mock Portfolio with adequate capital and no drawdown."""
    p = MagicMock()
    p.capital = 100_000.0
    p.get_drawdown.return_value = 0.0
    p.positions = {}
    return p


@pytest.fixture
def rm(portfolio):
    """Return a RiskManager with max 5 positions, 3% max drawdown."""
    from royaltdn.risk.manager import RiskManager
    return RiskManager(portfolio, max_positions=5, max_drawdown=0.03)


def _buy_signal(symbol="BTCUSDT", cell_name="test_cell", price=50000.0, sizing=0.01):
    return {
        "action": "BUY",
        "symbol": symbol,
        "price": price,
        "sizing": sizing,
        "cell_name": cell_name,
    }


def _short_signal(symbol="BTCUSDT", cell_name="test_cell", price=50000.0, sizing=0.01):
    return {
        "action": "SHORT",
        "symbol": symbol,
        "price": price,
        "sizing": sizing,
        "cell_name": cell_name,
    }


def _sell_signal(symbol="BTCUSDT", cell_name="test_cell", price=51000.0):
    return {
        "action": "SELL",
        "symbol": symbol,
        "price": price,
        "cell_name": cell_name,
    }


# ── Structured rejection paths ───────────────────────────────────────────


def test_rejection_null_signal(rm):
    """null_signal: signal is None → reason='null_signal'."""
    result = rm.approve(None)
    assert result is not None
    assert not result["approved"]
    assert result["reason"] == "null_signal"
    assert isinstance(result["detail"], str)


def test_rejection_max_positions(rm):
    """max_positions: pool full → reason='max_positions'."""
    # Fill all 5 slots with BUY entries
    for i in range(5):
        sig = _buy_signal(symbol="BTCUSDT", cell_name=f"cell_{i}", price=50000.0)
        result = rm.approve(sig)
        assert result["approved"], f"Entry {i} should be approved"
        # Must also update portfolio positions so SELL tracking works
        rm.portfolio.positions["BTCUSDT"] = rm.portfolio.positions.get("BTCUSDT", 0.0) + result["qty"]

    # 6th BUY should be rejected
    result = rm.approve(_buy_signal(cell_name="cell_6"))
    assert not result["approved"]
    assert result["reason"] == "max_positions"


def test_rejection_drawdown(rm):
    """drawdown: exceeded threshold → reason='drawdown'."""
    rm.portfolio.get_drawdown.return_value = 0.05  # 5% > 3% max
    result = rm.approve(_buy_signal())
    assert not result["approved"]
    assert result["reason"] == "drawdown"


def test_rejection_invalid_params(rm):
    """invalid_params: capital <= 0 or price <= 0."""
    rm.portfolio.capital = 0.0
    result = rm.approve(_buy_signal(price=50000.0))
    assert not result["approved"]
    assert result["reason"] == "invalid_params"


def test_rejection_no_position(rm):
    """no_position: SELL when no position exists."""
    result = rm.approve(_sell_signal())
    assert not result["approved"]
    assert result["reason"] == "no_position"


def test_rejection_unknown_action(rm):
    """unknown_action: e.g., HOLD is not recognized."""
    result = rm.approve({"action": "HOLD", "symbol": "BTCUSDT", "cell_name": "test"})
    assert not result["approved"]
    assert result["reason"] == "unknown_action"


# ── SHORT approval ───────────────────────────────────────────────────────


def test_short_approval(rm):
    """SHORT signal with capacity → approved with qty."""
    result = rm.approve(_short_signal())
    assert result["approved"]
    assert result["qty"] > 0
    assert ("BTCUSDT", "test_cell", "short") in rm._active_entries
    assert ("BTCUSDT", "test_cell", "short") in rm._entry_qty


def test_short_at_max_positions(rm):
    """SHORT at max_positions → rejected with 'max_positions'."""
    # Fill all 5 slots with BUY entries (mix of long and short)
    for i in range(5):
        sig = _buy_signal(symbol="BTCUSDT", cell_name=f"cell_{i}", price=50000.0)
        result = rm.approve(sig)
        assert result["approved"]
        rm.portfolio.positions["BTCUSDT"] = rm.portfolio.positions.get("BTCUSDT", 0.0) + result["qty"]

    # SHORT should be rejected
    result = rm.approve(_short_signal(cell_name="cell_short"))
    assert not result["approved"]
    assert result["reason"] == "max_positions"


def test_short_and_long_share_pool(rm):
    """SHORT and BUY entries share the same max_positions pool."""
    # 3 BUY entries
    for i in range(3):
        sig = _buy_signal(cell_name=f"buy_cell_{i}", price=50000.0)
        result = rm.approve(sig)
        assert result["approved"]
        rm.portfolio.positions["BTCUSDT"] = rm.portfolio.positions.get("BTCUSDT", 0.0) + result["qty"]

    # 2 SHORT entries
    for i in range(2):
        sig = _short_signal(cell_name=f"short_cell_{i}", price=50000.0)
        result = rm.approve(sig)
        assert result["approved"]

    # Next entry (any direction) should fail
    result = rm.approve(_buy_signal(cell_name="extra"))
    assert not result["approved"]
    assert result["reason"] == "max_positions"


# ── BUY-to-close recognition ─────────────────────────────────────────────


def test_buy_to_close_recognized(rm):
    """BUY signal with matching short entry → approved (close-short)."""
    # Enter short
    short_result = rm.approve(_short_signal(cell_name="test_cell"))
    assert short_result["approved"]
    short_qty = short_result["qty"]

    # BUY should match and close the short
    buy_result = rm.approve(_buy_signal(cell_name="test_cell"))
    assert buy_result["approved"]
    assert buy_result["qty"] == short_qty
    # Short entry should be removed
    assert ("BTCUSDT", "test_cell", "short") not in rm._active_entries


def test_buy_to_close_rejected_no_short(rm):
    """BUY without matching short entry → treated as normal entry."""
    result = rm.approve(_buy_signal(cell_name="unknown_cell"))
    assert result["approved"]  # Normal entry, not a close


def test_sell_frees_long_slot(rm):
    """SELL should free the (symbol, cell, 'long') slot."""
    # Enter long
    buy_result = rm.approve(_buy_signal(cell_name="test_cell"))
    assert buy_result["approved"]

    # SELL frees the slot
    sell_result = rm.approve(_sell_signal(cell_name="test_cell"))
    assert sell_result["approved"]
    assert ("BTCUSDT", "test_cell", "long") not in rm._active_entries


def test_buy_to_close_short_with_direction_key(rm):
    """BUY-to-close should match on (symbol, cell_name, 'short')."""
    # Enter SHORT via cell_1
    rm.approve(_short_signal(cell_name="cell_1"))
    # Enter LONG via cell_2 (same symbol, different cell)
    rm.approve(_buy_signal(cell_name="cell_2"))

    # BUY from cell_1 should close SHORT, not affect LONG
    result = rm.approve(_buy_signal(cell_name="cell_1"))
    assert result["approved"]
    assert ("BTCUSDT", "cell_1", "short") not in rm._active_entries
    # cell_2's LONG should still be active
    assert ("BTCUSDT", "cell_2", "long") in rm._active_entries
