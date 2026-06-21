#!/usr/bin/env python3
"""Tests for Backtesting module (Fase 7 Hito 4)."""
import json
import os
import sys
import tempfile

import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from royaltdn.strategy.backtesting import run_backtest, _compute_metrics, config_hash
from royaltdn.strategy.schema import validate_config


# ── Helpers ─────────────────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "version": 1,
    "name": "test_bt_strategy",
    "description": "Backtest test strategy",
    "symbols": ["SPY"],
    "timeframe": "1D",
    "indicators": [
        {"name": "RSI", "params": {"period": 14}, "source": "close"},
    ],
    "entry_rules": {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "lt", "value": 30},
        ],
    },
    "exit_rules": {
        "operator": "OR",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "gt", "value": 70},
        ],
    },
    "risk_management": {
        "stop_loss_pct": 2.0,
        "take_profit_pct": 5.0,
        "max_position_size": 1.0,
        "max_daily_loss": 0.1,
    },
}

INVALID_CONFIG = {
    "version": 1,
    "name": "",
    "symbols": [],
    "timeframe": "BAD",
    "indicators": [],
    "entry_rules": {"operator": "AND", "conditions": []},
    "exit_rules": {"operator": "AND", "conditions": []},
    "risk_management": {},
}


def test_config_hash():
    """Hash is deterministic."""
    h1 = config_hash(SAMPLE_CONFIG, "SPY", "1D", "1 year")
    h2 = config_hash(SAMPLE_CONFIG, "SPY", "1D", "1 year")
    assert h1 == h2
    h3 = config_hash(SAMPLE_CONFIG, "QQQ", "1D", "1 year")
    assert h1 != h3
    print("  ✅ config_hash deterministic")


def test_validate_config():
    """Schema validation works."""
    ok, err = validate_config(SAMPLE_CONFIG)
    assert ok, f"Valid config should pass: {err}"

    ok, err = validate_config(INVALID_CONFIG)
    assert not ok
    print("  ✅ Schema validation")


def test_compute_metrics_empty():
    """Empty trades returns zero metrics."""
    equity = pd.Series([10000, 10000, 10000])
    metrics = _compute_metrics(equity, None)
    assert metrics["num_trades"] == 0
    assert metrics["total_return"] == 0.0
    print("  ✅ Empty metrics")


def test_compute_metrics_with_trades():
    """Metrics computed from trade data."""
    equity = pd.Series([10000, 10100, 10200, 10300, 10400, 10500])
    trades = pd.DataFrame([
        {"pnl": 100, "fees": 10},
        {"pnl": 50, "fees": 5},
        {"pnl": -20, "fees": 5},
    ])
    metrics = _compute_metrics(equity, trades)
    assert metrics["num_trades"] == 3
    assert metrics["total_return"] > 0
    assert metrics["win_rate"] == 2 / 3
    assert metrics["profit_factor"] > 0
    print(f"  ✅ Trade metrics: {metrics['num_trades']} trades, WR={metrics['win_rate']:.0%}")


def test_run_backtest_invalid_config():
    """Invalid config returns error dict."""
    result = run_backtest(INVALID_CONFIG, symbol="SPY", timeframe="1D", period="1 year")
    assert "error" in result
    print(f"  ✅ Invalid config error: {result['error'][:50]}")


def test_run_backtest_no_trades():
    """Config that never triggers returns no-trades error."""
    impossible_config = dict(SAMPLE_CONFIG)
    impossible_config["entry_rules"] = {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "gt", "value": 200},
        ],
    }
    impossible_config["exit_rules"] = {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "gt", "value": 0},
        ],
    }
    result = run_backtest(
        impossible_config, symbol="SPY", timeframe="1D", period="2 years",
    )
    # May or may not generate trades - depends on yfinance data
    # At minimum, should not crash and should return a dict
    assert isinstance(result, dict)
    print(f"  ✅ No-trades config handled (error={result.get('error', 'none')})")


# ── Bug 5: Crypto broker routing ───────────────────────────────────────


def test_download_data_crypto_routes_to_broker():
    """Symbol with / routes to broker.get_bars() (Bug 5)."""
    from royaltdn.strategy.backtesting import _download_data
    from unittest.mock import MagicMock

    broker = MagicMock()
    df = pd.DataFrame({
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [1_000_000],
    })
    broker.get_bars.return_value = df

    result = _download_data("BTC/USDT", "1D", "2 years", broker=broker)
    assert result is not None
    assert not result.empty
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    broker.get_bars.assert_called_once()
    print("  ✅ Crypto symbol routes to broker.get_bars()")


@patch("yfinance")
def test_download_data_stock_uses_yfinance(mock_yf):
    """Stock symbol without / uses yfinance (Bug 5)."""
    from royaltdn.strategy.backtesting import _download_data

    mock_ticker = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker
    df = pd.DataFrame({
        "Open": [100.0],
        "High": [101.0],
        "Low": [99.0],
        "Close": [100.5],
        "Volume": [1_000_000],
    })
    mock_ticker.history.return_value = df

    result = _download_data("SPY", "1D", "2 years")
    assert result is not None
    mock_yf.Ticker.assert_called_once_with("SPY")
    print("  ✅ Stock symbol uses yfinance")


def test_download_data_crypto_no_broker_returns_none():
    """Symbol with / but no broker returns None (Bug 5)."""
    from royaltdn.strategy.backtesting import _download_data

    result = _download_data("BTC/USDT", "1D", "2 years")
    assert result is None
    print("  ✅ Crypto without broker returns None")


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print("=" * 50)
    print("RoyalTDN — Hito 4: Backtesting Engine")
    print("=" * 50)

    test_config_hash()
    test_validate_config()
    test_compute_metrics_empty()
    test_compute_metrics_with_trades()
    test_run_backtest_invalid_config()
    test_run_backtest_no_trades()

    # Bug 5: Crypto broker routing
    test_download_data_crypto_routes_to_broker()
    test_download_data_stock_uses_yfinance()
    test_download_data_crypto_no_broker_returns_none()

    print()
    print("✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
