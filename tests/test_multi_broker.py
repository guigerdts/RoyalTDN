#! /usr/bin/env python3
"""Multi-broker routing tests (FASE 17 — PR 3).

Verifies:
  - Orchestrator._get_broker_for_symbol() routes stocks vs crypto
  - PPM composite keys and multi-broker queries
  - RiskManager combined equity and multi-broker kill switch
  - get_atr() with broker param
  - Legacy loop uses stocks broker

Uso:
    pytest tests/test_multi_broker.py -v
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import pandas as pd

from royaltdn.brokers.base import BaseBroker, OrderResult
from royaltdn.brokers.alpaca import AlpacaBroker
from royaltdn.brokers.binance import BinanceBroker
from royaltdn.risk.portfolio import PortfolioPositionManager, Position
from royaltdn.risk_manager import get_atr


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_stocks_broker():
    """A MagicMock that behaves like an AlpacaBroker for stocks."""
    broker = MagicMock(spec=BaseBroker)
    broker._broker_name = "alpaca"
    broker.get_account_balance.return_value = 100000.0
    return broker


@pytest.fixture
def mock_crypto_broker():
    """A MagicMock that behaves like a BinanceBroker for crypto."""
    broker = MagicMock(spec=BaseBroker)
    broker._broker_name = "binance"
    broker.get_account_balance.return_value = 50000.0
    return broker


@pytest.fixture
def mock_brokers(mock_stocks_broker, mock_crypto_broker):
    return {"stocks": mock_stocks_broker, "crypto": mock_crypto_broker}


@pytest.fixture
def ppm():
    return PortfolioPositionManager()


# ═══════════════════════════════════════════════════════════════════════
# 1. Orchestrator broker routing
# ═══════════════════════════════════════════════════════════════════════


class TestGetBrokerForSymbol:
    """Tests 3.1 and 3.2: _get_broker_for_symbol routing."""

    def _make_orchestrator(self, brokers):
        """Create a minimal Orchestrator-like object with _get_broker_for_symbol."""
        from royaltdn.orchestrator import Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        orch._brokers = brokers
        orch._broker = brokers.get("stocks")
        return orch

    def test_stock_routes_to_alpaca(self, mock_brokers):
        """SPY → AlpacaBroker (stocks broker)."""
        orch = self._make_orchestrator(mock_brokers)
        broker = orch._get_broker_for_symbol("SPY")
        assert broker is mock_brokers["stocks"]
        assert broker._broker_name == "alpaca"

    def test_crypto_routes_to_binance(self, mock_brokers):
        """BTC/USDT → BinanceBroker (crypto broker)."""
        orch = self._make_orchestrator(mock_brokers)
        broker = orch._get_broker_for_symbol("BTC/USDT")
        assert broker is mock_brokers["crypto"]
        assert broker._broker_name == "binance"

    def test_eth_routes_to_binance(self, mock_brokers):
        """ETH/USD → BinanceBroker (crypto broker)."""
        orch = self._make_orchestrator(mock_brokers)
        broker = orch._get_broker_for_symbol("ETH/USD")
        assert broker is mock_brokers["crypto"]
        assert broker._broker_name == "binance"

    def test_fallback_to_stocks_when_no_crypto(self, mock_stocks_broker):
        """When no crypto broker, all symbols route to stocks broker."""
        brokers = {"stocks": mock_stocks_broker}
        orch = self._make_orchestrator(brokers)
        broker = orch._get_broker_for_symbol("BTC/USD")
        assert broker is mock_stocks_broker


# ═══════════════════════════════════════════════════════════════════════
# 2. PPM composite key
# ═══════════════════════════════════════════════════════════════════════


class TestPPMCompositeKey:
    """Tests 3.4 and 3.5: Position.broker field and composite keys."""

    def test_position_dataclass_has_broker_field(self):
        """Position dataclass must include broker field defaulting to 'alpaca'."""
        pos = Position(symbol="AAPL", side="long", qty=10, entry_price=150.0,
                       strategy="scanner", opened_at=datetime.utcnow())
        assert pos.broker == "alpaca"

        pos_binance = Position(symbol="BTC/USD", side="long", qty=0.5,
                                entry_price=50000.0, strategy="scanner",
                                opened_at=datetime.utcnow(), broker="binance")
        assert pos_binance.broker == "binance"

    def test_ppm_composite_key(self, ppm):
        """Open AAPL via alpaca and BTC/USD via binance, verify both stored."""
        ppm.open_position("AAPL", qty=10, entry_price=150.0,
                          strategy="scanner", broker="alpaca")
        ppm.open_position("BTC/USD", qty=0.5, entry_price=50000.0,
                          strategy="scanner", broker="binance")

        assert ppm.position_count() == 2

        # Each position accessible via its composite key
        pos_aapl = ppm.get_position("AAPL", broker="alpaca")
        assert pos_aapl is not None
        assert pos_aapl.symbol == "AAPL"
        assert pos_aapl.broker == "alpaca"

        pos_btc = ppm.get_position("BTC/USD", broker="binance")
        assert pos_btc is not None
        assert pos_btc.symbol == "BTC/USD"
        assert pos_btc.broker == "binance"

    def test_ppm_no_collision_same_symbol_different_broker(self, ppm):
        """Same symbol on different brokers should not collide."""
        ppm.open_position("BTC/USD", qty=0.5, entry_price=50000.0,
                          strategy="scanner", broker="binance")
        ppm.open_position("BTC/USD", qty=0.1, entry_price=49000.0,
                          strategy="scanner", broker="alpaca")

        assert ppm.position_count() == 2

        # Each broker sees its own position
        binance_positions = ppm.get_positions_by_broker("binance")
        assert "BTC/USD" in binance_positions
        assert binance_positions["BTC/USD"].qty == 0.5

        alpaca_positions = ppm.get_positions_by_broker("alpaca")
        assert "BTC/USD" in alpaca_positions
        assert alpaca_positions["BTC/USD"].qty == 0.1


# ═══════════════════════════════════════════════════════════════════════
# 3. PPM get_positions_by_broker
# ═══════════════════════════════════════════════════════════════════════


class TestPPMGetPositionsByBroker:
    """Test 3.5: filter positions by broker name."""

    def test_get_positions_by_broker(self, ppm):
        ppm.open_position("AAPL", qty=10, entry_price=150.0, broker="alpaca")
        ppm.open_position("MSFT", qty=5, entry_price=300.0, broker="alpaca")
        ppm.open_position("BTC/USD", qty=0.5, entry_price=50000.0, broker="binance")

        alpaca_positions = ppm.get_positions_by_broker("alpaca")
        assert len(alpaca_positions) == 2
        assert "AAPL" in alpaca_positions
        assert "MSFT" in alpaca_positions

        binance_positions = ppm.get_positions_by_broker("binance")
        assert len(binance_positions) == 1
        assert "BTC/USD" in binance_positions

    def test_get_positions_by_broker_empty(self, ppm):
        ppm.open_position("AAPL", qty=10, entry_price=150.0, broker="alpaca")
        assert ppm.get_positions_by_broker("binance") == {}


# ═══════════════════════════════════════════════════════════════════════
# 4. PPM total exposure multi-broker
# ═══════════════════════════════════════════════════════════════════════


class TestPPMTotalExposure:
    """Test 3.5: combined exposure across brokers."""

    def test_total_exposure_multi_broker(self, ppm):
        """Total exposure aggregates positions from all brokers."""
        ppm.open_position("AAPL", qty=10, entry_price=150.0, broker="alpaca")
        ppm.open_position("BTC/USD", qty=0.5, entry_price=50000.0, broker="binance")

        # AAPL: 10 * 150 = $1,500
        # BTC: 0.5 * 50000 = $25,000
        # Total value: $26,500
        # Equity: $150,000
        total_exp = ppm.get_total_exposure(150000.0)
        expected = (1500 + 25000) / 150000.0
        assert abs(total_exp - expected) < 0.001

    def test_total_exposure_zero_equity(self, ppm):
        ppm.open_position("AAPL", qty=10, entry_price=150.0, broker="alpaca")
        assert ppm.get_total_exposure(0) == 0.0

    def test_total_exposure_no_positions(self, ppm):
        assert ppm.get_total_exposure(100000.0) == 0.0


# ═══════════════════════════════════════════════════════════════════════
# 5. RiskManager combined equity
# ═══════════════════════════════════════════════════════════════════════


class TestRiskManagerCombinedEquity:
    """Test 3.6: check_portfolio_risk consolidates equity from all brokers."""

    def test_check_portfolio_risk_combined_equity(self, ppm):
        """Portfolio risk check uses combined equity across brokers."""
        ppm.open_position("AAPL", qty=10, entry_price=150.0, broker="alpaca")

        # Passed via account_equity param (simulating combined equity)
        from royaltdn.risk_manager import check_portfolio_risk

        # With $150k total equity, AAPL exposure = 1500/150000 = 1% — OK
        passed, reason = check_portfolio_risk(ppm, account_equity=150000.0)
        assert passed, f"Expected OK, got: {reason}"

    def test_check_portfolio_risk_exposure_limit(self, ppm):
        """Exposure check uses combined equity correctly."""
        ppm.open_position("AAPL", qty=1000, entry_price=150.0, broker="alpaca")

        from royaltdn.risk_manager import check_portfolio_risk

        # With $150k total equity, AAPL exposure = 150000/150000 = 100% — exceeds 25%
        passed, reason = check_portfolio_risk(ppm, account_equity=150000.0)
        assert not passed
        assert "exposure" in reason


# ═══════════════════════════════════════════════════════════════════════
# 6. RiskManager kill switch multi-broker
# ═══════════════════════════════════════════════════════════════════════


class TestRiskManagerKillSwitch:
    """Test 3.7: multi-broker close_position via kill switch."""

    def test_kill_switch_calls_all_brokers(self, mock_brokers):
        """Simulate kill switch iterating all brokers."""
        for name, broker in mock_brokers.items():
            broker.close_position.return_value = True
            broker.get_open_positions.return_value = []

        # Simulate the kill switch logic from _execute_scanner_signals
        for name, broker in mock_brokers.items():
            try:
                open_positions = broker.get_open_positions()
                for p in open_positions:
                    sym = p.get("symbol", "")
                    if sym:
                        broker.close_position(sym)
            except Exception:
                pass

        # Both brokers were asked for open positions
        mock_brokers["stocks"].get_open_positions.assert_called()
        mock_brokers["crypto"].get_open_positions.assert_called()

    def test_kill_switch_closes_positions_on_both_brokers(self, mock_brokers):
        """If a broker has open positions, close_position is called."""
        mock_brokers["stocks"].get_open_positions.return_value = [
            {"symbol": "SPY", "qty": 10},
        ]
        mock_brokers["crypto"].get_open_positions.return_value = [
            {"symbol": "BTC/USDT", "qty": 0.5},
        ]

        for name, broker in mock_brokers.items():
            try:
                open_positions = broker.get_open_positions()
                for p in open_positions:
                    sym = p.get("symbol", "")
                    if sym:
                        broker.close_position(sym)
            except Exception:
                pass

        mock_brokers["stocks"].close_position.assert_called_once_with("SPY")
        mock_brokers["crypto"].close_position.assert_called_once_with("BTC/USDT")


# ═══════════════════════════════════════════════════════════════════════
# 7. get_atr with broker param
# ═══════════════════════════════════════════════════════════════════════


class TestGetAtrWithBroker:
    """Test 3.8: get_atr accepts broker param and uses broker.get_bars()."""

    def test_get_atr_with_broker(self):
        """get_atr with a broker uses broker.get_bars() for ATR calculation."""
        now = datetime.now()
        start = now - timedelta(days=42)
        end = now
        dates = pd.date_range(start=start, end=end, freq="D", normalize=True)[:30]

        df = pd.DataFrame({
            "timestamp": dates,
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 101.0,
            "volume": 1000000,
        })

        mock_broker = MagicMock(spec=BaseBroker)
        mock_broker.get_bars.return_value = df

        atr = get_atr(broker=mock_broker, symbol="SPY", period=14)

        assert atr > 0
        # Verify get_bars was called with the right symbol and timeframe
        mock_broker.get_bars.assert_called_once()
        call_args, call_kwargs = mock_broker.get_bars.call_args
        assert call_args[0] == "SPY"
        assert call_kwargs.get("timeframe") == "1d"

    def test_get_atr_with_broker_insufficient_data(self):
        """get_atr returns 0.0 when there is not enough data."""
        df = pd.DataFrame({
            "timestamp": [datetime.now()],
            "open": [100.0],
            "high": [102.0],
            "low": [98.0],
            "close": [101.0],
            "volume": [1000000],
        })

        mock_broker = MagicMock(spec=BaseBroker)
        mock_broker.get_bars.return_value = df

        atr = get_atr(broker=mock_broker, symbol="SPY", period=14)

        assert atr == 0.0


# ═══════════════════════════════════════════════════════════════════════
# 8. Legacy loop uses stocks broker
# ═══════════════════════════════════════════════════════════════════════


class TestLegacyLoopUsesAlpaca:
    """Test 3.8 (legacy): SPY loop uses stocks broker for broker operations."""

    def test_legacy_loop_stock_broker_routing(self):
        """The Orchestrator's _get_broker_for_symbol('SPY') returns stocks broker."""
        from royaltdn.orchestrator import Orchestrator

        stocks_broker = MagicMock(spec=BaseBroker)
        stocks_broker._broker_name = "alpaca"
        brokers = {"stocks": stocks_broker}

        orch = Orchestrator.__new__(Orchestrator)
        orch._brokers = brokers
        orch._broker = stocks_broker

        broker = orch._get_broker_for_symbol("SPY")
        assert broker is stocks_broker
        assert broker._broker_name == "alpaca"

    def test_legacy_loop_close_position_uses_stocks_broker(self):
        """close_position('SPY') delegates to the stocks broker."""
        from royaltdn.orchestrator import Orchestrator

        stocks_broker = MagicMock(spec=BaseBroker)
        stocks_broker._broker_name = "alpaca"
        stocks_broker.close_position.return_value = True
        brokers = {"stocks": stocks_broker}

        orch = Orchestrator.__new__(Orchestrator)
        orch._brokers = brokers
        orch._broker = stocks_broker

        result = orch.close_position("SPY")
        assert result is True
        stocks_broker.close_position.assert_called_once_with("SPY")


# ═══════════════════════════════════════════════════════════════════════
# 9. PPM backward compatibility
# ═══════════════════════════════════════════════════════════════════════


class TestPPMBackwardCompat:
    """Verify backward compat: calls without broker param still work."""

    def test_open_position_defaults_to_alpaca(self, ppm):
        """open_position without broker defaults to 'alpaca'."""
        ppm.open_position("AAPL", qty=10, entry_price=150.0, strategy="scanner")

        # Should be findable without broker
        assert ppm.has_position("AAPL") is True
        assert ppm.has_position("AAPL", broker="alpaca") is True
        assert ppm.has_position("AAPL", broker="binance") is False

    def test_close_position_without_broker(self, ppm):
        """close_position without broker searches all keys."""
        ppm.open_position("AAPL", qty=10, entry_price=150.0, strategy="scanner", broker="alpaca")
        closed = ppm.close_position("AAPL")
        assert closed is not None
        assert closed.symbol == "AAPL"
        assert ppm.position_count() == 0

    def test_get_position_without_broker(self, ppm):
        """get_position without broker searches all keys."""
        ppm.open_position("BTC/USD", qty=0.5, entry_price=50000.0, strategy="scanner", broker="binance")
        pos = ppm.get_position("BTC/USD")
        assert pos is not None
        assert pos.broker == "binance"


# ═══════════════════════════════════════════════════════════════════════
# 10. UI position dict includes broker (PR 4 — 4.1/4.2)
# ═══════════════════════════════════════════════════════════════════════


class TestUIPositionDictIncludesBroker:
    """_build_positions_list() returns dicts with broker key for UI display."""

    def _make_orchestrator(self):
        from royaltdn.orchestrator import Orchestrator
        from royaltdn.risk.portfolio import PortfolioPositionManager

        orch = Orchestrator.__new__(Orchestrator)
        orch._portfolio = PortfolioPositionManager()
        orch._last_known_price = 150.0
        return orch

    def test_ui_position_dict_includes_broker(self):
        """Each position dict from _build_positions_list() has a broker key."""
        orch = self._make_orchestrator()

        orch._portfolio.open_position(
            "AAPL", qty=10, entry_price=150.0,
            strategy="scanner", broker="alpaca",
        )
        orch._portfolio.open_position(
            "BTC/USD", qty=0.5, entry_price=50000.0,
            strategy="scanner", broker="binance",
        )

        result = orch._build_positions_list()
        assert len(result) == 2

        for pos_dict in result:
            assert "broker" in pos_dict, f"Missing broker key in {pos_dict}"

        aapl = [p for p in result if p["symbol"] == "AAPL"][0]
        assert aapl["broker"] == "alpaca"

        btc = [p for p in result if p["symbol"] == "BTC/USD"][0]
        assert btc["broker"] == "binance"

    def test_ui_position_dict_broker_empty_list(self):
        """_build_positions_list() returns empty list when no positions."""
        orch = self._make_orchestrator()
        assert orch._build_positions_list() == []


# ═══════════════════════════════════════════════════════════════════════
# 11. Full pipeline mock (PR 4 — 4.3)
# ═══════════════════════════════════════════════════════════════════════


class TestFullPipelineMock:
    """End-to-end broker routing: both brokers, verify per-symbol delegation."""

    def test_full_pipeline_broker_routing(self, mock_brokers):
        """Stock vs crypto symbols route through correct broker for ALL operations.

        Verifies _get_broker_for_symbol, _is_market_open, and close_position
        all delegate to the correct broker instance.
        """
        from royaltdn.orchestrator import Orchestrator
        from royaltdn.risk.portfolio import PortfolioPositionManager

        orch = Orchestrator.__new__(Orchestrator)
        orch._brokers = mock_brokers
        orch._broker = mock_brokers.get("stocks")
        orch._portfolio = PortfolioPositionManager()

        # 1. Symbol → broker routing
        assert orch._get_broker_for_symbol("SPY") is mock_brokers["stocks"]
        assert orch._get_broker_for_symbol("AAPL") is mock_brokers["stocks"]
        assert orch._get_broker_for_symbol("BTC/USD") is mock_brokers["crypto"]
        assert orch._get_broker_for_symbol("ETH/USD") is mock_brokers["crypto"]

        # 2. is_market_open delegates per symbol
        orch._is_market_open("MSFT")
        mock_brokers["stocks"].is_market_open.assert_called_with("MSFT")

        orch._is_market_open("BTC/USD")
        mock_brokers["crypto"].is_market_open.assert_called_with("BTC/USD")

        # 3. close_position delegates per symbol
        orch.close_position("AAPL")
        mock_brokers["stocks"].close_position.assert_called_once_with("AAPL")

        mock_brokers["crypto"].close_position.reset_mock()
        orch.close_position("ETH/USD")
        mock_brokers["crypto"].close_position.assert_called_once_with("ETH/USD")

    def test_full_pipeline_stock_only_fallback(self, mock_stocks_broker):
        """Without crypto broker, all symbols route to stocks broker."""
        from royaltdn.orchestrator import Orchestrator
        from royaltdn.risk.portfolio import PortfolioPositionManager

        brokers = {"stocks": mock_stocks_broker}
        orch = Orchestrator.__new__(Orchestrator)
        orch._brokers = brokers
        orch._broker = mock_stocks_broker
        orch._portfolio = PortfolioPositionManager()

        # Even crypto symbols route to stocks fallback
        assert orch._get_broker_for_symbol("BTC/USD") is mock_stocks_broker
        assert orch._get_broker_for_symbol("SPY") is mock_stocks_broker


# ═══════════════════════════════════════════════════════════════════════
# 12. Invalid broker config (PR 4 — 4.3)
# ═══════════════════════════════════════════════════════════════════════


class TestInvalidBrokerConfig:
    """Empty or invalid brokers dict: graceful fallback, no crashes."""

    def test_empty_brokers_dict(self):
        """Empty brokers dict returns 0 equity, empty positions, None routing.

        No crash or exception at any point.
        """
        from royaltdn.orchestrator import Orchestrator
        from royaltdn.risk.portfolio import PortfolioPositionManager

        orch = Orchestrator.__new__(Orchestrator)
        orch._brokers = {}
        orch._broker = None
        orch._portfolio = PortfolioPositionManager()
        orch._last_known_equity = 0.0
        orch._initial_equity = 0.0

        # Equity returns 0.0 (no crash)
        assert orch._get_current_equity() == 0.0

        # Positions list returns [] (no crash)
        assert orch._build_positions_list() == []

        # Broker routing returns None
        assert orch._get_broker_for_symbol("SPY") is None
        assert orch._get_broker_for_symbol("BTC/USD") is None

    def test_empty_brokers_build_positions_list(self):
        """PPM with positions but empty brokers: positions still listed."""
        from royaltdn.orchestrator import Orchestrator
        from royaltdn.risk.portfolio import PortfolioPositionManager

        orch = Orchestrator.__new__(Orchestrator)
        orch._brokers = {}
        orch._broker = None
        orch._portfolio = PortfolioPositionManager()
        orch._last_known_price = 200.0

        # Position tracked in PPM (added via _execute_signal, not broker sync)
        orch._portfolio.open_position(
            "AAPL", qty=10, entry_price=150.0,
            strategy="scanner", broker="alpaca",
        )

        result = orch._build_positions_list()
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["broker"] == "alpaca"
