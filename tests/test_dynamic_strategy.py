#!/usr/bin/env python3
"""Tests for DynamicStrategy and StrategyStore (Fase 7 Hito 2)."""
import json
import os
import sys
import tempfile

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from royaltdn.strategy.dynamic import DynamicStrategy
from royaltdn.strategy.strategy_store import StrategyStore
from royaltdn.strategy.schema import validate_config


# ── Fixtures ────────────────────────────────────────────────────────────

VALID_CONFIG = {
    "version": 1,
    "name": "test_rsi_strategy",
    "description": "A test RSI strategy",
    "symbols": ["SPY"],
    "timeframe": "1D",
    "indicators": [
        {"name": "RSI", "params": {"period": 14}, "source": "close"},
    ],
    "entry_rules": {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "gt", "value": 30},
        ],
    },
    "exit_rules": {
        "operator": "OR",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "lt", "value": 70},
        ],
    },
    "risk_management": {
        "stop_loss_pct": 2.0,
        "take_profit_pct": 5.0,
        "max_position_size": 1.0,
        "max_daily_loss": 0.1,
    },
}

BUY_CONFIG = {
    "version": 1,
    "name": "buy_only",
    "description": "Always BUY when RSI > 30",
    "symbols": ["SPY"],
    "timeframe": "1D",
    "indicators": [
        {"name": "RSI", "params": {"period": 14}, "source": "close"},
        {"name": "SMA", "params": {"period": 5}, "source": "close"},
    ],
    "entry_rules": {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "gt", "value": 30},
        ],
    },
    "exit_rules": {
        "operator": "AND",
        "conditions": [
            {"indicator": "SMA", "params": {"period": 5}, "operator": "gt", "value": 0},
        ],
    },
    "risk_management": {
        "stop_loss_pct": 2.0,
        "take_profit_pct": 5.0,
        "max_position_size": 1.0,
        "max_daily_loss": 0.1,
    },
}

SELL_CONFIG = {
    "version": 1,
    "name": "sell_only",
    "description": "Always SELL when RSI < 70",
    "symbols": ["SPY"],
    "timeframe": "1D",
    "indicators": [
        {"name": "RSI", "params": {"period": 14}, "source": "close"},
        {"name": "SMA", "params": {"period": 5}, "source": "close"},
    ],
    "entry_rules": {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "lt", "value": -10},
        ],
    },
    "exit_rules": {
        "operator": "OR",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "lt", "value": 70},
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
    "name": "",  # invalid: empty name
    "symbols": [],
    "timeframe": "BAD",
    "indicators": [],
    "entry_rules": {"operator": "AND", "conditions": []},
    "exit_rules": {"operator": "AND", "conditions": []},
    "risk_management": {},
}


def _make_sample_data(n=200) -> pd.DataFrame:
    """Create synthetic OHLCV data."""
    np.random.seed(42)
    close = np.random.randn(n).cumsum() + 100
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.5,
        "high": close + np.abs(np.random.randn(n)) * 2 + 0.5,
        "low": close - np.abs(np.random.randn(n)) * 2 - 0.5,
        "close": close,
        "volume": np.abs(np.random.randn(n) * 1000 + 5000),
    })


# ── DynamicStrategy tests ───────────────────────────────────────────────


def test_load_valid_json():
    """Instantiate DynamicStrategy from valid config."""
    ds = DynamicStrategy(VALID_CONFIG)
    assert ds.name == "test_rsi_strategy"
    assert ds.symbols == ["SPY"]
    assert ds.timeframe == "1D"
    assert ds.validate() is True
    print("  ✅ DynamicStrategy from valid config")


def test_generate_signal_buy():
    """Entry rule RSI>30 fires on data where RSI is high."""
    ds = DynamicStrategy(BUY_CONFIG)
    data = _make_sample_data()
    # Last RSI is roughly > 30 for typical random walk
    signal = ds.generate_signal(data)
    assert signal is not None, "Expected a BUY signal"
    assert signal["action"] == "BUY"
    assert signal["symbol"] == "SPY"
    assert isinstance(signal["price"], float)
    assert "strategy" in signal
    assert "risk" in signal
    print(f"  ✅ BUY signal: {signal['action']} @ {signal['price']:.2f}")


def test_generate_signal_sell():
    """Exit rule RSI<70 fires on data where RSI is low."""
    ds = DynamicStrategy(SELL_CONFIG)
    data = _make_sample_data()
    signal = ds.generate_signal(data)
    assert signal is not None, "Expected a SELL signal"
    assert signal["action"] == "SELL"
    assert signal["symbol"] == "SPY"
    print(f"  ✅ SELL signal: {signal['action']} @ {signal['price']:.2f}")


def test_generate_signal_none():
    """No rules matched returns None."""
    no_match_config = dict(VALID_CONFIG)
    no_match_config["entry_rules"] = {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "gt", "value": 200},
        ],
    }
    no_match_config["exit_rules"] = {
        "operator": "AND",
        "conditions": [
            {"indicator": "RSI", "params": {"period": 14}, "operator": "lt", "value": -10},
        ],
    }
    ds = DynamicStrategy(no_match_config)
    data = _make_sample_data()
    signal = ds.generate_signal(data)
    assert signal is None, "Expected no signal (RSI>200 is impossible)"
    print("  ✅ No signal (impossible rule)")


def test_invalid_config():
    """Invalid config fails validation."""
    ds = DynamicStrategy(INVALID_CONFIG)
    assert ds.validate() is False
    print("  ✅ Invalid config rejected")


def test_from_file():
    """Load strategy from JSON file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(VALID_CONFIG, f)
        tmp_path = f.name
    try:
        ds = DynamicStrategy.from_file(tmp_path)
        assert ds.name == "test_rsi_strategy"
        assert ds.validate() is True
        signal = ds.generate_signal(_make_sample_data())
        assert signal is not None
        print("  ✅ from_file loads correctly")
    finally:
        os.unlink(tmp_path)


# ── StrategyStore tests ─────────────────────────────────────────────────


def test_strategy_store_crud():
    """Full CRUD cycle: save → load → list → delete."""
    store = StrategyStore(store_dir=tempfile.mkdtemp(prefix="strat_"))

    # Save
    path = store.save(VALID_CONFIG)
    assert os.path.exists(path)
    assert path.endswith(".json")
    print(f"  ✅ Saved to {path}")

    # Load
    loaded = store.load("test_rsi_strategy")
    assert loaded is not None
    assert loaded["name"] == "test_rsi_strategy"
    print("  ✅ Loaded by name")

    # List
    names = store.list_names()
    assert "test_rsi_strategy" in names
    print("  ✅ Listed in names")

    # Delete
    deleted = store.delete("test_rsi_strategy")
    assert deleted is True
    assert store.load("test_rsi_strategy") is None
    print("  ✅ Deleted")


def test_strategy_store_history():
    """Save same strategy twice, get_history returns 2 versions."""
    store = StrategyStore(store_dir=tempfile.mkdtemp(prefix="strat_hist_"))

    store.save(VALID_CONFIG)
    store.save(VALID_CONFIG)

    history = store.get_history("test_rsi_strategy")
    assert len(history) == 2
    assert history[0]["config"]["name"] == "test_rsi_strategy"
    assert history[1]["config"]["name"] == "test_rsi_strategy"
    assert history[0]["timestamp"] < history[1]["timestamp"]
    print(f"  ✅ History: {len(history)} versions")


def test_strategy_store_load_all():
    """load_all returns latest version of each strategy."""
    store = StrategyStore(store_dir=tempfile.mkdtemp(prefix="strat_all_"))

    store.save(VALID_CONFIG)
    store.save(SELL_CONFIG)

    all_cfgs = store.load_all()
    names = {c["name"] for c in all_cfgs}
    assert "test_rsi_strategy" in names
    assert "sell_only" in names
    print(f"  ✅ load_all: {len(all_cfgs)} strategies")


# ── Integration tests ───────────────────────────────────────────────────


def test_store_and_dynamic_integration():
    """Save config → load from store → generate signal."""
    store = StrategyStore(store_dir=tempfile.mkdtemp(prefix="strat_int_"))
    path = store.save(BUY_CONFIG)

    ds = DynamicStrategy.from_file(path)
    assert ds.validate() is True

    signal = ds.generate_signal(_make_sample_data())
    assert signal is not None
    assert signal["action"] == "BUY"
    print(f"  ✅ Integration OK: store → dynamic → {signal['action']}")


def test_schema_validate_config():
    """validate_config works standalone."""
    ok, err = validate_config(VALID_CONFIG)
    assert ok is True
    assert err == ""

    ok, err = validate_config(INVALID_CONFIG)
    assert ok is False
    print("  ✅ Schema validation standalone")

def test_empty_data_returns_none():
    """Empty DataFrame generates no signal."""
    ds = DynamicStrategy(BUY_CONFIG)
    empty = pd.DataFrame()
    assert ds.generate_signal(empty) is None

    single = pd.DataFrame({"close": [100.0]})
    assert ds.generate_signal(single) is None
    print("  ✅ Empty/single-bar data returns None")


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print("=" * 50)
    print("RoyalTDN — Hito 2: DynamicStrategy + StrategyStore")
    print("=" * 50)

    test_load_valid_json()
    test_generate_signal_buy()
    test_generate_signal_sell()
    test_generate_signal_none()
    test_invalid_config()
    test_from_file()
    test_empty_data_returns_none()

    print()
    print("--- StrategyStore ---")
    test_strategy_store_crud()
    test_strategy_store_history()
    test_strategy_store_load_all()

    print()
    print("--- Integration ---")
    test_store_and_dynamic_integration()
    test_schema_validate_config()

    print()
    print("✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
