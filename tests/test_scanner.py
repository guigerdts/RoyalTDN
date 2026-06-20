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


def test_asset_universe_sp500_via_sdk() -> None:
    """Mock TradingClient to test sp500 loads symbols via SDK."""
    mock_assets = []
    for sym in ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]:
        asset = MagicMock()
        asset.symbol = sym
        asset.tradable = True
        asset.exchange = "NASDAQ"
        mock_assets.append(asset)

    with patch("alpaca.trading.client.TradingClient.get_all_assets", return_value=mock_assets):
        u = AssetUniverse("key", "secret", universe_type="sp500")
        symbols = u.get_symbols()

    assert "AAPL" in symbols
    assert "MSFT" in symbols
    assert "GOOGL" in symbols
    assert len(symbols) == 5
    print(f"  ✅ get_symbols(sp500) via SDK: {len(symbols)} symbols")


def test_asset_universe_cache_ttl_miss() -> None:
    """Cache expires after TTL and is regenerated."""
    import time as _time_module
    u = AssetUniverse("key", "secret", universe_type="etfs", cache_ttl=600)

    # First call populates cache
    r1 = u.get_symbols()
    assert r1 == AssetUniverse.DEFAULT_ETFS
    cache_key = "universe:etfs"
    assert cache_key in u._cache
    original_ts, original_data = u._cache[cache_key]

    # Advance time beyond TTL
    future_time = original_ts + 600 + 1
    with patch.object(_time_module, "time", return_value=future_time):
        r2 = u.get_symbols()

    # Cache should have been refreshed with a new timestamp
    new_ts, new_data = u._cache[cache_key]
    assert new_data == r2
    assert new_ts == future_time
    # The data should still be DEFAULT_ETFS
    assert r2 == AssetUniverse.DEFAULT_ETFS
    print("  ✅ Cache TTL miss: cache regenerated")


def test_asset_universe_all_with_sp500_fail() -> None:
    """universe_type='all' falls back to DEFAULT_ETFS when sp500 fails."""
    with patch.object(AssetUniverse, "_get_sp500_via_sdk", return_value=[]):
        u = AssetUniverse("key", "secret", universe_type="all")
        symbols = u.get_symbols()

    assert symbols == AssetUniverse.DEFAULT_ETFS
    assert len(symbols) == len(AssetUniverse.DEFAULT_ETFS)
    print("  ✅ get_symbols(all) with sp500 fail: returns ETFs only")


def test_asset_universe_requests_not_imported() -> None:
    """universe module does NOT import the 'requests' library."""
    # Remove universe from sys.modules to force fresh import
    import sys as _sys
    _sys.modules.pop("royaltdn.scanner.universe", None)
    _sys.modules.pop("royaltdn.scanner", None)

    # Track modules before import
    modules_before = set(_sys.modules.keys())
    import royaltdn.scanner.universe  # noqa: F811
    modules_after = set(_sys.modules.keys())

    new_modules = modules_after - modules_before
    assert "requests" not in new_modules
    print("  ✅ universe module does not import requests")


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


# ── Tests TokenBucket ───────────────────────────────────────────────────

def test_token_bucket_initial_tokens() -> None:
    """TokenBucket starts with max_tokens tokens."""
    from royaltdn.scanner.filters import TokenBucket
    bucket = TokenBucket(max_tokens=200)
    assert bucket.available_tokens == 200
    print("  ✅ TokenBucket: initial tokens = 200")


def test_token_bucket_consume() -> None:
    """Consuming tokens reduces available count."""
    from royaltdn.scanner.filters import TokenBucket
    import time as _time_module
    with patch.object(_time_module, "monotonic", return_value=1000.0):
        bucket = TokenBucket(max_tokens=200)
        bucket.consume(3)
        assert bucket.available_tokens == 197
    print("  ✅ TokenBucket: consume 3 → 197 remaining")


def test_token_bucket_refill() -> None:
    """Tokens refill over time at the configured rate."""
    from royaltdn.scanner.filters import TokenBucket
    import time as _time_module
    with patch.object(_time_module, "monotonic", return_value=1000.0):
        bucket = TokenBucket(max_tokens=200)
        # Consume all 200 tokens in one shot
        bucket.consume(200)
        assert bucket.available_tokens == 0

    # Advance time by 60 seconds (full refill at 200/60 tokens/sec)
    with patch.object(_time_module, "monotonic", return_value=1060.0):
        tokens = bucket.available_tokens
        assert tokens == 200, f"Expected 200 after 60s refill, got {tokens}"

    print("  ✅ TokenBucket: refilled to 200 after 60s")


def test_liquidity_filter_rate_limiting() -> None:
    """LiquidityFilter.filter() consumes 1 token per symbol."""
    f = LiquidityFilter(min_volume=100_000, min_price=5.0)
    import time as _time_module
    with patch.object(_time_module, "monotonic", return_value=1000.0):
        f = LiquidityFilter(min_volume=100_000, min_price=5.0)
        initial_tokens = f.token_bucket.available_tokens
        assert initial_tokens == 200

        client = MagicMock()
        client.get_latest_bar.side_effect = [
            MockBar(close=150.0, volume=1_000_000),
            MockBar(close=200.0, volume=2_000_000),
            MockBar(close=50.0, volume=800_000),
        ]
        f.filter(["SPY", "QQQ", "IWM"], client)

        consumed = initial_tokens - f.token_bucket.available_tokens
        assert consumed == 3, f"Expected 3 tokens consumed, got {consumed}"
    print("  ✅ LiquidityFilter: consumed 1 token per symbol (3 total)")


@patch("royaltdn.scanner.filters.time.sleep")
def test_liquidity_filter_retry_success_on_3rd(mock_sleep) -> None:
    """_call_with_retry retries on HTTP 429 and succeeds on 3rd attempt."""
    f = LiquidityFilter(min_volume=100_000, min_price=5.0)
    client = MagicMock()
    # Mock get_latest_bar: fail twice with 429, succeed on 3rd
    client.get_latest_bar.side_effect = [
        Exception("429 Too Many Requests"),
        Exception("429 Too Many Requests"),
        MockBar(close=150.0, volume=1_000_000),
    ]
    result = f._call_with_retry("SPY", client)
    assert result is not None
    assert result.close == 150.0
    assert client.get_latest_bar.call_count == 3
    print("  ✅ _call_with_retry: succeeded on 3rd attempt after 429")


@patch("royaltdn.scanner.filters.time.sleep")
def test_liquidity_filter_retry_max_exhausted(mock_sleep) -> None:
    """_call_with_retry returns None after exhausting all 5 retries on 429."""
    f = LiquidityFilter(min_volume=100_000, min_price=5.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = Exception("429 Too Many Requests")
    result = f._call_with_retry("SPY", client)
    assert result is None
    assert client.get_latest_bar.call_count == 5
    print("  ✅ _call_with_retry: returns None after 5 exhausted retries")


def test_liquidity_filter_auth_abort() -> None:
    """HTTP 401 in _call_with_retry aborts immediately (raises)."""
    f = LiquidityFilter(min_volume=100_000, min_price=5.0)
    client = MagicMock()
    client.get_latest_bar.side_effect = Exception("401 Unauthorized")

    import pytest as _pytest
    with _pytest.raises(Exception) as exc_info:
        f._call_with_retry("SPY", client)
    assert "401" in str(exc_info.value)
    # Should only have made 1 attempt (no retry on auth errors)
    assert client.get_latest_bar.call_count == 1
    print("  ✅ _call_with_retry: 401 aborts immediately, no retry")


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


# ── Tests Scanner Batch ─────────────────────────────────────────────────


def _make_batch_mock_response(symbols: list) -> MagicMock:
    """Helper: build a mock get_stock_bars response with valid data."""
    base_date = pd.Timestamp("2024-01-01")
    resp = MagicMock()
    resp.data = {}
    for i, sym in enumerate(symbols):
        bar = MagicMock()
        bar.timestamp = base_date + pd.Timedelta(days=i)
        bar.open = 100.0
        bar.high = 101.0
        bar.low = 99.0
        bar.close = 100.0
        bar.volume = 1_000_000
        resp.data[sym] = [bar] * 60  # 60 daily bars
    return resp


def test_scanner_batch_distribution() -> None:
    """250 symbols are split into 3 batches (100 + 100 + 50)."""
    universe = MagicMock()
    universe.get_symbols.return_value = [f"SYM{i:03d}" for i in range(250)]

    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = [f"SYM{i:03d}" for i in range(250)]
    from royaltdn.scanner.filters import TokenBucket
    liquidity_filter.token_bucket = TokenBucket()

    data_client = MagicMock()
    # Return a valid response for each batch call
    data_client.get_stock_bars.side_effect = [
        _make_batch_mock_response([f"SYM{i:03d}" for i in range(100)]),
        _make_batch_mock_response([f"SYM{i:03d}" for i in range(100, 200)]),
        _make_batch_mock_response([f"SYM{i:03d}" for i in range(200, 250)]),
    ]

    strategies = {"mock": MockStrategy("mock")}
    scanner = Scanner(universe, liquidity_filter, strategies, data_client)

    symbols = [f"SYM{i:03d}" for i in range(250)]
    result = scanner._batch_get_symbol_data(symbols)

    assert data_client.get_stock_bars.call_count == 3
    # Verify batch sizes: 100 + 100 + 50
    calls = data_client.get_stock_bars.call_args_list
    assert len(calls[0][0][0].symbol_or_symbols) == 100
    assert len(calls[1][0][0].symbol_or_symbols) == 100
    assert len(calls[2][0][0].symbol_or_symbols) == 50
    # Verify all symbols were processed
    assert len(result) == 250
    print("  ✅ Scanner batch: 250 symbols → 3 calls (100+100+50)")


def test_scanner_batch_partial() -> None:
    """<100 symbols make a single batch call."""
    universe = MagicMock()
    universe.get_symbols.return_value = [f"SYM{i:03d}" for i in range(50)]

    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = [f"SYM{i:03d}" for i in range(50)]
    from royaltdn.scanner.filters import TokenBucket
    liquidity_filter.token_bucket = TokenBucket()

    data_client = MagicMock()
    data_client.get_stock_bars.return_value = _make_batch_mock_response(
        [f"SYM{i:03d}" for i in range(50)]
    )

    strategies = {"mock": MockStrategy("mock")}
    scanner = Scanner(universe, liquidity_filter, strategies, data_client)

    symbols = [f"SYM{i:03d}" for i in range(50)]
    result = scanner._batch_get_symbol_data(symbols)

    data_client.get_stock_bars.assert_called_once()
    call_syms = data_client.get_stock_bars.call_args[0][0].symbol_or_symbols
    assert len(call_syms) == 50
    assert len(result) == 50
    print("  ✅ Scanner batch: 50 symbols → 1 call")


def test_scanner_batch_error_isolation() -> None:
    """Error in one batch doesn't prevent other batches from completing."""
    universe = MagicMock()
    all_symbols = [f"SYM{i:03d}" for i in range(250)]
    universe.get_symbols.return_value = all_symbols

    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = all_symbols
    from royaltdn.scanner.filters import TokenBucket
    liquidity_filter.token_bucket = TokenBucket()

    data_client = MagicMock()
    data_client.get_stock_bars.side_effect = [
        _make_batch_mock_response([f"SYM{i:03d}" for i in range(100)]),
        Exception("API error on batch 2"),
        _make_batch_mock_response([f"SYM{i:03d}" for i in range(200, 250)]),
    ]

    strategies = {"mock": MockStrategy("mock")}
    scanner = Scanner(universe, liquidity_filter, strategies, data_client)

    symbols = [f"SYM{i:03d}" for i in range(250)]
    result = scanner._batch_get_symbol_data(symbols)

    # Should have 150 symbols (100 from batch 0 + 50 from batch 2)
    assert len(result) == 150
    assert data_client.get_stock_bars.call_count == 3
    print("  ✅ Scanner batch: error in batch 2 → other batches still succeed")


def test_scanner_auth_failure_aborts() -> None:
    """HTTP 401 in batch download sets _auth_failed and stops further batches."""
    universe = MagicMock()
    all_symbols = [f"SYM{i:03d}" for i in range(250)]
    universe.get_symbols.return_value = all_symbols

    liquidity_filter = MagicMock()
    liquidity_filter.filter.return_value = all_symbols
    from royaltdn.scanner.filters import TokenBucket
    liquidity_filter.token_bucket = TokenBucket()

    data_client = MagicMock()
    data_client.get_stock_bars.side_effect = [
        _make_batch_mock_response([f"SYM{i:03d}" for i in range(100)]),
        Exception("401 Unauthorized"),
        _make_batch_mock_response([f"SYM{i:03d}" for i in range(200, 250)]),
    ]

    strategies = {"mock": MockStrategy("mock")}
    scanner = Scanner(universe, liquidity_filter, strategies, data_client)

    symbols = [f"SYM{i:03d}" for i in range(250)]
    result = scanner._batch_get_symbol_data(symbols)

    assert scanner._auth_failed is True
    # Only 2 calls should have been made (first batch succeeded, second auth-failed aborts)
    assert data_client.get_stock_bars.call_count == 2
    # Only first batch data should be in result
    assert len(result) == 100
    print("  ✅ Scanner batch: 401 aborts and sets _auth_failed")


# ── Tests tqdm dependency ──────────────────────────────────────────────

def test_tqdm_dependency_declared() -> None:
    """tqdm>=4.66,<5 is declared in pyproject.toml dependencies."""
    import tomllib
    with open("pyproject.toml", "rb") as f:
        config = tomllib.load(f)
    deps = config["project"]["dependencies"]
    assert any("tqdm" in dep for dep in deps), (
        f"tqdm not found in {deps}"
    )
    # Verify version constraint
    tqdm_dep = [dep for dep in deps if "tqdm" in dep][0]
    assert ">=4.66" in tqdm_dep
    assert "<5" in tqdm_dep
    print(f"  ✅ tqdm dependency declared: {tqdm_dep}")


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
    test_asset_universe_sp500_via_sdk()
    test_asset_universe_cache_ttl_miss()
    test_asset_universe_all_with_sp500_fail()
    test_asset_universe_requests_not_imported()

    # LiquidityFilter
    test_liquidity_filter_construct()
    test_liquidity_filter_all_pass()
    test_liquidity_filter_volume_reject()
    test_liquidity_filter_price_reject()
    test_liquidity_filter_api_error()

    # TokenBucket
    test_token_bucket_initial_tokens()
    test_token_bucket_consume()
    test_token_bucket_refill()
    test_liquidity_filter_rate_limiting()
    test_liquidity_filter_retry_success_on_3rd()
    test_liquidity_filter_retry_max_exhausted()
    test_liquidity_filter_auth_abort()

    # Scanner
    test_scanner_scan_with_mocks()
    test_scanner_top_signals()

    # Scanner batch
    test_scanner_batch_distribution()
    test_scanner_batch_partial()
    test_scanner_batch_error_isolation()
    test_scanner_auth_failure_aborts()

    # tqdm dependency
    test_tqdm_dependency_declared()

    print("\n✅ ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
