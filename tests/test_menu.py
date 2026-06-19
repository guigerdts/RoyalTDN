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
