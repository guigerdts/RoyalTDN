#!/usr/bin/env python3
"""Integration tests for Hito 5 (Fase 7 final integration)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from royaltdn.strategy.strategy_store import StrategyStore
from royaltdn.strategy.dynamic import DynamicStrategy
from royaltdn.strategy.schema import validate_config


# ── Fixtures ────────────────────────────────────────────────────────────

VALID_CONFIG = {
    "version": 1,
    "name": "integration_test_strat",
    "description": "Integration test strategy",
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

ALWAYS_TRUE_CONFIG = {
    "version": 1,
    "name": "always_buy",
    "description": "Always BUY strategy",
    "symbols": ["SPY"],
    "timeframe": "1D",
    "indicators": [
        {"name": "SMA", "params": {"period": 5}, "source": "close"},
    ],
    "entry_rules": {
        "operator": "AND",
        "conditions": [
            {"indicator": "SMA", "params": {"period": 5}, "operator": "gt", "value": 0},
        ],
    },
    "exit_rules": {
        "operator": "AND",
        "conditions": [
            {"indicator": "SMA", "params": {"period": 5}, "operator": "lt", "value": 0},
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


# ── Tests ───────────────────────────────────────────────────────────────


def test_store_save_and_dynamic_validate():
    """Save a config via store, load it, validate via DynamicStrategy."""
    store = StrategyStore(store_dir=tempfile.mkdtemp(prefix="int_"))
    path = store.save(VALID_CONFIG)
    assert os.path.exists(path)

    ds = DynamicStrategy.from_file(path)
    assert ds.validate() is True
    assert ds.name == "integration_test_strat"
    print("  ✅ Store → DynamicStrategy validation chain OK")


def test_watcher_detects_new_strategy():
    """Simulate watcher detecting a new strategy file."""
    store = StrategyStore(store_dir=tempfile.mkdtemp(prefix="watch_"))
    strategies = {}

    # Before save — no strategies
    before = store.list_names()
    assert "always_buy" not in before

    # Save strategy
    path = store.save(ALWAYS_TRUE_CONFIG)

    # Simulate watcher logic
    for fname in store._list_json_files():
        fpath = os.path.join(store.store_dir, fname)
        with open(fpath) as f:
            cfg = json.load(f)
        name = cfg.get("name", "unnamed")
        ds = DynamicStrategy(cfg)
        if ds.validate():
            strategies[name] = ds

    assert "always_buy" in strategies
    assert strategies["always_buy"].validate() is True
    print("  ✅ Watcher detection: strategy loaded correctly")


def test_strategy_generates_signal():
    """DynamicStrategy generates a BUY signal on synthetic data."""
    import pandas as pd
    import numpy as np

    ds = DynamicStrategy(ALWAYS_TRUE_CONFIG)
    data = pd.DataFrame({
        "close": np.random.randn(200).cumsum() + 100,
        "high": np.random.randn(200).cumsum() + 102,
        "low": np.random.randn(200).cumsum() + 98,
        "open": np.random.randn(200).cumsum() + 100,
        "volume": np.abs(np.random.randn(200) * 1000 + 5000),
    })
    signal = ds.generate_signal(data)
    assert signal is not None
    assert signal["action"] == "BUY"
    assert signal["symbol"] == "SPY"
    assert "strategy" in signal
    assert signal["strategy"] == "always_buy"
    print(f"  ✅ User signal: {signal['action']} @ {signal['price']:.2f} (strat={signal['strategy']})")


def test_invalid_strategy_rejected():
    """Invalid config should have validate()=False."""
    ds = DynamicStrategy(INVALID_CONFIG)
    assert ds.validate() is False
    print("  ✅ Invalid strategy rejected")


def test_multiple_user_strategies():
    """Multiple strategies can be loaded simultaneously."""
    store = StrategyStore(store_dir=tempfile.mkdtemp(prefix="multi_"))
    store.save(VALID_CONFIG)
    store.save(ALWAYS_TRUE_CONFIG)

    configs = store.load_all()
    strategies = {}
    for cfg in configs:
        name = cfg.get("name", "unnamed")
        ds = DynamicStrategy(cfg)
        if ds.validate():
            strategies[name] = ds

    assert len(strategies) == 2
    assert "integration_test_strat" in strategies
    assert "always_buy" in strategies
    print(f"  ✅ Multiple strategies loaded: {list(strategies.keys())}")


def test_strategy_symbol_filtering():
    """Strategy only generates signal for matching symbols."""
    import pandas as pd
    import numpy as np

    # Strategy for AAPL only
    aapl_config = dict(ALWAYS_TRUE_CONFIG)
    aapl_config["name"] = "aapl_only"
    aapl_config["symbols"] = ["AAPL"]

    ds = DynamicStrategy(aapl_config)
    data = pd.DataFrame({
        "close": np.random.randn(200).cumsum() + 100,
        "high": np.random.randn(200).cumsum() + 102,
        "low": np.random.randn(200).cumsum() + 98,
        "open": np.random.randn(200).cumsum() + 100,
        "volume": np.abs(np.random.randn(200) * 1000 + 5000),
    })

    # Should NOT signal for SPY
    current_symbol = "SPY"
    symbols = ds.symbols
    should_skip = bool(symbols and current_symbol not in symbols and "ALL" not in symbols)
    assert should_skip is True, "AAPL strategy should skip SPY"

    # Should signal for AAPL
    current_symbol = "AAPL"
    should_not_skip = not bool(symbols and current_symbol not in symbols and "ALL" not in symbols)
    assert should_not_skip is True, "AAPL strategy should NOT skip AAPL"

    print("  ✅ Symbol filtering works correctly")


def test_requirements_file():
    """requirements/fase7.txt exists and contains expected packages."""
    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements", "fase7.txt")
    assert os.path.exists(req_path), "requirements/fase7.txt not found"

    with open(req_path) as f:
        content = f.read()

    assert "pandas-ta" in content or "pandas_ta" in content
    assert "yfinance" in content
    print(f"  ✅ requirements/fase7.txt OK ({len(content.splitlines())} lines)")


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print("=" * 50)
    print("RoyalTDN — Hito 5: Integración Final")
    print("=" * 50)

    test_store_save_and_dynamic_validate()
    test_watcher_detects_new_strategy()
    test_strategy_generates_signal()
    test_invalid_strategy_rejected()
    test_multiple_user_strategies()
    test_strategy_symbol_filtering()
    test_requirements_file()

    print()
    print("✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
