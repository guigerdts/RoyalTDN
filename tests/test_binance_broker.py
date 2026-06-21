#! /usr/bin/env python3
"""Unit tests for BinanceBroker (FASE 17 — PR 2).

Verifies HMAC-SHA-256 signing, symbol normalisation, and all 7 abstract
methods from BaseBroker.  Uses ``unittest.mock.patch`` on ``requests.get``
and ``requests.post`` so no network is required.

Uso:
    pytest tests/test_binance_broker.py -v
"""

import hashlib
import hmac
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import pandas as pd

from royaltdn.brokers.base import BaseBroker, OrderResult
from royaltdn.brokers.binance import BinanceBroker


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_json_response(payload: dict, status: int = 200):
    """Return a MagicMock that behaves like ``requests.Response``."""
    resp = MagicMock()
    resp.json.return_value = payload
    resp.status_code = status
    resp.raise_for_status.return_value = None
    return resp


def make_http_error_response(status: int = 400):
    """Return a MagicMock that raises ``HTTPError`` when checked."""
    resp = MagicMock()
    resp.raise_for_status.side_effect = __import__("requests").HTTPError(
        f"HTTP {status}"
    )
    resp.status_code = status
    return resp


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def broker():
    """Create a BinanceBroker with dummy credentials (no network)."""
    return BinanceBroker(api_key="test_key", secret_key="test_secret", testnet=True)


# ── 1. normalize_symbol ──────────────────────────────────────────────────────


class TestNormalizeSymbol:
    def test_with_slash_usd(self, broker):
        """'BTC/USD' → 'BTCUSDT'"""
        assert broker.normalize_symbol("BTC/USD") == "BTCUSDT"

    def test_with_slash_usdt(self, broker):
        """'BTC/USDT' → 'BTCUSDT'"""
        assert broker.normalize_symbol("BTC/USDT") == "BTCUSDT"

    def test_without_slash(self, broker):
        """'BTCUSDT' → 'BTCUSDT' (already native)"""
        assert broker.normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_eth_usd(self, broker):
        """'ETH/USD' → 'ETHUSDT'"""
        assert broker.normalize_symbol("ETH/USD") == "ETHUSDT"


# ── 2. get_account_balance ───────────────────────────────────────────────────


class TestGetAccountBalance:
    @patch("royaltdn.brokers.binance.requests.get")
    def test_returns_usdt_free(self, mock_get, broker):
        mock_get.return_value = make_json_response({
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.0"},
                {"asset": "USDT", "free": "1000.00", "locked": "50.00"},
            ],
        })

        balance = broker.get_account_balance()

        assert balance == 1000.00
        # Verify the request was sent to the right path
        call_url = mock_get.call_args[0][0]
        assert "/api/v3/account" in call_url

    @patch("royaltdn.brokers.binance.requests.get")
    def test_returns_zero_when_no_usdt(self, mock_get, broker):
        mock_get.return_value = make_json_response({
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.0"},
            ],
        })

        balance = broker.get_account_balance()

        assert balance == 0.0


# ── 3. get_bars ──────────────────────────────────────────────────────────────


class TestGetBars:
    @patch("royaltdn.brokers.binance.requests.get")
    def test_returns_dataframe(self, mock_get, broker):
        """Verify OHLCV DataFrame shape from klines response."""
        mock_get.return_value = make_json_response([
            [1700000000000, "100.0", "105.0", "99.0", "102.0", "1000.0"],
            [1700003600000, "102.0", "106.0", "101.0", "104.0", "1200.0"],
        ])

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)
        df = broker.get_bars("BTCUSDT", "1h", start, end)

        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 2
        assert df.index.name == "timestamp"

    @patch("royaltdn.brokers.binance.requests.get")
    def test_empty_response(self, mock_get, broker):
        """Empty klines list returns empty DataFrame."""
        mock_get.return_value = make_json_response([])

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)
        df = broker.get_bars("BTCUSDT", "1h", start, end)

        assert isinstance(df, pd.DataFrame)
        assert df.empty


# ── 4. submit_order ──────────────────────────────────────────────────────────


class TestSubmitOrder:
    @patch("royaltdn.brokers.binance.requests.post")
    def test_returns_order_result_on_success(self, mock_post, broker):
        mock_post.return_value = make_json_response({
            "orderId": 12345,
            "status": "FILLED",
            "fills": [{"price": "50000.00", "qty": "0.001"}],
        })

        result = broker.submit_order("BTCUSDT", "buy", 0.001)

        assert isinstance(result, OrderResult)
        assert result.order_id == "12345"
        assert result.symbol == "BTCUSDT"
        assert result.side == "buy"
        assert result.qty == 0.001
        assert result.price == 50000.0
        assert result.status == "FILLED"
        assert result.broker == "binance"

    @patch("royaltdn.brokers.binance.requests.post")
    def test_returns_none_on_http_error(self, mock_post, broker):
        mock_post.return_value = make_http_error_response(400)

        result = broker.submit_order("BTCUSDT", "buy", 0.001)

        assert result is None


# ── 5. get_open_positions ────────────────────────────────────────────────────


class TestGetOpenPositions:
    @patch("royaltdn.brokers.binance.requests.get")
    def test_returns_non_zero_balances(self, mock_get, broker):
        mock_get.return_value = make_json_response({
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.1"},
                {"asset": "USDT", "free": "1000", "locked": "0.0"},
                {"asset": "ETH", "free": "0.0", "locked": "0.0"},
            ],
        })

        positions = broker.get_open_positions()

        assert len(positions) == 2  # BTC and USDT
        btc_pos = [p for p in positions if "BTC" in p["symbol"]][0]
        assert btc_pos["qty"] == 0.6
        assert btc_pos["free"] == 0.5
        assert btc_pos["locked"] == 0.1
        assert btc_pos["broker"] == "binance"

    @patch("royaltdn.brokers.binance.requests.get")
    def test_empty_when_all_zero(self, mock_get, broker):
        mock_get.return_value = make_json_response({
            "balances": [
                {"asset": "BTC", "free": "0.0", "locked": "0.0"},
                {"asset": "ETH", "free": "0.0", "locked": "0.0"},
            ],
        })

        positions = broker.get_open_positions()

        assert positions == []


# ── 6. close_position ────────────────────────────────────────────────────────


class TestClosePosition:
    @patch("royaltdn.brokers.binance.requests.get")
    @patch("royaltdn.brokers.binance.requests.post")
    def test_sells_full_position(self, mock_post, mock_get, broker):
        """Should submit a sell order for the full balance."""
        mock_get.return_value = make_json_response({
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.0"},
            ],
        })
        mock_post.return_value = make_json_response({
            "orderId": 999,
            "status": "FILLED",
            "fills": [{"price": "50000.00", "qty": "0.5"}],
        })

        result = broker.close_position("BTCUSDT")

        assert result is True
        # Verify the POST was made with the correct qty
        call_params = mock_post.call_args[1].get("params", {})
        assert call_params.get("quantity") == 0.5
        assert call_params.get("side") == "SELL"


# ── 7. is_market_open ────────────────────────────────────────────────────────


class TestIsMarketOpen:
    def test_always_true(self, broker):
        assert broker.is_market_open("BTC/USD") is True
        assert broker.is_market_open("ETH/USDT") is True
        assert broker.is_market_open("ANYTHING") is True


# ── 8. HMAC signing ──────────────────────────────────────────────────────────


class TestHmacSigning:
    def test_signature_in_params(self, broker):
        """Verify _signed_request includes both timestamp and signature."""
        with patch("royaltdn.brokers.binance.requests.get") as mock_get:
            mock_get.return_value = make_json_response({"key": "value"})

            broker._signed_request("GET", "/api/v3/account", {"foo": "bar"})

            call_kwargs = mock_get.call_args[1]
            params = call_kwargs["params"]
            assert "timestamp" in params
            assert "signature" in params
            assert params["foo"] == "bar"

    def test_signature_algorithm(self, broker):
        """Verify HMAC-SHA-256 produces the right hex digest for known input."""
        # Manually compute the expected signature
        params = {"symbol": "BTCUSDT", "timestamp": 1234567890000}
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        expected = hmac.new(
            b"test_secret",
            qs.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Compare with the broker's own signing method
        actual = broker._sign(params)
        assert actual == expected

    def test_params_are_sorted(self, broker):
        """_sign sorts params alphabetically before hashing."""
        sig_a = broker._sign({"b": 2, "a": 1, "c": 3})
        sig_b = broker._sign({"a": 1, "b": 2, "c": 3})
        assert sig_a == sig_b  # order must not matter


# ── 9. testnet vs production URL ─────────────────────────────────────────────


class TestBedUrl:
    def test_testnet_url(self):
        """BINANCE_TESTNET=true → sandbox URL."""
        b = BinanceBroker(api_key="k", secret_key="s", testnet=True)
        assert b._base_url == BinanceBroker.BASE_URL_SANDBOX
        assert "testnet" in b._base_url

    def test_prod_url(self):
        """BINANCE_TESTNET=false → production URL."""
        b = BinanceBroker(api_key="k", secret_key="s", testnet=False)
        assert b._base_url == BinanceBroker.BASE_URL_PROD
        assert "api.binance.com" in b._base_url


# ── 10. Abstract base class ensures interface ────────────────────────────────


class TestBaseBrokerInterface:
    def test_binance_is_concrete_broker(self):
        """BinanceBroker must implement all abstract methods from BaseBroker."""
        import inspect

        abstract_methods = []
        for _name, method in inspect.getmembers(BaseBroker):
            if getattr(method, "__isabstractmethod__", False):
                abstract_methods.append(_name)

        for method_name in abstract_methods:
            assert hasattr(BinanceBroker, method_name), (
                f"BinanceBroker missing abstract method: {method_name}"
            )
