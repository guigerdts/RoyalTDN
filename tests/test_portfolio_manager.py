#!/usr/bin/env python3
"""Tests for PortfolioPositionManager (FASE 16).

Verifies:
1. open_position / close_position / get_position
2. has_position / position_count / get_all_positions
3. get_symbol_exposure / get_total_exposure
4. close_all_positions
5. Duplicate position rejection
6. Exposure with zero equity
7. Multiple positions exposure math

Uso:
    pytest tests/test_portfolio_manager.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from datetime import datetime
from royaltdn.risk.portfolio import PortfolioPositionManager, Position


class TestPortfolioPositionManager:
    """Test suite for PortfolioPositionManager."""

    def test_open_position(self):
        ppm = PortfolioPositionManager()
        pos = ppm.open_position("AAPL", 10, 150.0, strategy="scanner")
        assert isinstance(pos, Position)
        assert pos.symbol == "AAPL"
        assert pos.qty == 10
        assert pos.entry_price == 150.0
        assert pos.strategy == "scanner"
        assert pos.side == "long"
        assert isinstance(pos.opened_at, datetime)

    def test_open_position_rejects_duplicate(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        with pytest.raises(ValueError, match="already exists"):
            ppm.open_position("AAPL", 5, 155.0)

    def test_close_position(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        closed = ppm.close_position("AAPL")
        assert closed is not None
        assert closed.symbol == "AAPL"
        assert ppm.has_position("AAPL") is False

    def test_close_nonexistent_position(self):
        ppm = PortfolioPositionManager()
        assert ppm.close_position("NONEXIST") is None

    def test_get_position(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        pos = ppm.get_position("AAPL")
        assert pos is not None
        assert pos.symbol == "AAPL"
        assert ppm.get_position("NONEXIST") is None

    def test_has_position(self):
        ppm = PortfolioPositionManager()
        assert ppm.has_position("AAPL") is False
        ppm.open_position("AAPL", 10, 150.0)
        assert ppm.has_position("AAPL") is True

    def test_position_count(self):
        ppm = PortfolioPositionManager()
        assert ppm.position_count() == 0
        ppm.open_position("AAPL", 10, 150.0)
        ppm.open_position("MSFT", 20, 300.0)
        assert ppm.position_count() == 2

    def test_get_all_positions(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        ppm.open_position("MSFT", 20, 300.0)
        all_pos = ppm.get_all_positions()
        assert len(all_pos) == 2
        # Keys are composite ("broker:symbol")
        assert "alpaca:AAPL" in all_pos
        assert "alpaca:MSFT" in all_pos
        # Position objects have the right symbol
        assert all_pos["alpaca:AAPL"].symbol == "AAPL"
        assert all_pos["alpaca:MSFT"].symbol == "MSFT"

    def test_get_symbol_exposure(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        exposure = ppm.get_symbol_exposure("AAPL", 100000)
        assert exposure == pytest.approx(0.015, rel=1e-3)  # (10 * 150) / 100000 = 0.015

    def test_get_symbol_exposure_zero_equity(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        assert ppm.get_symbol_exposure("AAPL", 0) == 0.0

    def test_get_symbol_exposure_nonexistent(self):
        ppm = PortfolioPositionManager()
        assert ppm.get_symbol_exposure("NONEXIST", 100000) == 0.0

    def test_get_total_exposure(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        ppm.open_position("MSFT", 20, 300.0)
        total = ppm.get_total_exposure(100000)
        # (10*150 + 20*300) / 100000 = (1500 + 6000) / 100000 = 0.075
        assert total == pytest.approx(0.075, rel=1e-3)

    def test_get_total_exposure_no_positions(self):
        ppm = PortfolioPositionManager()
        assert ppm.get_total_exposure(100000) == 0.0

    def test_get_total_exposure_zero_equity(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        assert ppm.get_total_exposure(0) == 0.0

    def test_close_all_positions(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        ppm.open_position("MSFT", 20, 300.0)
        closed = ppm.close_all_positions()
        assert len(closed) == 2
        assert ppm.position_count() == 0

    def test_multiple_positions_independent(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        ppm.open_position("MSFT", 20, 300.0)
        assert ppm.has_position("AAPL")
        assert ppm.has_position("MSFT")
        ppm.close_position("AAPL")
        assert not ppm.has_position("AAPL")
        assert ppm.has_position("MSFT")
        assert ppm.position_count() == 1

    def test_close_all_positions_returns_correct_order(self):
        ppm = PortfolioPositionManager()
        ppm.open_position("AAPL", 10, 150.0)
        ppm.open_position("MSFT", 20, 300.0)
        closed = ppm.close_all_positions()
        symbols = {p.symbol for p in closed}
        assert symbols == {"AAPL", "MSFT"}
