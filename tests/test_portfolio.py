"""Unit tests for Portfolio: drawdown, update_price, short PnL, and short liability.

Covers:
- Peak-equity drawdown tracking (peak stays at max, never decreases)
- update_price() mark-to-market updates total value
- Short PnL calculation: (entry - exit) * qty
- get_drawdown() returns ratio (0.0833 not 8.33)
- Short liability in get_total_value()
"""

from __future__ import annotations

import pytest


@pytest.fixture
def portfolio():
    """Return a fresh Portfolio with 100k initial capital."""
    from royaltdn.risk.portfolio import Portfolio
    return Portfolio(initial_capital=100_000.0)


# ── Peak-equity drawdown tracking ────────────────────────────────────────


def test_peak_starts_at_capital(portfolio):
    """Peak value should start equal to initial capital."""
    assert portfolio._peak_value == 100_000.0


def test_peak_tracks_upward(portfolio):
    """Peak should increase when capital grows (e.g. from short credit)."""
    # Simulate a short entry that adds capital
    short_qty = 1.0
    short_price = 50000.0
    portfolio.capital += short_qty * short_price  # credit from short sale
    portfolio.get_total_value()  # triggers _peak_value update
    expected_peak = 100_000.0 + short_qty * short_price
    assert portfolio._peak_value == expected_peak


def test_peak_does_not_decrease(portfolio):
    """Peak should stay at 120000 when value drops to 110000."""
    portfolio._peak_value = 120_000.0
    portfolio.get_total_value()  # recalculates but shouldn't lower peak
    assert portfolio._peak_value == 120_000.0


# ── update_price() mark-to-market ────────────────────────────────────────


def test_update_price_long_position(portfolio):
    """Mark-to-market update should change total value for long positions."""
    portfolio.positions["BTCUSDT"] = 1.0
    portfolio._position_costs["BTCUSDT"] = 50000.0
    portfolio.capital = 50_000.0

    # Initially total = 50000 + 1*50000 = 100000
    assert portfolio.get_total_value() == 100_000.0

    # Update price to 48000 → total = 50000 + 1*48000 = 98000
    portfolio.update_price("BTCUSDT", 48000.0)
    assert portfolio.get_total_value() == 98_000.0


def test_update_price_short_position(portfolio):
    """MTM update should reflect short liability changes."""
    portfolio.capital = 150_000.0  # 100k initial + 50k from short sale
    portfolio._short_positions["BTCUSDT"] = 1.0
    portfolio._short_position_costs["BTCUSDT"] = 50000.0

    # update_price sets mtm for short symbols too
    portfolio.update_price("BTCUSDT", 50000.0)
    # total = 150000 - (1 * 50000) = 100000
    assert portfolio.get_total_value() == 100_000.0

    # Price drops → short liability decreases → total increases
    portfolio.update_price("BTCUSDT", 45000.0)
    # total = 150000 - (1 * 45000) = 105000
    assert portfolio.get_total_value() == 105_000.0


# ── get_drawdown() ratio ─────────────────────────────────────────────────


def test_drawdown_ratio_zero(portfolio):
    """Drawdown should be 0 when total == peak."""
    assert portfolio.get_drawdown() == 0.0


def test_drawdown_ratio_value(portfolio):
    """Drawdown should return correct ratio (0.0833, not 8.33)."""
    portfolio._peak_value = 120_000.0
    portfolio.capital = 100_000.0
    portfolio.positions["BTCUSDT"] = 1.0
    portfolio._position_costs["BTCUSDT"] = 10_000.0
    # total = 100000 + 1*10000 = 110000
    # drawdown = (120000 - 110000) / 120000 = 10000/120000 = 0.08333
    assert portfolio.get_drawdown() == pytest.approx(0.08333, rel=1e-3)


def test_drawdown_ratio_zero_peak(portfolio):
    """Drawdown should be 0 when peak is 0."""
    portfolio._peak_value = 0.0
    assert portfolio.get_drawdown() == 0.0


# ── Short PnL ────────────────────────────────────────────────────────────


def test_short_entry_updates_capital(portfolio):
    """SHORT entry should increase capital (credit from selling borrowed shares)."""
    initial = portfolio.capital
    portfolio.update({
        "action": "SHORT",
        "symbol": "BTCUSDT",
        "qty": 0.1,
        "price": 30000.0,
    })
    # Capital increases by qty * price = 3000
    assert portfolio.capital == initial + 3000.0
    assert portfolio._short_positions.get("BTCUSDT") == 0.1
    assert portfolio._short_position_costs.get("BTCUSDT") == 30000.0


def test_short_close_pnl(portfolio):
    """Close short with BUY: PnL = (entry - exit) * qty = (30000-25000)*0.1 = 500.0."""
    # Enter short
    portfolio.update({
        "action": "SHORT",
        "symbol": "BTCUSDT",
        "qty": 0.1,
        "price": 30000.0,
    })
    # Close short (buy-to-cover)
    pnl = portfolio.update({
        "action": "BUY",
        "symbol": "BTCUSDT",
        "qty": 0.1,
        "price": 25000.0,
    })
    assert pnl == 500.0
    # Position should be removed
    assert "BTCUSDT" not in portfolio._short_positions
    assert "BTCUSDT" not in portfolio._short_position_costs


def test_short_close_negative_pnl(portfolio):
    """Close short at higher price: PnL = (30000 - 32000) * 0.1 = -200.0 (loss)."""
    portfolio.update({
        "action": "SHORT",
        "symbol": "BTCUSDT",
        "qty": 0.1,
        "price": 30000.0,
    })
    pnl = portfolio.update({
        "action": "BUY",
        "symbol": "BTCUSDT",
        "qty": 0.1,
        "price": 32000.0,
    })
    assert pnl == -200.0


# ── Short liability in get_total_value ───────────────────────────────────


def test_total_value_with_short(portfolio):
    """get_total_value should subtract short liability from capital."""
    portfolio.capital = 130_000.0  # 100k initial + 30k short credit
    portfolio._short_positions["BTCUSDT"] = 1.0
    portfolio._short_position_costs["BTCUSDT"] = 30000.0
    portfolio._mtm_prices["BTCUSDT"] = 30000.0

    # total = 130000 - (1 * 30000) = 100000
    assert portfolio.get_total_value() == 100_000.0

    # If price drops to 25000, short liability decreases
    portfolio._mtm_prices["BTCUSDT"] = 25000.0
    assert portfolio.get_total_value() == 105_000.0


def test_total_value_with_both_long_and_short(portfolio):
    """get_total_value should correctly account for both long and short positions."""
    portfolio.capital = 130_000.0
    portfolio.positions["ETHUSDT"] = 10.0
    portfolio._position_costs["ETHUSDT"] = 2000.0
    portfolio._short_positions["BTCUSDT"] = 1.0
    portfolio._short_position_costs["BTCUSDT"] = 30000.0
    portfolio._mtm_prices["ETHUSDT"] = 2000.0
    portfolio._mtm_prices["BTCUSDT"] = 30000.0

    # total = 130000 + (10*2000) - (1*30000) = 130000 + 20000 - 30000 = 120000
    assert portfolio.get_total_value() == 120_000.0


# ── update_price tracks short symbols ────────────────────────────────────


def test_update_price_short_symbol_mtm(portfolio):
    """update_price should store MTM price for short position symbols."""
    portfolio._short_positions["BTCUSDT"] = 1.0
    portfolio.update_price("BTCUSDT", 48000.0)
    assert portfolio._mtm_prices["BTCUSDT"] == 48000.0
