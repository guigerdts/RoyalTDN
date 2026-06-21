#!/usr/bin/env python3
"""Tests for FASE 17.5 bug fixes.

Covers:
1. ``is_crypto_symbol()`` helper (Bug 2)
2. ``_get_default_crypto()`` with broker_type param (Bug 2)
3. ``LiquidityFilter.filter()`` empty broker DataFrame (Bug 2)
4. ``sys.dont_write_bytecode`` (Bug 7 — smoke check)

Uso:
    pytest tests/test_fase17_5_bugs.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, patch

from royaltdn.scanner.universe import (
    AssetUniverse,
    is_crypto_symbol,
    _CRYPTO_SYMBOLS,
)
from royaltdn.scanner.filters import LiquidityFilter


# ═══════════════════════════════════════════════════════════════════════
# 3.1 — is_crypto_symbol parametrized
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTC/USD", True),
        ("ETH/USD", True),
        ("BTCUSDT", True),
        ("ETHUSDT", True),
        ("LTCUSDT", True),
        ("SPY", False),
        ("AAPL", False),
        ("QQQ", False),
        ("", False),
    ],
)
def test_is_crypto_symbol(symbol: str, expected: bool) -> None:
    assert is_crypto_symbol(symbol) is expected


def test_crypto_symbols_frozenset_contains_all_pairs() -> None:
    """``_CRYPTO_SYMBOLS`` includes both Alpaca and Binance pairs (normalised)."""
    assert "BTCUSD" in _CRYPTO_SYMBOLS  # from DEFAULT_CRYPTO (BTC/USD -> BTCUSD)
    assert "BTCUSDT" in _CRYPTO_SYMBOLS  # from DEFAULT_CRYPTO_BINANCE
    assert "ETHUSD" in _CRYPTO_SYMBOLS
    assert "ETHUSDT" in _CRYPTO_SYMBOLS
    assert "SPY" not in _CRYPTO_SYMBOLS


# ═══════════════════════════════════════════════════════════════════════
# 3.2 — _get_default_crypto with broker_type
# ═══════════════════════════════════════════════════════════════════════

class TestGetDefaultCrypto:
    """_get_default_crypto() returns broker-specific format."""

    @pytest.fixture
    def universe_alpaca(self) -> AssetUniverse:
        return AssetUniverse("dummy_key", "dummy_secret", broker_type="alpaca")

    @pytest.fixture
    def universe_binance(self) -> AssetUniverse:
        return AssetUniverse("dummy_key", "dummy_secret", broker_type="binance")

    def test_alpaca_returns_slash_symbols(self, universe_alpaca: AssetUniverse) -> None:
        symbols = universe_alpaca._get_default_crypto()
        assert len(symbols) == 10
        assert all("/" in s for s in symbols)
        assert symbols == AssetUniverse.DEFAULT_CRYPTO

    def test_binance_returns_clean_symbols(self, universe_binance: AssetUniverse) -> None:
        symbols = universe_binance._get_default_crypto()
        assert len(symbols) == 10
        assert all("/" not in s for s in symbols)
        assert symbols == AssetUniverse.DEFAULT_CRYPTO_BINANCE

    def test_default_broker_type_is_alpaca(self) -> None:
        u = AssetUniverse("dummy_key", "dummy_secret")
        assert u._get_default_crypto() == AssetUniverse.DEFAULT_CRYPTO


# ═══════════════════════════════════════════════════════════════════════
# 3.3 — LiquidityFilter with empty broker DataFrame
# ═══════════════════════════════════════════════════════════════════════

def test_liquidity_filter_empty_broker_df_logs_warning() -> None:
    """Empty DataFrame from crypto broker logs warning and skips symbol."""
    import pandas as pd

    mock_broker = MagicMock()
    mock_broker.get_bars.return_value = pd.DataFrame()  # empty DataFrame

    lf = LiquidityFilter(
        min_volume=100_000, min_price=5.0, brokers={"crypto": mock_broker},
    )
    data_client = MagicMock()

    with patch("royaltdn.scanner.filters.logger.warning") as mock_warning:
        result = lf.filter(["BTC/USD"], data_client)

    assert result == []
    mock_warning.assert_called_once()
    args, _ = mock_warning.call_args
    assert "Sin datos para" in str(args[0])


def test_liquidity_filter_empty_broker_df_skips_symbol() -> None:
    """Empty DataFrame from broker does not crash and does not return the symbol."""
    import pandas as pd

    mock_broker = MagicMock()
    mock_broker.get_bars.return_value = pd.DataFrame()

    lf = LiquidityFilter(
        min_volume=100_000, min_price=5.0, brokers={"crypto": mock_broker},
    )
    data_client = MagicMock()
    # Provide a valid stock symbol too — to verify that crypto skip does not
    # prevent stock symbols from passing
    data_client.get_stock_bars.return_value = MagicMock(
        df=pd.DataFrame({"volume": [500_000], "close": [150.0]}),
    )
    result = lf.filter(["BTC/USD", "SPY"], data_client)

    assert "BTC/USD" not in result  # skipped
    assert "SPY" in result  # still passes


# ═══════════════════════════════════════════════════════════════════════
# Bug 7 — sys.dont_write_bytecode smoke check
# ═══════════════════════════════════════════════════════════════════════

def test_dont_write_bytecode_is_set() -> None:
    """``sys.dont_write_bytecode`` is True after importing ``royaltdn``."""
    import royaltdn  # noqa: F811 — re-import uses cached module
    assert sys.dont_write_bytecode is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
