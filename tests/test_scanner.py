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

DEFAULT_ETFS = [
    "XLF", "XLE", "XLK", "XLV", "XLI",
    "XLP", "XLY", "XLB", "XLU", "XRT",
    "SPY", "QQQ", "IWM", "DIA", "GLD", "TLT",
]


def test_asset_universe_etf_list():
    """get_etf_symbols() devuelve la lista por defecto."""
    u = AssetUniverse("key", "secret")
    etfs = u.get_etf_symbols()
    assert etfs == DEFAULT_ETFS
    assert len(etfs) == 16
    print(f"  ✅ get_etf_symbols(): {len(etfs)} ETFs")


def test_asset_universe_custom_etf_list():
    """get_etf_symbols() con lista personalizada."""
    u = AssetUniverse("key", "secret")
    custom = ["SPY", "QQQ"]
    result = u.get_etf_symbols(etf_list=custom)
    assert result == custom
    print("  ✅ get_etf_symbols() lista personalizada")


def test_asset_universe_sp500_empty_on_error():
    """get_sp500_symbols() devuelve [] si la API falla."""
    u = AssetUniverse("key", "secret")
    # Sin conexión a API, debe devolver vacío sin crash
    symbols = u.get_sp500_symbols()
    assert symbols == []
    print("  ✅ get_sp500_symbols() → [] en error de API")


def test_asset_universe_get_all():
    """get_all_symbols() combina ETFs + SP500."""
    u = AssetUniverse("key", "secret")
    # Sin API de SP500, sólo ETFs
    all_syms = u.get_all_symbols()
    assert len(all_syms) >= 16  # al menos los ETFs
    for etf in DEFAULT_ETFS:
        assert etf in all_syms
    print(f"  ✅ get_all_symbols(): {len(all_syms)} símbolos")


def test_asset_universe_cache():
    """Los resultados deben cachearse."""
    u = AssetUniverse("key", "secret")
    r1 = u.get_etf_symbols()
    r2 = u.get_etf_symbols()
    assert r1 is r2  # misma referencia (cache)
    print("  ✅ Cache funciona")


# ── Tests LiquidityFilter ───────────────────────────────────────────────

def test_liquidity_filter_construct():
    """Constructor almacena parámetros."""
    f = LiquidityFilter(min_volume=100_000, min_price=10.0, max_spread_pct=1.0)
    assert f.min_volume == 100_000
    assert f.min_price == 10.0
    assert f.max_spread_pct == 1.0
    print("  ✅ LiquidityFilter construcción")


def test_liquidity_filter_all_pass():
    """Tres símbolos con buena liquidez pasan el filtro."""
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


def test_liquidity_filter_volume_reject():
    """Volumen por debajo del mínimo → rechazado."""
    f = LiquidityFilter(min_volume=500_000, min_price=5.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = [
        MockBar(close=150.0, volume=1_000),
        MockBar(close=200.0, volume=2_000_000),
    ]
    result = f.filter(["SPY", "QQQ"], client)
    assert result == ["QQQ"]  # SPY rechazado por bajo volumen
    print("  ✅ LiquidityFilter: rechaza bajo volumen")


def test_liquidity_filter_price_reject():
    """Precio por debajo del mínimo → rechazado."""
    f = LiquidityFilter(min_volume=100_000, min_price=10.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = [
        MockBar(close=2.0, volume=1_000_000),
        MockBar(close=150.0, volume=1_000_000),
    ]
    result = f.filter(["PENNY", "SPY"], client)
    assert result == ["SPY"]  # PENNY rechazado por bajo precio
    print("  ✅ LiquidityFilter: rechaza bajo precio")


def test_liquidity_filter_api_error():
    """Error de API para un símbolo → descartado silenciosamente."""
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

def test_scanner_scan_with_mocks():
    """Scanner.scan() con universe, filter y estrategias mock."""
    # Universe mock — devuelve símbolos directamente
    universe = MagicMock()
    universe.get_all_symbols.return_value = ["SPY", "QQQ"]

    # Filter mock — todos pasan
    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = ["SPY", "QQQ"]

    # Data client mock — devuelve barras
    data_client = MagicMock()

    # Mock de get_stock_bars que devuelve datos
    base_date = pd.Timestamp("2024-01-01")

    def mock_get_stock_bars(request):
        result = MagicMock()
        symbol = request.symbol_or_symbols
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
        result.data = {symbol: bars_list}
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

    assert len(results) > 0, "Scanner debería generar señales"
    print(f"  ✅ Scanner.scan(): {len(results)} señales generadas")

    # Verificar estructura de cada señal
    for r in results:
        assert "symbol" in r
        assert "strategy" in r
        assert "action" in r
        assert "price" in r

    print("  ✅ Scanner: estructura de señal correcta")


def test_scanner_top_signals():
    """get_top_signals() devuelve las top N."""
    universe = MagicMock()
    universe.get_all_symbols.return_value = ["SPY", "QQQ", "AAPL"]

    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = ["SPY", "QQQ", "AAPL"]

    data_client = MagicMock()
    base_date = pd.Timestamp("2024-01-01")

    def mock_bars(request):
        result = MagicMock()
        symbol = request.symbol_or_symbols
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
        result.data = {symbol: bars_list}
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

def main():
    print("=" * 50)
    print("RoyalTDN — Test Scanner (Fase 5.6-5.7)")
    print("=" * 50)

    # AssetUniverse
    test_asset_universe_etf_list()
    test_asset_universe_custom_etf_list()
    test_asset_universe_sp500_empty_on_error()
    test_asset_universe_get_all()
    test_asset_universe_cache()

    # LiquidityFilter
    test_liquidity_filter_construct()
    test_liquidity_filter_all_pass()
    test_liquidity_filter_volume_reject()
    test_liquidity_filter_price_reject()
    test_liquidity_filter_api_error()

    # Scanner
    test_scanner_scan_with_mocks()
    test_scanner_top_signals()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
