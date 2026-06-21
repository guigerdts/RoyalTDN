#! /usr/bin/env python3
"""Unit tests for AlpacaBroker (FASE 17).

Verifies all 7 BaseBroker methods are correctly wired to the underlying
Alpaca SDK clients (TradingClient, StockHistoricalDataClient,
CryptoHistoricalDataClient).

Uso:
    pytest tests/test_alpaca_broker.py -v
"""

import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import pandas as pd

from royaltdn.brokers.base import BaseBroker, OrderResult
from royaltdn.brokers.alpaca import AlpacaBroker


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_trading():
    """Return a MagicMock for TradingClient."""
    return MagicMock()


@pytest.fixture
def mock_stock_data():
    """Return a MagicMock for StockHistoricalDataClient."""
    return MagicMock()


@pytest.fixture
def mock_crypto_data():
    """Return a MagicMock for CryptoHistoricalDataClient."""
    return MagicMock()


@pytest.fixture
def broker(mock_trading, mock_stock_data, mock_crypto_data):
    """Create an AlpacaBroker with all three clients mocked.

    Patches at the original SDK module level since AlpacaBroker uses
    function-level (lazy) imports that don't exist in its own module namespace.
    """
    with patch("alpaca.trading.client.TradingClient", return_value=mock_trading), \
         patch("alpaca.data.historical.StockHistoricalDataClient", return_value=mock_stock_data), \
         patch("alpaca.data.historical.CryptoHistoricalDataClient", return_value=mock_crypto_data):
        b = AlpacaBroker(api_key="test_key", secret_key="test_secret", paper=True)
        # Swap in our mocks directly so tests can configure return values
        b._trading = mock_trading
        b._stock_data = mock_stock_data
        b._crypto_data = mock_crypto_data
        return b


# ── 1. get_account_balance ─────────────────────────────────────────────────


class TestGetAccountBalance:
    def test_returns_equity(self, broker, mock_trading):
        mock_account = MagicMock()
        mock_account.equity = "100000.50"
        mock_trading.get_account.return_value = mock_account

        balance = broker.get_account_balance()

        assert balance == 100000.50
        mock_trading.get_account.assert_called_once()


# ── 2. submit_order ────────────────────────────────────────────────────────


class TestSubmitOrder:
    def test_returns_order_result_on_success(self, broker, mock_trading):
        mock_order = MagicMock()
        mock_order.id = "ord-123"
        mock_order.filled_avg_price = "150.25"
        mock_order.status = "accepted"
        mock_trading.submit_order.return_value = mock_order

        result = broker.submit_order("AAPL", "buy", 10)

        assert isinstance(result, OrderResult)
        assert result.order_id == "ord-123"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.qty == 10
        assert result.price == 150.25
        assert result.status == "accepted"
        assert result.broker == "alpaca"

    def test_returns_none_on_failure(self, broker, mock_trading):
        mock_trading.submit_order.side_effect = Exception("API error")

        result = broker.submit_order("AAPL", "buy", 10)

        assert result is None

    def test_sell_side_conversion(self, broker, mock_trading):
        from alpaca.trading.enums import OrderSide
        mock_order = MagicMock()
        mock_order.id = "ord-456"
        mock_order.filled_avg_price = None
        mock_order.status = "new"
        mock_trading.submit_order.return_value = mock_order

        broker.submit_order("SPY", "sell", 5)

        call_kwargs = mock_trading.submit_order.call_args
        market_order = call_kwargs[0][0]
        assert market_order.side == OrderSide.SELL


# ── 3. get_bars — stock vs crypto routing ──────────────────────────────────


class TestGetBars:
    def test_stock_symbol_uses_stock_client(self, broker, mock_stock_data, mock_crypto_data):
        mock_df = pd.DataFrame({"close": [100.0, 101.0]})
        mock_response = MagicMock()
        mock_response.df = mock_df
        mock_stock_data.get_stock_bars.return_value = mock_response

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 10)
        df = broker.get_bars("SPY", "1d", start, end)

        assert isinstance(df, pd.DataFrame)
        mock_stock_data.get_stock_bars.assert_called_once()
        # Stock symbol should NOT call crypto client
        mock_crypto_data.get_crypto_bars.assert_not_called()

    def test_crypto_symbol_uses_crypto_client(self, broker, mock_crypto_data):
        mock_df = pd.DataFrame({"close": [50000.0, 51000.0]})
        mock_response = MagicMock()
        mock_response.df = mock_df
        mock_crypto_data.get_crypto_bars.return_value = mock_response

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 10)
        df = broker.get_bars("BTC/USD", "1d", start, end)

        assert isinstance(df, pd.DataFrame)
        mock_crypto_data.get_crypto_bars.assert_called_once()


# ── 4. get_open_positions ──────────────────────────────────────────────────


class TestGetOpenPositions:
    def test_returns_position_dicts(self, broker, mock_trading):
        pos = MagicMock()
        pos.symbol = "AAPL"
        pos.qty = "10"
        pos.avg_entry_price = "150.00"
        pos.current_price = "155.00"
        pos.unrealized_pl = "50.00"
        mock_trading.get_all_positions.return_value = [pos]

        positions = broker.get_open_positions()

        assert len(positions) == 1
        assert positions[0]["symbol"] == "AAPL"
        assert positions[0]["qty"] == 10.0
        assert positions[0]["entry"] == 150.0
        assert positions[0]["current"] == 155.0
        assert positions[0]["pnl"] == 50.0
        assert positions[0]["broker"] == "alpaca"


# ── 5. close_position ──────────────────────────────────────────────────────


class TestClosePosition:
    def test_returns_true_on_success(self, broker, mock_trading):
        mock_trading.close_position.return_value = None  # no return value

        result = broker.close_position("AAPL")

        assert result is True
        mock_trading.close_position.assert_called_once_with("AAPL")

    def test_returns_false_on_error(self, broker, mock_trading):
        mock_trading.close_position.side_effect = Exception("Not found")

        result = broker.close_position("AAPL")

        assert result is False


# ── 6. is_market_open ──────────────────────────────────────────────────────


class TestIsMarketOpen:
    def test_crypto_always_open(self, broker, mock_trading):
        result = broker.is_market_open("BTC/USD")

        assert result is True
        mock_trading.get_clock.assert_not_called()

    def test_stock_delegates_to_clock(self, broker, mock_trading):
        mock_clock = MagicMock()
        mock_clock.is_open = True
        mock_trading.get_clock.return_value = mock_clock

        result = broker.is_market_open("SPY")

        assert result is True
        mock_trading.get_clock.assert_called_once()

    def test_stock_clock_closed(self, broker, mock_trading):
        mock_clock = MagicMock()
        mock_clock.is_open = False
        mock_trading.get_clock.return_value = mock_clock

        result = broker.is_market_open("AAPL")

        assert result is False


# ── 7. normalize_symbol ────────────────────────────────────────────────────


class TestNormalizeSymbol:
    def test_returns_symbol_unchanged(self, broker):
        assert broker.normalize_symbol("SPY") == "SPY"
        assert broker.normalize_symbol("BTC/USD") == "BTC/USD"
        assert broker.normalize_symbol("AAPL") == "AAPL"


# ── 8. Abstract base class ensures interface ───────────────────────────────


class TestBaseBrokerInterface:
    def test_alpaca_is_concrete_broker(self):
        """AlpacaBroker must implement all abstract methods."""
        import inspect
        from royaltdn.brokers.alpaca import AlpacaBroker

        # Verify every abstract method in BaseBroker is implemented
        abstract_methods = []
        for name, method in inspect.getmembers(BaseBroker):
            if getattr(method, "__isabstractmethod__", False):
                abstract_methods.append(name)

        for method_name in abstract_methods:
            assert hasattr(AlpacaBroker, method_name), (
                f"AlpacaBroker missing abstract method: {method_name}"
            )
