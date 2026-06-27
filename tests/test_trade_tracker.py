"""Unit tests for TradeTracker recording, eviction, and computed metrics.

Covers:
- Trade dataclass creation
- TradeTracker recording with correct fields (pnl, pnl_pct)
- Ring-buffer eviction when max_trades is exceeded
- Computed properties: win_rate, profit_factor, expectancy,
  best_trade, worst_trade, total_pnl, sharpe_ratio, avg_holding_time
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def tracker() -> "TradeTracker":
    """Return a fresh TradeTracker with default capacity (100)."""
    from royaltdn.core.trade_tracker import TradeTracker
    return TradeTracker()


# ── Trade dataclass ──────────────────────────────────────────────────


def test_trade_dataclass_defaults() -> None:
    """Trade fields should have sensible defaults."""
    from royaltdn.core.trade_tracker import Trade

    t = Trade(symbol="BTCUSDT")
    assert t.symbol == "BTCUSDT"
    assert t.direction == "long"
    assert t.entry_price == 0.0
    assert t.exit_price == 0.0
    assert t.qty == 0.0
    assert t.pnl == 0.0
    assert t.strategy_name == ""
    assert t.exit_reason == "signal"


# ── Trade recording ──────────────────────────────────────────────────


def test_record_single_trade(tracker: "TradeTracker") -> None:
    """Recording a trade should store it and increment total_trades."""
    t = tracker.record_trade(
        symbol="BTCUSDT", direction="long",
        entry_price=30000.0, exit_price=32000.0,
        qty=0.1, pnl=200.0, strategy_name="swing_1",
    )
    assert tracker.total_trades == 1
    assert t.symbol == "BTCUSDT"
    assert t.pnl == 200.0


def test_record_trade_computes_pnl_pct(tracker: "TradeTracker") -> None:
    """pnl_pct should be auto-computed from pnl / (entry_price * qty) * 100."""
    t = tracker.record_trade(
        symbol="BTCUSDT", direction="long",
        entry_price=30000.0, exit_price=32000.0,
        qty=0.1, pnl=200.0, strategy_name="swing_1",
    )
    # 200.0 / (30000 * 0.1) * 100 = 200.0 / 3000 * 100 = 6.67
    assert t.pnl_pct == pytest.approx(6.6667, rel=1e-3)


def test_record_trade_explicit_pnl_pct(tracker: "TradeTracker") -> None:
    """Explicit pnl_pct should be used instead of auto-computed."""
    t = tracker.record_trade(
        symbol="BTCUSDT", direction="long",
        entry_price=30000.0, exit_price=32000.0,
        qty=0.1, pnl=200.0, pnl_pct=99.9, strategy_name="swing_1",
    )
    assert t.pnl_pct == 99.9


def test_record_trade_zero_cost_basis(tracker: "TradeTracker") -> None:
    """pnl_pct should stay 0 when entry_price * qty == 0."""
    t = tracker.record_trade(
        symbol="BTCUSDT", direction="long",
        entry_price=0.0, exit_price=100.0,
        qty=0.0, pnl=50.0, strategy_name="test",
    )
    assert t.pnl_pct == 0.0


# ── Capacity / eviction ──────────────────────────────────────────────


def test_capacity_max_trades_100() -> None:
    """Default max_trades should be 100."""
    from royaltdn.core.trade_tracker import TradeTracker
    tt = TradeTracker()
    assert tt.max_trades == 100


def test_custom_max_trades() -> None:
    """Should accept custom max_trades."""
    from royaltdn.core.trade_tracker import TradeTracker
    tt = TradeTracker(max_trades=5)
    assert tt.max_trades == 5


def test_eviction_oldest_discarded(tracker: "TradeTracker") -> None:
    """101 trades should keep exactly 100, discarding the oldest."""
    for i in range(101):
        tracker.record_trade(
            symbol="BTCUSDT", pnl=float(i),
            strategy_name="test",
        )
    assert tracker.total_trades == 100
    # The first trade (pnl=0) should be evicted; the last (pnl=100) kept
    assert tracker.trades[0].pnl == 1.0  # oldest remaining
    assert tracker.trades[-1].pnl == 100.0  # newest


def test_eviction_at_capacity(tracker: "TradeTracker") -> None:
    """Trades exactly at capacity should keep all."""
    for i in range(100):
        tracker.record_trade(
            symbol="BTCUSDT", pnl=float(i),
            strategy_name="test",
        )
    assert tracker.total_trades == 100
    assert tracker.trades[0].pnl == 0.0  # oldest
    assert tracker.trades[-1].pnl == 99.0  # newest


# ── Computed properties: count and winning ───────────────────────────


def test_total_trades_empty(tracker: "TradeTracker") -> None:
    """Empty tracker should report 0 total_trades."""
    assert tracker.total_trades == 0


def test_win_rate_all_winners(tracker: "TradeTracker") -> None:
    """All winning trades → win_rate = 1.0."""
    for i in range(10):
        tracker.record_trade(symbol="BTCUSDT", pnl=50.0, strategy_name="test")
    assert tracker.win_rate == 1.0


def test_win_rate_all_losers(tracker: "TradeTracker") -> None:
    """All losing trades → win_rate = 0.0."""
    for i in range(5):
        tracker.record_trade(symbol="BTCUSDT", pnl=-10.0, strategy_name="test")
    assert tracker.win_rate == 0.0


def test_win_rate_mixed(tracker: "TradeTracker") -> None:
    """3 winners, 2 losers → win_rate = 0.6."""
    for _ in range(3):
        tracker.record_trade(symbol="BTCUSDT", pnl=50.0, strategy_name="test")
    for _ in range(2):
        tracker.record_trade(symbol="BTCUSDT", pnl=-10.0, strategy_name="test")
    assert tracker.win_rate == pytest.approx(0.6)


def test_win_rate_empty(tracker: "TradeTracker") -> None:
    """Empty tracker → win_rate = 0.0."""
    assert tracker.win_rate == 0.0


# ── Profit factor ────────────────────────────────────────────────────


def test_profit_factor_all_winners(tracker: "TradeTracker") -> None:
    """No losses → profit_factor = inf."""
    for i in range(3):
        tracker.record_trade(symbol="BTCUSDT", pnl=100.0, strategy_name="test")
    assert tracker.profit_factor == float("inf")


def test_profit_factor_all_losers(tracker: "TradeTracker") -> None:
    """No profits → profit_factor = 0.0."""
    for i in range(3):
        tracker.record_trade(symbol="BTCUSDT", pnl=-50.0, strategy_name="test")
    assert tracker.profit_factor == 0.0


def test_profit_factor_mixed(tracker: "TradeTracker") -> None:
    """Gross profit 300, gross loss 100 → profit_factor = 3.0."""
    tracker.record_trade(symbol="A", pnl=200.0, strategy_name="test")
    tracker.record_trade(symbol="B", pnl=100.0, strategy_name="test")
    tracker.record_trade(symbol="C", pnl=-100.0, strategy_name="test")
    assert tracker.profit_factor == pytest.approx(3.0)


def test_profit_factor_empty(tracker: "TradeTracker") -> None:
    """Empty tracker → profit_factor = 0.0."""
    assert tracker.profit_factor == 0.0


# ── Expectancy ───────────────────────────────────────────────────────


def test_expectancy(tracker: "TradeTracker") -> None:
    """Sum(pnl) / count = expectancy."""
    tracker.record_trade(symbol="A", pnl=200.0, strategy_name="test")
    tracker.record_trade(symbol="B", pnl=100.0, strategy_name="test")
    tracker.record_trade(symbol="C", pnl=-50.0, strategy_name="test")
    # (200 + 100 - 50) / 3 = 250 / 3 = 83.33
    assert tracker.expectancy == pytest.approx(83.3333, rel=1e-3)


def test_expectancy_empty(tracker: "TradeTracker") -> None:
    """Empty tracker → expectancy = 0.0."""
    assert tracker.expectancy == 0.0


# ── Best / worst trade ───────────────────────────────────────────────


def test_best_trade(tracker: "TradeTracker") -> None:
    """best_trade should return the trade with highest pnl."""
    tracker.record_trade(symbol="A", pnl=50.0, strategy_name="test")
    tracker.record_trade(symbol="B", pnl=200.0, strategy_name="test")
    tracker.record_trade(symbol="C", pnl=10.0, strategy_name="test")
    assert tracker.best_trade is not None
    assert tracker.best_trade.symbol == "B"
    assert tracker.best_trade.pnl == 200.0


def test_worst_trade(tracker: "TradeTracker") -> None:
    """worst_trade should return the trade with lowest pnl."""
    tracker.record_trade(symbol="A", pnl=50.0, strategy_name="test")
    tracker.record_trade(symbol="B", pnl=-100.0, strategy_name="test")
    tracker.record_trade(symbol="C", pnl=10.0, strategy_name="test")
    assert tracker.worst_trade is not None
    assert tracker.worst_trade.symbol == "B"
    assert tracker.worst_trade.pnl == -100.0


def test_best_worst_empty(tracker: "TradeTracker") -> None:
    """Empty tracker → best_trade and worst_trade are None."""
    assert tracker.best_trade is None
    assert tracker.worst_trade is None


# ── Total P&L ────────────────────────────────────────────────────────


def test_total_pnl(tracker: "TradeTracker") -> None:
    """total_pnl should sum all trade P&Ls."""
    tracker.record_trade(symbol="A", pnl=200.0, strategy_name="test")
    tracker.record_trade(symbol="B", pnl=-50.0, strategy_name="test")
    tracker.record_trade(symbol="C", pnl=30.0, strategy_name="test")
    assert tracker.total_pnl == 180.0


def test_total_pnl_empty(tracker: "TradeTracker") -> None:
    """Empty tracker → total_pnl = 0.0."""
    assert tracker.total_pnl == 0.0


# ── Sharpe ratio ─────────────────────────────────────────────────────


def test_sharpe_ratio_zero_with_one_trade(tracker: "TradeTracker") -> None:
    """Fewer than 2 trades → sharpe_ratio = 0.0."""
    tracker.record_trade(symbol="A", pnl=100.0, strategy_name="test")
    assert tracker.sharpe_ratio == 0.0


def test_sharpe_ratio_zero_empty(tracker: "TradeTracker") -> None:
    """Empty tracker → sharpe_ratio = 0.0."""
    assert tracker.sharpe_ratio == 0.0


def test_sharpe_ratio_known_values(tracker: "TradeTracker") -> None:
    """Sharpe ratio should compute correctly with known P&L values."""
    # Trades with pnl: [100, 200, 150, 50, 180]
    pnls = [100.0, 200.0, 150.0, 50.0, 180.0]
    for pnl in pnls:
        tracker.record_trade(symbol="A", pnl=pnl, strategy_name="test")

    # mean = 136.0, stdev ≈ 55.59
    # sharpe = (136 / 55.59) * sqrt(252) ≈ 2.446 * 15.874 ≈ 38.82
    import statistics
    _mean = statistics.mean(pnls)
    _stdev = statistics.stdev(pnls)
    expected = (_mean / _stdev) * math.sqrt(252)

    assert tracker.sharpe_ratio == pytest.approx(expected, rel=1e-3)


def test_sharpe_ratio_zero_stdev(tracker: "TradeTracker") -> None:
    """All identical P&Ls → stdev=0 → sharpe_ratio = 0.0."""
    for _ in range(5):
        tracker.record_trade(symbol="A", pnl=100.0, strategy_name="test")
    assert tracker.sharpe_ratio == 0.0


# ── Avg holding time ─────────────────────────────────────────────────


def test_avg_holding_time(tracker: "TradeTracker") -> None:
    """avg_holding_time should return mean of non-zero durations."""
    tracker.record_trade(
        symbol="A", pnl=100.0, strategy_name="test", duration_seconds=3600.0,
    )
    tracker.record_trade(
        symbol="B", pnl=50.0, strategy_name="test", duration_seconds=7200.0,
    )
    assert tracker.avg_holding_time == pytest.approx(5400.0)


def test_avg_holding_time_empty(tracker: "TradeTracker") -> None:
    """Empty tracker → avg_holding_time = 0.0."""
    assert tracker.avg_holding_time == 0.0


def test_avg_holding_time_zero_durations(tracker: "TradeTracker") -> None:
    """Trades without duration data → avg_holding_time = 0.0."""
    tracker.record_trade(symbol="A", pnl=100.0, strategy_name="test")
    tracker.record_trade(symbol="B", pnl=50.0, strategy_name="test")
    assert tracker.avg_holding_time == 0.0


# ── Integration: full spec scenario ──────────────────────────────────


def test_spec_scenario_metrics_after_one_trade(tracker: "TradeTracker") -> None:
    """After one winning trade, win_rate=1.0, PF=inf, expectancy=200.0."""
    tracker.record_trade(
        symbol="BTCUSDT", direction="long",
        entry_price=30000.0, exit_price=32000.0,
        qty=0.1, pnl=200.0, strategy_name="swing_1",
    )
    assert tracker.win_rate == 1.0
    assert tracker.profit_factor == float("inf")
    assert tracker.expectancy == pytest.approx(200.0)
    assert tracker.total_pnl == pytest.approx(200.0)


def test_spec_scenario_profit_factor_with_losses(tracker: "TradeTracker") -> None:
    """2 winners (total 300) + 1 loser (-100) → PF = 3.0."""
    tracker.record_trade(symbol="A", pnl=200.0, strategy_name="test")
    tracker.record_trade(symbol="B", pnl=100.0, strategy_name="test")
    tracker.record_trade(symbol="C", pnl=-100.0, strategy_name="test")
    assert tracker.profit_factor == pytest.approx(3.0)


def test_spec_scenario_sharpe_zero_with_one_trade(tracker: "TradeTracker") -> None:
    """Exactly 1 trade → sharpe_ratio = 0.0."""
    tracker.record_trade(symbol="A", pnl=50.0, strategy_name="test")
    assert tracker.sharpe_ratio == 0.0


def test_readonly_trades_property(tracker: "TradeTracker") -> None:
    """The trades property should return a copy, not the internal list."""
    tracker.record_trade(symbol="A", pnl=100.0, strategy_name="test")
    trades_copy = tracker.trades
    trades_copy.append("not_a_trade")  # type: ignore[arg-type]
    # The mutation should not affect the internal list
    assert tracker.total_trades == 1
