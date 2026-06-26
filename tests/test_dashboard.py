"""Unit tests for Dashboard 6-panel Rich rendering.

Covers:
- All six panel builders return Rich ``Panel`` instances.
- Panel rendering with mocked data (no crash).
- Edge cases: empty positions, no trades, unknown engine attrs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_portfolio() -> MagicMock:
    """Return a Portfolio mock with two open positions."""
    p = MagicMock()
    p.capital = 95_000.0
    p.initial_capital = 100_000.0
    p.positions = {"BTCUSDT": 0.5, "ETHUSDT": 2.0}
    p._position_costs = {"BTCUSDT": 30_000.0, "ETHUSDT": 2_000.0}
    p._mtm_prices = {"BTCUSDT": 32_000.0, "ETHUSDT": 2_100.0}
    p.get_total_value.return_value = 120_200.0
    p.get_drawdown.return_value = 0.05
    return p


@pytest.fixture
def mock_empty_portfolio() -> MagicMock:
    """Return a Portfolio mock with no open positions."""
    p = MagicMock()
    p.capital = 100_000.0
    p.initial_capital = 100_000.0
    p.positions = {}
    p._position_costs = {}
    p._mtm_prices = {}
    p.get_total_value.return_value = 100_000.0
    p.get_drawdown.return_value = 0.0
    return p


@pytest.fixture
def mock_trade_tracker() -> MagicMock:
    """Return a TradeTracker mock with sample trades."""
    tt = MagicMock()
    tt.total_trades = 25
    tt.win_rate = 0.64
    tt.profit_factor = 2.5
    tt.expectancy = 185.0
    tt.total_pnl = 4_625.0
    tt.sharpe_ratio = 1.85
    tt.avg_holding_time = 7_200.0

    # Sample trade list
    best = MagicMock()
    best.pnl = 500.0
    worst = MagicMock()
    worst.pnl = -200.0
    tt.best_trade = best
    tt.worst_trade = worst

    from core.trade_tracker import Trade

    tt.trades = [
        Trade(
            symbol="BTCUSDT", direction="long",
            entry_price=30_000.0, exit_price=32_000.0,
            qty=0.1, pnl=200.0, duration_seconds=3_600.0,
            strategy_name="swing_1",
        ),
        Trade(
            symbol="ETHUSDT", direction="long",
            entry_price=2_000.0, exit_price=1_900.0,
            qty=1.0, pnl=-100.0, duration_seconds=1_800.0,
            strategy_name="scalp_1",
        ),
    ]
    return tt


@pytest.fixture
def mock_engine() -> MagicMock:
    """Return an Engine mock in paper mode."""
    e = MagicMock()
    e.bus = MagicMock()
    e._running = True
    e.mode = "paper"
    e.start_time = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
    e.cells = ["swing_1", "scalp_1", "grid_1"]
    return e


@pytest.fixture
def mock_engine_no_extras() -> MagicMock:
    """Return an Engine mock without mode / start_time attrs (T5 not applied yet)."""
    e = MagicMock(spec=["bus", "_running", "cells"])
    e.bus = MagicMock()
    e._running = True
    e.cells = []
    # mode, start_time deliberately absent
    return e


@pytest.fixture
def dashboard(
    mock_portfolio: MagicMock,
    mock_trade_tracker: MagicMock,
    mock_engine: MagicMock,
) -> "Dashboard":
    """Return a Dashboard wired to mocked data sources."""
    from monitoring.dashboard import Dashboard
    return Dashboard(mock_portfolio, mock_trade_tracker, mock_engine)


@pytest.fixture
def empty_dashboard(
    mock_empty_portfolio: MagicMock,
    mock_trade_tracker: MagicMock,
    mock_engine: MagicMock,
) -> "Dashboard":
    """Return a Dashboard with no open positions."""
    from monitoring.dashboard import Dashboard
    return Dashboard(mock_empty_portfolio, mock_trade_tracker, mock_engine)


@pytest.fixture
def dashboard_no_trades(
    mock_portfolio: MagicMock,
    mock_engine: MagicMock,
) -> "Dashboard":
    """Return a Dashboard with no TradeTracker data."""
    from monitoring.dashboard import Dashboard
    tt = MagicMock()
    tt.total_trades = 0
    tt.trades = []
    tt.win_rate = 0.0
    tt.profit_factor = 0.0
    tt.expectancy = 0.0
    tt.total_pnl = 0.0
    tt.sharpe_ratio = 0.0
    tt.avg_holding_time = 0.0
    tt.best_trade = None
    tt.worst_trade = None
    return Dashboard(mock_portfolio, tt, mock_engine)


# ── Panel builder tests ──────────────────────────────────────────────


def test_build_kpi_bar_panel_returns_panel(dashboard: "Dashboard") -> None:
    """KPI Bar panel should return a Rich Panel."""
    from rich.panel import Panel

    result = dashboard._build_kpi_bar_panel()
    assert isinstance(result, Panel)


def test_build_open_positions_panel_returns_panel(dashboard: "Dashboard") -> None:
    """Open Positions panel should return a Rich Panel."""
    from rich.panel import Panel

    result = dashboard._build_open_positions_panel()
    assert isinstance(result, Panel)


def test_build_closed_trades_panel_returns_panel(dashboard: "Dashboard") -> None:
    """Closed Trades panel should return a Rich Panel."""
    from rich.panel import Panel

    result = dashboard._build_closed_trades_panel()
    assert isinstance(result, Panel)


def test_build_prof_metrics_panel_returns_panel(dashboard: "Dashboard") -> None:
    """Professional Metrics panel should return a Rich Panel."""
    from rich.panel import Panel

    result = dashboard._build_prof_metrics_panel()
    assert isinstance(result, Panel)


def test_build_bot_status_panel_returns_panel(dashboard: "Dashboard") -> None:
    """Bot Status panel should return a Rich Panel."""
    from rich.panel import Panel

    result = dashboard._build_bot_status_panel()
    assert isinstance(result, Panel)


def test_build_events_panel_returns_panel(dashboard: "Dashboard") -> None:
    """Events panel should return a Rich Panel."""
    from rich.panel import Panel

    result = dashboard._build_events_panel()
    assert isinstance(result, Panel)


# ── All panels at once ──────────────────────────────────────────────


def test_all_panels_render_with_live_data(dashboard: "Dashboard") -> None:
    """All 6 panel builders return Panels with mocked live data.

    This is the spec scenario: GIVEN Engine running with real
    Portfolio, TradeTracker, and Journal — WHEN rendered — THEN
    6 distinct panels appear.
    """
    from rich.panel import Panel

    builders = [
        dashboard._build_kpi_bar_panel,
        dashboard._build_open_positions_panel,
        dashboard._build_closed_trades_panel,
        dashboard._build_prof_metrics_panel,
        dashboard._build_bot_status_panel,
        dashboard._build_events_panel,
    ]

    for builder in builders:
        result = builder()
        assert isinstance(result, Panel), f"{builder.__name__} did not return Panel"


def test_refresh_no_crash(dashboard: "Dashboard") -> None:
    """Running a single refresh cycle should not crash with mocked data."""
    import asyncio
    from collections import deque
    from rich.panel import Panel

    dashboard._events = deque(maxlen=50)
    dashboard._running = True

    # Simulate a single refresh cycle (what _run_rich does per iteration)
    panels = [
        dashboard._build_kpi_bar_panel(),
        dashboard._build_open_positions_panel(),
        dashboard._build_closed_trades_panel(),
        dashboard._build_prof_metrics_panel(),
        dashboard._build_bot_status_panel(),
        dashboard._build_events_panel(),
    ]

    for p in panels:
        assert isinstance(p, Panel)


# ── Edge cases ───────────────────────────────────────────────────────


def test_empty_positions_renders(empty_dashboard: "Dashboard") -> None:
    """Dashboard with no open positions should still render all panels."""
    from rich.panel import Panel

    assert isinstance(empty_dashboard._build_open_positions_panel(), Panel)


def test_no_trades_renders(dashboard_no_trades: "Dashboard") -> None:
    """Dashboard with no trades should show fallback text in trade panels."""
    from rich.panel import Panel

    assert isinstance(dashboard_no_trades._build_closed_trades_panel(), Panel)
    assert isinstance(dashboard_no_trades._build_prof_metrics_panel(), Panel)


def test_engine_without_mode_starttime(dashboard_no_trades: "Dashboard") -> None:
    """Bot Status should handle missing mode/start_time gracefully."""
    from rich.panel import Panel

    # Create a dashboard with an engine that lacks mode/start_time
    from unittest.mock import MagicMock
    from monitoring.dashboard import Dashboard

    engine = MagicMock(spec=["bus", "_running", "cells"])
    engine.bus = MagicMock()
    engine._running = True
    engine.cells = []

    import collections
    mock_portfolio = MagicMock()
    mock_portfolio.positions = {}
    mock_portfolio._position_costs = {}
    mock_portfolio._mtm_prices = {}
    mock_portfolio.capital = 100_000.0
    mock_portfolio.initial_capital = 100_000.0
    mock_portfolio.get_total_value.return_value = 100_000.0
    mock_portfolio.get_drawdown.return_value = 0.0

    d = Dashboard(mock_portfolio, None, engine)
    result = d._build_bot_status_panel()
    assert isinstance(result, Panel)


def test_event_panel_with_events(dashboard: "Dashboard") -> None:
    """Events panel should render with sample events in the buffer."""
    from rich.panel import Panel
    from collections import deque

    dashboard._events = deque(maxlen=50)
    dashboard._events.append({"type": "signal", "symbol": "BTCUSDT", "action": "BUY", "price": 30000.0})
    dashboard._events.append({"type": "approved", "symbol": "BTCUSDT", "detail": "ok"})
    dashboard._events.append({"type": "rejected", "symbol": "ETHUSDT", "detail": "max_positions"})
    dashboard._events.append({"type": "executed", "symbol": "BTCUSDT", "qty": 0.1, "price": 30000.0})
    dashboard._events.append({"type": "position", "symbol": "BTCUSDT", "status": "opened", "capital": 97000.0})
    dashboard._events.append({"type": "position", "symbol": "BTCUSDT", "status": "closed", "pnl": 200.0})

    result = dashboard._build_events_panel()
    assert isinstance(result, Panel)


# ── Duration helper ──────────────────────────────────────────────────


def test_fmt_duration() -> None:
    """_fmt_duration should format seconds correctly."""
    from monitoring.dashboard import Dashboard

    assert Dashboard._fmt_duration(0.0) == "-"
    assert Dashboard._fmt_duration(30.0) == "30s"
    assert Dashboard._fmt_duration(120.0) == "2m"
    assert Dashboard._fmt_duration(3660.0) == "1.0h"
    assert Dashboard._fmt_duration(90000.0) == "1.0d"
    assert Dashboard._fmt_duration(-5.0) == "-"


def test_fmt_event_detail() -> None:
    """_fmt_event_detail should format by event type."""
    from monitoring.dashboard import Dashboard

    assert Dashboard._fmt_event_detail({"price": 30000.0}, "tick") == "$30000.00"
    assert Dashboard._fmt_event_detail({"action": "BUY", "price": 30000.0}, "signal") == "BUY @ $30000.00"
    assert Dashboard._fmt_event_detail({"detail": "ok"}, "approved") == "ok"
    assert Dashboard._fmt_event_detail({}, "approved") == "risk_approved"
    assert Dashboard._fmt_event_detail({"detail": "max_pos"}, "rejected") == "max_pos"
    assert Dashboard._fmt_event_detail({"qty": 0.1, "price": 30000.0}, "executed") == "0.1 @ $30000.00"
    assert Dashboard._fmt_event_detail({"action": "SELL", "qty": 0.1, "price": 32000.0}, "trade") == "SELL 0.1 @ $32000.00"
    assert Dashboard._fmt_event_detail({"status": "opened", "capital": 97000.0}, "position") == "capital=$97,000.00"
    assert Dashboard._fmt_event_detail({"status": "closed", "pnl": 200.0}, "position") == "PnL=$+200.00"
    assert Dashboard._fmt_event_detail({}, "unknown") == "-"
