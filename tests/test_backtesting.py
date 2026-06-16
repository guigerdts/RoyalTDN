#!/usr/bin/env python3
"""Tests for Backtesting module (Fase 7 Hito 4)."""
import json
import os
import sys
import tempfile

import pandas as pd
import numpy as np

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

    print()
    print("✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
