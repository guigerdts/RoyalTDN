#!/usr/bin/env python3
"""RoyalTDN — Test del módulo Scanner (Fase 5.6-5.7)

Verifica:
1. AssetUniverse: listas de ETFs, fallback vacío en error
2. LiquidityFilter: construcción, filtro por volumen, precio
3. Scanner: escaneo con mocks, ranking, top N

Uso:
    pytest tests/test_scanner.py -v
    python tests/test_scanner.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
from unittest.mock import MagicMock, patch

from royaltdn.scanner.universe import AssetUniverse
from royaltdn.scanner.filters import LiquidityFilter
from royaltdn.scanner.scanner import Scanner
from royaltdn.strategy.base import BaseStrategy


# ── Helpers ──────────────────────────────────────────────────────────────

class MockBar:
    """Simula una Bar de Alpaca."""
    def __init__(self, close=150.0, volume=1_000_000, timestamp=None):
        self.open = close
        self.high = close * 1.01
        self.low = close * 0.99
        self.close = close
        self.volume = volume
        self.timestamp = timestamp or pd.Timestamp("2024-01-15")
        self.bid_price = None
        self.ask_price = None


class MockStrategy(BaseStrategy):
    """Estrategia mock para pruebas."""
    def __init__(self, name="mock_strategy", signal=None):
        super().__init__()
        self._name = name
        self._signal = signal or {"action": "BUY", "price": 100.0}

    @property
    def name(self):
        return self._name

    def generate_signal(self, data):
        return self._signal

    def get_parameters(self):
        return {"name": self._name}


# ── Tests AssetUniverse ─────────────────────────────────────────────────

DEFAULT_ETFS = AssetUniverse.DEFAULT_ETFS


def test_asset_universe_etf_list() -> None:
    """get_symbols() with universe_type='etfs' returns DEFAULT_ETFS."""
    u = AssetUniverse("key", "secret", universe_type="etfs")
    symbols = u.get_symbols()
    assert symbols == DEFAULT_ETFS
    assert len(symbols) == 16
    print(f"  ✅ get_symbols(etfs): {len(symbols)} ETFs")


def test_asset_universe_cache() -> None:
    """get_symbols() caches results with TTL."""
    u = AssetUniverse("key", "secret", universe_type="etfs")
    r1 = u.get_symbols()
    r2 = u.get_symbols()
    assert r1 is r2  # misma referencia (cache hit)
    assert len(u._cache) == 1
    print("  ✅ Cache funciona")


def test_asset_universe_invalid_type() -> None:
    """Invalid universe_type falls back to 'etfs'."""
    u = AssetUniverse("key", "secret", universe_type="crypto")
    assert u.universe_type == "etfs"
    symbols = u.get_symbols()
    assert symbols == DEFAULT_ETFS
    print("  ✅ universe_type inválido → fallback etfs")


def test_asset_universe_invalidate_cache() -> None:
    """invalidate_cache() clears the cache."""
    u = AssetUniverse("key", "secret", universe_type="etfs")
    u.get_symbols()  # populate cache
    assert len(u._cache) == 1
    u.invalidate_cache()
    assert len(u._cache) == 0
    print("  ✅ invalidate_cache() funciona")


def test_asset_universe_sp500_empty_on_error() -> None:
    """get_symbols(sp500) returns [] on API error (no mocking)."""
    u = AssetUniverse("key", "secret", universe_type="sp500")
    # Sin conexión a API real, _get_sp500_via_sdk() debe retornar []
    # porque TradingClient.get_all_assets() fallará sin credenciales reales
    symbols = u.get_symbols()
    assert isinstance(symbols, list)
    print(f"  ✅ get_symbols(sp500) sin API: {len(symbols)} símbolos (esperado [])")


def test_asset_universe_all_universe() -> None:
    """get_symbols('all') returns at least ETFs (sp500 fails without API)."""
    u = AssetUniverse("key", "secret", universe_type="all")
    symbols = u.get_symbols()
    # sp500 falla sin API, por lo que retorna solo ETFs
    assert len(symbols) >= 16
    for etf in DEFAULT_ETFS:
        assert etf in symbols
    print(f"  ✅ get_symbols(all): {len(symbols)} símbolos")


# ── Tests LiquidityFilter ───────────────────────────────────────────────

def test_liquidity_filter_construct() -> None:
    """Constructor stores parameters."""
    f = LiquidityFilter(min_volume=100_000, min_price=10.0, max_spread_pct=1.0)
    assert f.min_volume == 100_000
    assert f.min_price == 10.0
    assert f.max_spread_pct == 1.0
    print("  ✅ LiquidityFilter construcción")


def test_liquidity_filter_all_pass() -> None:
    """Three symbols with good liquidity pass the filter."""
    f = LiquidityFilter(min_volume=500_000, min_price=5.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = [
        MockBar(close=150.0, volume=1_000_000),
        MockBar(close=200.0, volume=2_000_000),
        MockBar(close=50.0, volume=800_000),
    ]
    result = f.filter(["SPY", "QQQ", "IWM"], client)
    assert result == ["SPY", "QQQ", "IWM"]
    assert client.get_latest_bar.call_count == 3
    print("  ✅ LiquidityFilter: 3/3 pasaron")


def test_liquidity_filter_volume_reject() -> None:
    """Volume below minimum is rejected."""
    f = LiquidityFilter(min_volume=500_000, min_price=5.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = [
        MockBar(close=150.0, volume=1_000),
        MockBar(close=200.0, volume=2_000_000),
    ]
    result = f.filter(["SPY", "QQQ"], client)
    assert result == ["QQQ"]  # SPY rechazado por bajo volumen
    print("  ✅ LiquidityFilter: rechaza bajo volumen")


def test_liquidity_filter_price_reject() -> None:
    """Price below minimum is rejected."""
    f = LiquidityFilter(min_volume=100_000, min_price=10.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = [
        MockBar(close=2.0, volume=1_000_000),
        MockBar(close=150.0, volume=1_000_000),
    ]
    result = f.filter(["PENNY", "SPY"], client)
    assert result == ["SPY"]  # PENNY rechazado por bajo precio
    print("  ✅ LiquidityFilter: rechaza bajo precio")


def test_liquidity_filter_api_error() -> None:
    """API error for a symbol is silently discarded."""
    f = LiquidityFilter(min_volume=100_000, min_price=5.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = [
        Exception("API error"),
        MockBar(close=150.0, volume=1_000_000),
    ]
    result = f.filter(["BAD", "SPY"], client)
    assert result == ["SPY"]  # BAD descartado por error
    print("  ✅ LiquidityFilter: descarta error de API")


# ── Tests Scanner ───────────────────────────────────────────────────────

def test_scanner_scan_with_mocks() -> None:
    """Scanner.scan() with mocked universe, filter and strategies."""
    # Universe mock — returns symbols directly
    universe = MagicMock()
    universe.get_symbols.return_value = ["SPY", "QQQ"]

    # Filter mock — todos pasan
    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = ["SPY", "QQQ"]
    from royaltdn.scanner.filters import TokenBucket
    liquidity_filter.token_bucket = TokenBucket()

    # Data client mock — devuelve barras
    data_client = MagicMock()

    # Mock de get_stock_bars que maneja batches
    base_date = pd.Timestamp("2024-01-01")

    def mock_get_stock_bars(request):
        result = MagicMock()
        symbols = request.symbol_or_symbols
        if isinstance(symbols, str):
            symbols = [symbols]
        result.data = {}
        for symbol in symbols:
            bars_list = []
            for i in range(60):
                bar = MagicMock()
                bar.timestamp = base_date + pd.Timedelta(days=i)
                bar.open = 100.0 + i * 0.1
                bar.high = 101.0 + i * 0.1
                bar.low = 99.0 + i * 0.1
                bar.close = 100.0 + i * 0.1
                bar.volume = 1_000_000
                bars_list.append(bar)
            result.data[symbol] = bars_list
        return result

    data_client.get_stock_bars.side_effect = mock_get_stock_bars

    # Estrategias mock
    strategies = {
        "sma_crossover": MockStrategy("sma_crossover"),
        "factor_rotation": MockStrategy("factor_rotation", signal={
            "action": "RANK",
            "price": 100.0,
            "metadata": {"score": 1.5, "momentum": 0.05, "volatility": 0.02},
        }),
    }

    scanner = Scanner(universe, liquidity_filter, strategies, data_client)
    results = scanner.scan()

    assert len(results) > 0, "Scanner should generate signals"
    print(f"  ✅ Scanner.scan(): {len(results)} signals generated")

    # Verify signal structure
    for r in results:
        assert "symbol" in r
        assert "strategy" in r
        assert "action" in r
        assert "price" in r

    print("  ✅ Scanner: correct signal structure")


def test_scanner_top_signals() -> None:
    """get_top_signals() returns top N signals."""
    universe = MagicMock()
    universe.get_symbols.return_value = ["SPY", "QQQ", "AAPL"]

    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = ["SPY", "QQQ", "AAPL"]
    from royaltdn.scanner.filters import TokenBucket
    liquidity_filter.token_bucket = TokenBucket()

    data_client = MagicMock()
    base_date = pd.Timestamp("2024-01-01")

    def mock_bars(request):
        result = MagicMock()
        symbols = request.symbol_or_symbols
        if isinstance(symbols, str):
            symbols = [symbols]
        result.data = {}
        for symbol in symbols:
            bars_list = []
            for i in range(60):
                bar = MagicMock()
                bar.timestamp = base_date + pd.Timedelta(days=i)
                bar.open = 100.0
                bar.high = 101.0
                bar.low = 99.0
                bar.close = 100.0
                bar.volume = 1_000_000
                bars_list.append(bar)
            result.data[symbol] = bars_list
        return result

    data_client.get_stock_bars.side_effect = mock_bars

    strategies = {"mock": MockStrategy("mock")}
    scanner = Scanner(universe, liquidity_filter, strategies, data_client)

    results = scanner.scan()
    assert len(results) == 3, "3 símbolos * 1 estrategia = 3 señales"

    top = scanner.get_top_signals(n=2)
    assert len(top) == 2, "top 2 de 3"
    print(f"  ✅ Scanner.get_top_signals(2): {len(top)} señales")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 50)
    print("RoyalTDN — Test Scanner (Fase 13)")
    print("=" * 50)

    # AssetUniverse
    test_asset_universe_etf_list()
    test_asset_universe_cache()
    test_asset_universe_invalid_type()
    test_asset_universe_invalidate_cache()
    test_asset_universe_sp500_empty_on_error()
    test_asset_universe_all_universe()

    # LiquidityFilter
    test_liquidity_filter_construct()
    test_liquidity_filter_all_pass()
    test_liquidity_filter_volume_reject()
    test_liquidity_filter_price_reject()
    test_liquidity_filter_api_error()

    # Scanner
    test_scanner_scan_with_mocks()
    test_scanner_top_signals()

    print("\n✅ ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
