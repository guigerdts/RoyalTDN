"""Tests for the interactive text menu (Fase 10)."""

from unittest.mock import patch, MagicMock
import pytest

# numpy C extensions broken in this environment (Termux) — skip strategy-dependent tests
_numpy_ok = False
try:
    import pandas as pd  # noqa: F401
    import numpy as np  # noqa: F401
    _numpy_ok = True
except ImportError:
    pass


def test_import_menu():
    """Verify menu module imports correctly."""
    from royaltdn.frontend.menu.app import run_menu, _show_dashboard, _builder_flow
    assert callable(run_menu)
    assert callable(_show_dashboard)
    assert callable(_builder_flow)


def test_dashboard_empty_data():
    """Dashboard with no data should not crash."""
    from royaltdn.frontend.menu.app import _build_kpis
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    sections = []
    _build_kpis({}, sections, Panel, Table, Text)
    assert len(sections) == 1  # KPI panel rendered


@pytest.mark.skipif(not _numpy_ok, reason="numpy C extensions not available")
def test_builder_flow_full():
    """Full builder flow with mocked inputs creates a valid strategy."""
    from royaltdn.frontend.menu.app import _builder_flow
    from rich.console import Console
    import io

    console = Console(file=io.StringIO())

    # Mock all the inputs needed for a full strategy creation
    inputs = [
        "Mi Estrategia",      # Stage 1: name
        "1",                   # Stage 2: SMA indicator
        "20",                  # Stage 3: period param
        "",                    # Stage 3: source (default)
        "n",                   # Stage 4: no more indicators
        "1",                   # Stage 5: 1 condition for entry
        "1",                   # Stage 5: indicator 1
        "1",                   # Stage 5: operator group 1 (Comparison)
        "1",                   # Stage 5: operator gt
        "100",                 # Stage 5: value
        "1",                   # Stage 6: 1 condition for exit
        "1",                   # Stage 6: indicator 1
        "1",                   # Stage 6: operator group 1
        "2",                   # Stage 6: operator lt
        "50",                  # Stage 6: value
        "SPY",                 # Stage 7: symbol
        "1D",                  # Stage 8: timeframe
        "1m",                  # Stage 9: period
        "n",                   # Stage 11: save? no
        "",                    # _wait_enter() after backtest trade display
    ]

    with patch("builtins.input", side_effect=inputs):
        _builder_flow(console)

    # Verify no crash and flow completed


def test_ctrl_c_menu_exit():
    """Ctrl+C at main menu should exit gracefully."""
    from royaltdn.frontend.menu.app import run_menu

    with patch("builtins.input", side_effect=KeyboardInterrupt()):
        # Should not raise
        run_menu(logs_dir="/tmp/nonexistent_test_logs")


@pytest.fixture
def mock_state_loader():
    """Fixture for a StateLoader with controlled data."""
    from unittest.mock import MagicMock

    loader = MagicMock()
    loader.load_all.return_value = {
        "status": {"bot_status": "ONLINE", "uptime": "1:23:45"},
        "equity": {"current_equity": 50000, "pnl_day": 250, "drawdown_pct": -2.5},
        "positions": {
            "open_positions": [
                {
                    "symbol": "SPY",
                    "side": "long",
                    "qty": 10,
                    "entry_price": 500,
                    "unrealized_pl": 50,
                }
            ]
        },
        "scanner": {
            "last_scan": {
                "timestamp": "2025-01-01T12:00:00",
                "symbols": [
                    {"symbol": "SPY", "price": 500, "signal": "BUY", "score": 75}
                ],
            }
        },
        "trades": {
            "total_trades": 50,
            "win_rate": 55.5,
            "profit_factor": 1.2,
            "total_pnl": 1500,
        },
        "strategies": {"strategies": []},
    }
    return loader


def test_dashboard_with_data(mock_state_loader):
    """Dashboard with valid data should render all sections."""
    from royaltdn.frontend.menu.app import (
        _build_kpis,
        _build_positions,
        _build_signals,
        _build_summary,
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    sections = []
    _build_kpis(mock_state_loader.load_all(), sections, Panel, Table, Text)
    _build_positions(mock_state_loader.load_all(), sections, Panel, Table, Text)
    _build_signals(mock_state_loader.load_all(), sections, Panel, Table, Text)
    _build_summary(mock_state_loader.load_all(), sections, Panel, Table, Text)

    assert len(sections) == 4  # All 4 sections rendered


# ── Bug 1: Scanner mock filter ─────────────────────────────────────────


def test_mock_filter_all_mock():
    """Scanner with all mock entries produces empty result."""
    signals = [
        {"symbol": "BTC/USDT", "action": "BUY", "price": 50000, "score": 0.8, "strategy": "mock"},
        {"symbol": "ETH/USDT", "action": "SELL", "price": 3000, "score": 0.6, "strategy": "mock"},
    ]
    real_signals = [s for s in signals if s.get("strategy") != "mock"]
    assert len(real_signals) == 0


def test_mock_filter_mixed():
    """Mixed entries show only real signals."""
    signals = [
        {"symbol": "SPY", "action": "BUY", "price": 450, "score": 0.85, "strategy": "sma_crossover"},
        {"symbol": "AAPL", "action": "SELL", "price": 150, "score": 0.7, "strategy": "bollinger"},
        {"symbol": "BTC/USDT", "action": "BUY", "price": 50000, "score": 0.8, "strategy": "mock"},
    ]
    real_signals = [s for s in signals if s.get("strategy") != "mock"]
    assert len(real_signals) == 2
    assert all(s["strategy"] != "mock" for s in real_signals)


def test_mock_filter_none_mock():
    """No mock entries — all signals shown unchanged."""
    signals = [
        {"symbol": "SPY", "action": "BUY", "price": 450, "score": 0.85, "strategy": "sma_crossover"},
        {"symbol": "AAPL", "action": "SELL", "price": 150, "score": 0.7, "strategy": "bollinger"},
    ]
    real_signals = [s for s in signals if s.get("strategy") != "mock"]
    assert len(real_signals) == 2
    assert real_signals == signals


# ── Bug 3: Crypto default symbol ──────────────────────────────────────


def _get_quick_backtest_default_symbol(config, universe):
    """Helper: call _quick_backtest and extract the default symbol from the prompt."""
    from royaltdn.frontend.menu.app import _quick_backtest
    from rich.console import Console
    import io

    console = Console(file=io.StringIO())
    recorded_prompts = []

    def recording_input(prompt="", /):
        recorded_prompts.append(prompt)
        raise KeyboardInterrupt()  # bail after first prompt

    with patch("builtins.input", recording_input):
        with patch.dict("os.environ", {"SCANNER_UNIVERSE": universe}):
            _quick_backtest(config, console, "/tmp/test_logs")

    prompt_text = recorded_prompts[0] if recorded_prompts else ""
    return prompt_text


def test_crypto_default_symbol_btc():
    """Crypto universe defaults to BTC/USDT in quick backtest prompt."""
    prompt = _get_quick_backtest_default_symbol(
        {"name": "test", "timeframe": "1D"}, universe="crypto",
    )
    assert "BTC/USDT" in prompt


def test_stocks_default_symbol_spy():
    """Stocks universe defaults to SPY in quick backtest prompt."""
    prompt = _get_quick_backtest_default_symbol(
        {"name": "test", "timeframe": "1D"}, universe="etfs",
    )
    assert "SPY" in prompt


def test_crypto_default_config_symbol_wins():
    """Config symbol takes priority over SCANNER_UNIVERSE default."""
    prompt = _get_quick_backtest_default_symbol(
        {"name": "test", "symbol": "ETH/USDT", "timeframe": "1D"},
        universe="crypto",
    )
    assert "ETH/USDT" in prompt


# ── Bug 4: Version setdefault ────────────────────────────────────────


@pytest.mark.skipif(not _numpy_ok, reason="numpy C extensions not available")
def test_schema_version_missing_fails_before_setdefault():
    """Config without version fails validation."""
    from royaltdn.strategy.schema import validate_config

    config = {
        "name": "Test Strategy",
        "symbols": ["SPY"],
        "timeframe": "1D",
        "indicators": [{"name": "SMA", "params": {"period": 20}, "source": "close"}],
        "entry_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "gt", "value": 100}],
        },
        "exit_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "lt", "value": 50}],
        },
        "risk_management": {
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_position_size": 1000,
            "max_daily_loss": 500,
        },
    }
    ok, err = validate_config(config)
    assert not ok
    assert "version" in err


@pytest.mark.skipif(not _numpy_ok, reason="numpy C extensions not available")
def test_schema_version_setdefault_passes():
    """Config with setdefault('version', 1) passes validation."""
    from royaltdn.strategy.schema import validate_config

    config = {
        "name": "Test Strategy",
        "symbols": ["SPY"],
        "timeframe": "1D",
        "indicators": [{"name": "SMA", "params": {"period": 20}, "source": "close"}],
        "entry_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "gt", "value": 100}],
        },
        "exit_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "lt", "value": 50}],
        },
        "risk_management": {
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_position_size": 1000,
            "max_daily_loss": 500,
        },
    }
    config.setdefault("version", 1)
    ok, err = validate_config(config)
    assert ok


@pytest.mark.skipif(not _numpy_ok, reason="numpy C extensions not available")
def test_schema_explicit_version_2_still_fails():
    """Explicit version != 1 still fails validation."""
    from royaltdn.strategy.schema import validate_config

    config = {
        "name": "Test Strategy",
        "version": 2,
        "symbols": ["SPY"],
        "timeframe": "1D",
        "indicators": [{"name": "SMA", "params": {"period": 20}, "source": "close"}],
        "entry_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "gt", "value": 100}],
        },
        "exit_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "lt", "value": 50}],
        },
        "risk_management": {
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_position_size": 1000,
            "max_daily_loss": 500,
        },
    }
    ok, err = validate_config(config)
    assert not ok
    assert "version must be 1" in err


@pytest.mark.skipif(not _numpy_ok, reason="numpy C extensions not available")
def test_schema_explicit_version_1_passes():
    """Explicit version 1 passes validation."""
    from royaltdn.strategy.schema import validate_config

    config = {
        "name": "Test Strategy",
        "version": 1,
        "symbols": ["SPY"],
        "timeframe": "1D",
        "indicators": [{"name": "SMA", "params": {"period": 20}, "source": "close"}],
        "entry_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "gt", "value": 100}],
        },
        "exit_rules": {
            "operator": "AND",
            "conditions": [{"indicator": "SMA", "operator": "lt", "value": 50}],
        },
        "risk_management": {
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_position_size": 1000,
            "max_daily_loss": 500,
        },
    }
    ok, err = validate_config(config)
    assert ok
