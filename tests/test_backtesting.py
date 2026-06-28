"""Tests for M4 backtester foundation components (PR 1).

Covers:
- PaperBroker slippage and commission (``execution/paper_broker.py``)
- EventEngine ``run_batch()`` (``core/engine.py``)
- Replayer (``royaltdn/backtesting/replayer.py``)
- Metrics (``royaltdn/backtesting/metrics.py``)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

# pandas is imported lazily inside tests that need it (it depends on
# numpy, which may be broken on some platforms).

# Detect whether numpy is usable at runtime.  The C extensions may be
# broken on Termux / Android, preventing even a simple ``import numpy``.
# Tests that call numpy-dependent code are skipped when it's broken.
_HAS_NUMPY: bool = False
try:
    import numpy as _np  # noqa: F401

    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False

NUMPY_SKIP_REASON = "numpy C extensions unavailable on this system"


# ========================================================================
# PaperBroker — Slippage & Commission
# ========================================================================


@pytest.fixture
def broker_portfolio():
    """Return a Portfolio and a PaperBroker wired to it with realistic
    commission and slippage."""
    from royaltdn.risk.portfolio import Portfolio
    from royaltdn.execution.paper_broker import PaperBroker

    portfolio = Portfolio(initial_capital=100_000.0)
    broker = PaperBroker(
        portfolio=portfolio,
        commission_pct=0.001,
        slippage_pct=0.0005,
    )
    return portfolio, broker


class TestPaperBrokerCosts:
    """PaperBroker commission_pct / slippage_pct behaviour."""

    # -- Slippage -----------------------------------------------------------

    def test_buy_fill_price_increases(self, broker_portfolio):
        """BUY fills at price * (1 + slippage)."""
        _, broker = broker_portfolio
        result = asyncio.run(
            broker.submit_order({
                "action": "BUY", "symbol": "BTC/USDT", "price": 100.0, "qty": 1.0,
            })
        )
        assert result["fill_price"] == pytest.approx(100.05, rel=1e-9)

    def test_sell_fill_price_decreases(self, broker_portfolio):
        """SELL fills at price * (1 - slippage)."""
        _, broker = broker_portfolio
        result = asyncio.run(
            broker.submit_order({
                "action": "SELL", "symbol": "BTC/USDT", "price": 50.0, "qty": 1.0,
            })
        )
        assert result["fill_price"] == pytest.approx(49.975, rel=1e-9)

    def test_short_fill_price_decreases(self, broker_portfolio):
        """SHORT fills at price * (1 - slippage) — same as SELL."""
        _, broker = broker_portfolio
        result = asyncio.run(
            broker.submit_order({
                "action": "SHORT", "symbol": "BTC/USDT", "price": 50.0, "qty": 1.0,
            })
        )
        assert result["fill_price"] == pytest.approx(49.975, rel=1e-9)

    # -- Commission ---------------------------------------------------------

    def test_commission_recorded_in_trade_dict(self, broker_portfolio):
        """Trade dict includes commission and slippage fields."""
        _, broker = broker_portfolio
        result = asyncio.run(
            broker.submit_order({
                "action": "BUY", "symbol": "BTC/USDT", "price": 100.0, "qty": 10.0,
            })
        )
        assert "commission" in result
        assert "slippage" in result
        # notional = fill_price * qty = 100.05 * 10 = 1000.5
        # commission = 1000.5 * 0.001 = 1.0005
        expected = 1000.5 * 0.001
        assert result["commission"] == pytest.approx(expected, rel=1e-9)

    def test_commission_baked_into_effective_price(self, broker_portfolio):
        """For BUY, effective price = fill_price * (1 + commission)."""
        _, broker = broker_portfolio
        result = asyncio.run(
            broker.submit_order({
                "action": "BUY", "symbol": "BTC/USDT", "price": 100.0, "qty": 10.0,
            })
        )
        fill = 100.0 * (1 + 0.0005)
        expected = fill * (1 + 0.001)
        assert result["price"] == pytest.approx(expected, rel=1e-9)

    def test_commission_affects_portfolio_capital(self, broker_portfolio):
        """Portfolio capital reflects commission after BUY."""
        portfolio, broker = broker_portfolio
        initial = portfolio.capital
        result = asyncio.run(
            broker.submit_order({
                "action": "BUY", "symbol": "BTC/USDT", "price": 100.0, "qty": 10.0,
            })
        )
        # update_portfolio uses trade["price"] which includes commission
        broker.update_portfolio(result)
        # fill_price = 100.05, effective_price = 100.05 * 1.001 ≈ 100.15005
        # capital change = 100.15005 * 10 = 1001.5005
        expected_capital = initial - result["price"] * 10.0
        assert portfolio.capital == pytest.approx(expected_capital, rel=1e-9)

    # -- Zero costs ---------------------------------------------------------

    def test_zero_costs_no_effect(self):
        """commission_pct=0, slippage_pct=0 → original price, no commission."""
        from royaltdn.execution.paper_broker import PaperBroker
        from royaltdn.risk.portfolio import Portfolio

        broker = PaperBroker(
            portfolio=Portfolio(100_000.0),
            commission_pct=0.0,
            slippage_pct=0.0,
        )
        result = asyncio.run(
            broker.submit_order({
                "action": "BUY", "symbol": "BTC/USDT", "price": 100.0, "qty": 1.0,
            })
        )
        assert result["fill_price"] == 100.0
        assert result["price"] == 100.0
        assert result["commission"] == 0.0
        assert result["slippage"] == 0.0


# ========================================================================
# EventEngine — run_batch
# ========================================================================


class MockBus:
    """Minimal MockBus for engine tests (same as test_engine.py)."""

    def __init__(self) -> None:
        self.emitted: list[dict] = []

    async def emit(self, event: dict) -> None:
        self.emitted.append(event)

    async def get(self) -> dict:
        raise NotImplementedError


def _build_engine_batch(return_signal: dict):
    """Helper: create an EventEngine + broker pair for batch tests.

    Returns:
        Tuple of (engine, broker, cell).
    """
    from royaltdn.core.engine import EventEngine
    from royaltdn.execution.paper_broker import PaperBroker
    from royaltdn.risk.portfolio import Portfolio

    clock = MagicMock()
    clock.now.return_value = "2025-01-01T00:00:00"
    bus = MockBus()
    portfolio = Portfolio(initial_capital=100_000.0)
    broker = PaperBroker(portfolio=portfolio, commission_pct=0.0, slippage_pct=0.0)

    rm = MagicMock()
    rm.approve.return_value = {"approved": True, **return_signal}

    engine = EventEngine(clock, bus, rm, broker)

    cell = MagicMock()
    cell.handle = AsyncMock(return_value=return_signal)
    cell.name = "test_cell"
    cell.state = "IDLE"
    engine.register(cell)

    return engine, broker, cell


class TestEngineRunBatch:
    """EventEngine.run_batch behaviour."""

    def test_run_batch_processes_single_event(self):
        """Single tick event → broker receives one trade."""
        signal = {
            "action": "BUY", "symbol": "BTCUSDT",
            "price": 50000.0, "qty": 0.01, "sizing": 0.01,
        }
        engine, broker, _ = _build_engine_batch(signal)

        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000.0}
        engine.run_batch([event])

        assert len(broker.trades) == 1
        assert broker.trades[0]["action"] == "BUY"
        assert broker.trades[0]["symbol"] == "BTCUSDT"

    def test_run_batch_skips_non_tick_events(self):
        """Events with type != 'tick' are skipped."""
        signal = {
            "action": "BUY", "symbol": "BTCUSDT",
            "price": 50000.0, "qty": 0.01, "sizing": 0.01,
        }
        engine, broker, _ = _build_engine_batch(signal)

        event = {"type": "signal", "symbol": "BTCUSDT", "price": 50000.0}
        engine.run_batch([event])

        assert len(broker.trades) == 0

    def test_run_batch_matches_process_event(self):
        """``run_batch`` and ``_process_event`` produce identical trades."""

        def make_engine():
            from royaltdn.core.engine import EventEngine
            from royaltdn.execution.paper_broker import PaperBroker
            from royaltdn.risk.portfolio import Portfolio

            clk = MagicMock()
            clk.now.return_value = "2025-01-01T00:00:00"
            bs = MockBus()
            pf = Portfolio(initial_capital=100_000.0)
            br = PaperBroker(portfolio=pf, commission_pct=0.0, slippage_pct=0.0)

            rsk = MagicMock()
            rsk.approve.return_value = {"approved": True, **signal}

            eng = EventEngine(clk, bs, rsk, br)

            c = MagicMock()
            c.handle = AsyncMock(return_value=signal)
            c.name = "test_cell"
            c.state = "IDLE"
            eng.register(c)

            return eng, br

        signal = {
            "action": "BUY", "symbol": "BTCUSDT",
            "price": 50000.0, "qty": 0.01, "sizing": 0.01,
        }
        event = {"type": "tick", "symbol": "BTCUSDT", "price": 50000.0}

        # Engine A — run_batch (sync)
        eng_a, broker_a = make_engine()
        eng_a.run_batch([event])

        # Engine B — _process_event (async via asyncio.run)
        eng_b, broker_b = make_engine()
        asyncio.run(eng_b._process_event(event))

        assert len(broker_a.trades) == len(broker_b.trades)
        for ta, tb in zip(broker_a.trades, broker_b.trades):
            assert ta["action"] == tb["action"]
            assert ta["symbol"] == tb["symbol"]
            assert ta["price"] == tb["price"]
            assert ta["qty"] == tb["qty"]

    def test_run_batch_multiple_events(self):
        """Multiple events are processed in sequence."""
        signal = {
            "action": "BUY", "symbol": "BTCUSDT",
            "price": 50000.0, "qty": 0.01, "sizing": 0.01,
        }
        engine, broker, cell = _build_engine_batch(signal)

        events = [
            {"type": "tick", "symbol": "BTCUSDT", "price": 50000.0},
            {"type": "tick", "symbol": "BTCUSDT", "price": 50100.0},
            {"type": "tick", "symbol": "BTCUSDT", "price": 50200.0},
        ]
        engine.run_batch(events)

        # Cell returns signal every time → 3 trades
        assert len(broker.trades) == 3


# ========================================================================
# Replayer
# ========================================================================


@pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
class TestReplayer:
    """Royaltdn.backtesting.replayer.Replayer behaviour."""

    @pytest.fixture
    def sample_ohlcv(self) -> pd.DataFrame:
        """5-row OHLCV DataFrame with 5-minute intervals."""
        import pandas as pd
        from datetime import datetime

        base = datetime(2025, 1, 1, 10, 0)
        return pd.DataFrame({
            "timestamp": [base, base + pd.Timedelta(minutes=5),
                          base + pd.Timedelta(minutes=10),
                          base + pd.Timedelta(minutes=15),
                          base + pd.Timedelta(minutes=20)],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [102.0, 103.0, 104.0, 105.0, 106.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [101.0, 102.0, 103.0, 104.0, 105.0],
            "volume": [1000.0, 1100.0, 1200.0, 1300.0, 1400.0],
        })

    def test_replayer_emits_correct_number_of_events(self, sample_ohlcv):
        """5 rows → 5 tick events."""
        from royaltdn.core.clock import SimClock
        from royaltdn.backtesting.replayer import Replayer

        clock = SimClock(sample_ohlcv["timestamp"].iloc[0])
        replayer = Replayer(sample_ohlcv, clock, "BTC/USDT")
        events = list(replayer)

        assert len(events) == 5

    def test_replayer_event_structure(self, sample_ohlcv):
        """Each event has correct type, symbol, price, and data."""
        from royaltdn.core.clock import SimClock
        from royaltdn.backtesting.replayer import Replayer

        clock = SimClock(sample_ohlcv["timestamp"].iloc[0])
        replayer = Replayer(sample_ohlcv, clock, "BTC/USDT")

        for i, event in enumerate(replayer):
            row = sample_ohlcv.iloc[i]
            assert event["type"] == "tick"
            assert event["symbol"] == "BTC/USDT"
            assert event["price"] == float(row["close"])
            assert event["data"]["open"] == float(row["open"])
            assert event["data"]["high"] == float(row["high"])
            assert event["data"]["low"] == float(row["low"])
            assert event["data"]["close"] == float(row["close"])
            assert event["data"]["volume"] == float(row["volume"])

    def test_replayer_advances_clock(self, sample_ohlcv):
        """Clock advances by correct timedelta after each row."""
        from datetime import timedelta
        from royaltdn.core.clock import SimClock
        from royaltdn.backtesting.replayer import Replayer

        start = sample_ohlcv["timestamp"].iloc[0]
        clock = SimClock(start)
        replayer = Replayer(sample_ohlcv, clock, "BTC/USDT")

        # Consume all events (this drives clock.advance)
        list(replayer)

        # After 5 rows with 5-min deltas + initial (no advance on first row):
        # 4 advances × 5 minutes = 20 minutes
        expected = start + timedelta(minutes=20)
        assert clock.now() == expected

    def test_replayer_clock_not_advanced_on_first_row(self, sample_ohlcv):
        """First row does NOT call clock.advance."""
        from royaltdn.core.clock import SimClock
        from royaltdn.backtesting.replayer import Replayer

        start = sample_ohlcv["timestamp"].iloc[0]
        clock = SimClock(start)
        replayer = Replayer(sample_ohlcv, clock, "BTC/USDT")

        next(iter(replayer))  # consume first event only

        # Clock should still be at start (no advance called)
        assert clock.now() == start


# ========================================================================
# Metrics
# ========================================================================


@pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
class TestMetrics:
    """royaltdn.backtesting.metrics.compute_metrics behaviour."""

    def test_metrics_known_pnls(self):
        """PnLs [100, 200, -50, 150, -30] → win_rate=0.6, PF=5.625."""
        from royaltdn.backtesting.metrics import compute_metrics

        trades = [
            {"pnl": 100}, {"pnl": 200}, {"pnl": -50},
            {"pnl": 150}, {"pnl": -30},
        ]
        # Minimal equity curve to enable Sharpe/Sortino/Calmar/MDD
        equity = [100_000.0, 100_370.0]  # 2 points is enough for returns
        metrics = compute_metrics(trades, equity_curve=equity)

        assert metrics["win_rate"] == pytest.approx(0.6, rel=1e-3)
        assert metrics["profit_factor"] == pytest.approx(5.625, rel=1e-3)
        assert metrics["expectancy"] == pytest.approx(74.0, rel=1e-3)

    def test_metrics_empty_trades(self):
        """Empty trades → all metrics 0.0, no crash."""
        from royaltdn.backtesting.metrics import compute_metrics

        metrics = compute_metrics([])
        for key, value in metrics.items():
            assert value == 0.0, f"Expected {key}=0.0, got {value}"

    def test_metrics_single_trade(self):
        """Single trade → curve-based metrics 0.0, win_rate=1.0."""
        from royaltdn.backtesting.metrics import compute_metrics

        trades = [{"pnl": 100}]
        metrics = compute_metrics(trades)

        assert metrics["sharpe"] == 0.0
        assert metrics["sortino"] == 0.0
        assert metrics["calmar"] == 0.0
        assert metrics["max_drawdown"] == 0.0
        assert metrics["win_rate"] == 1.0
        assert metrics["expectancy"] == 100.0

    def test_metrics_max_drawdown(self):
        """Equity [100000, 101000, 99000, 102000] → MDD ≈ 1.98%."""
        from royaltdn.backtesting.metrics import compute_metrics

        trades = [{"pnl": 1}]  # need at least 1 trade for non-zero return path
        equity = [100_000.0, 101_000.0, 99_000.0, 102_000.0]
        metrics = compute_metrics(trades, equity_curve=equity)

        # (101000 - 99000) / 101000 ≈ 0.0198
        assert metrics["max_drawdown"] == pytest.approx(0.0198, abs=1e-4)

    def test_metrics_no_equity_curve(self):
        """Without equity curve, curve-based metrics are 0.0."""
        from royaltdn.backtesting.metrics import compute_metrics

        trades = [{"pnl": 100}, {"pnl": -30}]
        metrics = compute_metrics(trades)

        assert metrics["sharpe"] == 0.0
        assert metrics["max_drawdown"] == 0.0
        assert metrics["win_rate"] == 0.5
        assert metrics["profit_factor"] == pytest.approx(100.0 / 30.0, rel=1e-3)

    def test_metrics_two_trades_sharpe_nonzero(self):
        """With ≥2 trades and equity curve, Sharpe is computed."""
        import numpy as np

        from royaltdn.backtesting.metrics import compute_metrics

        trades = [{"pnl": 100}, {"pnl": 50}]
        equity = [100_000.0, 100_100.0, 100_150.0]
        metrics = compute_metrics(trades, equity_curve=equity, rf=0.0)

        # We can't predict the exact Sharpe value without computing it,
        # but we can verify it's non-zero and finite
        assert metrics["sharpe"] != 0.0 or len(equity) < 2
        assert np.isfinite(metrics["sharpe"])

    def test_metrics_with_rf(self):
        """Risk-free rate reduces Sharpe and Sortino."""
        from royaltdn.backtesting.metrics import compute_metrics

        trades = [{"pnl": 100}, {"pnl": 50}]
        equity = [100_000.0, 100_100.0, 100_150.0]
        m0 = compute_metrics(trades, equity_curve=equity, rf=0.0)
        m1 = compute_metrics(trades, equity_curve=equity, rf=0.05)

        # Sharpe with rf=0.05 should be lower than with rf=0.0
        # (but they could be equal if mean excess is the same, which won't
        # happen at these returns)
        assert m1["sharpe"] <= m0["sharpe"] + 1e-9
        assert m1["sortino"] <= m0["sortino"] + 1e-9

    def test_metrics_all_losses(self):
        """All losing trades → win_rate=0, profit_factor=0."""
        from royaltdn.backtesting.metrics import compute_metrics

        trades = [{"pnl": -50}, {"pnl": -30}]
        metrics = compute_metrics(trades)

        assert metrics["win_rate"] == 0.0
        assert metrics["profit_factor"] == 0.0  # no gross profit
        assert metrics["expectancy"] == pytest.approx(-40.0, rel=1e-3)


# ========================================================================
# Backtester Orchestrator — Integration Tests (PR 2)
# ========================================================================


class _BuyHoldCell:
    """Test-only cell: enters on a chosen bar, exits on a later bar.

    Avoids the 20-bar warmup requirement of the real ``Cell`` and lets
    the test control exactly when entry/exit signals are produced.
    """

    def __init__(
        self,
        symbol: str,
        sizing: float = 0.5,
        entry_bar: int = 5,
        exit_bar: int = 26,
    ) -> None:
        self.name = "buy_hold_test"
        self.symbol = symbol
        self.state: str = "IDLE"
        self.sizing: float = sizing
        self.entry_price: float = 0.0
        self._entry_bar: int = entry_bar
        self._exit_bar: int = exit_bar
        self._bar_count: int = 0

    async def handle(self, event: dict) -> dict | None:
        """Return BUY on entry_bar, SELL on exit_bar, None otherwise."""
        if event.get("symbol") != self.symbol:
            return None
        self._bar_count += 1
        price = float(event.get("price", 0.0))

        if self.state == "IDLE" and self._bar_count == self._entry_bar:
            return {
                "action": "BUY",
                "symbol": self.symbol,
                "price": price,
                "sizing": self.sizing,
                "cell_name": self.name,
            }

        if self.state == "IN_POSITION" and self._bar_count == self._exit_bar:
            return {
                "action": "SELL",
                "symbol": self.symbol,
                "price": price,
                "sizing": self.sizing,
                "entry_price": self.entry_price,
                "cell_name": self.name,
            }

        return None

    def enter_position(self, price: float, direction: str = "long") -> None:
        """Called by EventEngine after risk approval."""
        self.state = "IN_POSITION" if direction == "long" else "IN_SHORT"
        self.entry_price = price

    def exit_position(self) -> None:
        """Called by EventEngine after successful exit execution."""
        self.state = "IDLE"
        self.entry_price = 0.0


def _trending_ohlcv(
    n: int = 30,
    start_price: float = 100.0,
    step: float = 0.5,
    symbol: str = "TEST/USDT",
) -> pd.DataFrame:
    """Build an OHLCV DataFrame with a linear price trend."""
    import pandas as pd
    from datetime import datetime

    base_ts = datetime(2025, 1, 1, 10, 0)
    prices = [start_price + i * step for i in range(n)]
    return pd.DataFrame({
        "timestamp": [base_ts + pd.Timedelta(hours=i) for i in range(n)],
        "open": prices,
        "high": [p + 1.0 for p in prices],
        "low": [p - 1.0 for p in prices],
        "close": prices,
        "volume": [1000.0] * n,
    })


@pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
class TestBacktesterOrchestration:
    """Integration tests for the backtester orchestrator (PR 2)."""

    # -- Empty OHLCV --------------------------------------------------------

    def test_empty_ohlcv_returns_zero_metrics(self):
        """``run()`` with empty DataFrame → zero metrics, no crash."""
        import pandas as pd

        from royaltdn.backtesting import run

        result = asyncio.run(run(
            strategy_config={"symbol": "TEST/USDT"},
            ohlcv=pd.DataFrame(),
            initial_capital=100_000.0,
        ))
        assert len(result.trades) == 0
        assert result.equity_curve == [100_000.0]
        for key, value in result.metrics.items():
            assert value == 0.0, f"Expected {key}=0.0, got {value}"

    # -- Dead strategy ------------------------------------------------------

    def test_dead_strategy_zero_trades(self):
        """Cell without entry/exit config → 0 trades, no crash."""
        from royaltdn.backtesting import run

        ohlcv = _trending_ohlcv(n=30)
        config: dict = {
            "name": "dead",
            "symbol": "TEST/USDT",
            # No entry / exit conditions → no signals
            "risk": {"sizing": 0.5, "max_positions": 10, "max_drawdown": 0.2},
        }

        result = asyncio.run(run(
            strategy_config=config,
            ohlcv=ohlcv,
            initial_capital=100_000.0,
        ))
        assert len(result.trades) == 0
        # equity_curve: initial + one per bar
        assert len(result.equity_curve) == 31  # 1 initial + 30 bars
        for key, value in result.metrics.items():
            assert value == 0.0, f"Expected {key}=0.0, got {value}"

    # -- Buy-and-hold (manual pipeline wire) --------------------------------

    def test_buy_and_hold_predictable_pnl(self):
        """Wire full pipeline with controlled cell → predictable PnL."""
        from royaltdn.core.clock import SimClock
        from royaltdn.core.bus import EventBus
        from royaltdn.core.engine import EventEngine
        from royaltdn.core.trade_tracker import TradeTracker
        from royaltdn.risk.portfolio import Portfolio
        from royaltdn.risk.manager import RiskManager
        from royaltdn.execution.paper_broker import PaperBroker
        from royaltdn.backtesting.replayer import Replayer

        ohlcv = _trending_ohlcv(n=30)
        clock = SimClock(ohlcv["timestamp"].iloc[0])
        bus = EventBus()
        portfolio = Portfolio(initial_capital=100_000.0)
        risk_mgr = RiskManager(
            portfolio=portfolio,
            max_positions=10,
            max_drawdown=0.2,
        )
        broker = PaperBroker(
            portfolio=portfolio,
            commission_pct=0.0,
            slippage_pct=0.0,
        )
        trade_tracker = TradeTracker(max_trades=99_999)
        engine = EventEngine(clock, bus, risk_mgr, broker, trade_tracker=trade_tracker)

        cell = _BuyHoldCell("TEST/USDT", sizing=0.5, entry_bar=5, exit_bar=26)
        engine.register(cell)

        replayer = Replayer(ohlcv, clock, "TEST/USDT")
        for event in replayer:
            engine.run_batch([event])

        # ── Assertions ─────────────────────────────────────────────────
        assert len(trade_tracker.trades) == 1, (
            f"Expected 1 closed trade, got {len(trade_tracker.trades)}"
        )
        trade = trade_tracker.trades[0]

        # _bar_count starts at 1 on the first event (0-indexed bar 0).
        # entry_bar=5 → bar index 4 → price = 100.0 + 4*0.5 = 102.0
        # exit_bar=26  → bar index 25 → price = 100.0 + 25*0.5 = 112.5
        entry_idx = 5 - 1
        exit_idx = 26 - 1
        expected_entry = 100.0 + entry_idx * 0.5
        expected_exit = 100.0 + exit_idx * 0.5
        expected_qty = (100_000.0 * 0.5) / expected_entry

        assert trade.symbol == "TEST/USDT"
        assert trade.direction == "long"
        assert trade.entry_price == pytest.approx(expected_entry, rel=1e-9)
        assert trade.exit_price == pytest.approx(expected_exit, rel=1e-9)
        assert trade.qty == pytest.approx(expected_qty, rel=1e-6)
        assert trade.pnl == pytest.approx(
            (expected_exit - expected_entry) * expected_qty, rel=1e-6,
        )

    def test_buy_and_hold_equity_curve_length(self):
        """Equity curve has (n_bars + 1) points after replay."""
        from royaltdn.core.clock import SimClock
        from royaltdn.core.bus import EventBus
        from royaltdn.core.engine import EventEngine
        from royaltdn.core.trade_tracker import TradeTracker
        from royaltdn.risk.portfolio import Portfolio
        from royaltdn.risk.manager import RiskManager
        from royaltdn.execution.paper_broker import PaperBroker
        from royaltdn.backtesting.replayer import Replayer

        ohlcv = _trending_ohlcv(n=30)
        clock = SimClock(ohlcv["timestamp"].iloc[0])
        bus = EventBus()
        portfolio = Portfolio(initial_capital=100_000.0)
        risk_mgr = RiskManager(portfolio, max_positions=10, max_drawdown=0.2)
        broker = PaperBroker(portfolio=portfolio)
        tracker = TradeTracker(max_trades=99_999)
        engine = EventEngine(clock, bus, risk_mgr, broker, trade_tracker=tracker)

        cell = _BuyHoldCell("TEST/USDT", sizing=0.5, entry_bar=5, exit_bar=26)
        engine.register(cell)

        equity_curve: list[float] = [portfolio.get_total_value()]
        replayer = Replayer(ohlcv, clock, "TEST/USDT")
        for event in replayer:
            engine.run_batch([event])
            equity_curve.append(portfolio.get_total_value())

        assert len(equity_curve) == 31, (
            f"Expected 31 points (initial + 30 bars), got {len(equity_curve)}"
        )
        # Equity should end higher than it started (trending up, buy+hold)
        assert equity_curve[-1] > equity_curve[0]


# ========================================================================
# Benchmark comparison
# ========================================================================


@pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
class TestBenchmarkComparison:
    """bt_metrics.compute_benchmark behaviour."""

    def test_benchmark_outperforms_when_strategy_wins(self):
        """Strategy with higher return → outperformed=True."""
        from royaltdn.backtesting.metrics import compute_benchmark

        # Strategy goes up 20 %, benchmark goes up 10 %
        strategy = [100.0, 120.0]
        benchmark = [100.0, 110.0]

        result = compute_benchmark(strategy, benchmark)
        assert result["strategy_outperformed"] is True
        assert result["strategy_return"] == pytest.approx(0.20, rel=1e-3)
        assert result["benchmark_return"] == pytest.approx(0.10, rel=1e-3)

    def test_benchmark_underperforms_when_benchmark_wins(self):
        """Benchmark with higher return → outperformed=False."""
        from royaltdn.backtesting.metrics import compute_benchmark

        strategy = [100.0, 105.0]
        benchmark = [100.0, 120.0]

        result = compute_benchmark(strategy, benchmark)
        assert result["strategy_outperformed"] is False

    def test_benchmark_empty_equity(self):
        """Empty/single-point equity curves → zero result."""
        from royaltdn.backtesting.metrics import compute_benchmark

        result = compute_benchmark([], [])
        assert result["alpha"] == 0.0
        assert result["strategy_outperformed"] is False

        result = compute_benchmark([100.0], [100.0])
        assert result["alpha"] == 0.0

    def test_benchmark_beta_computed(self):
        """Beta is a finite float when both curves have movement."""
        from royaltdn.backtesting.metrics import compute_benchmark

        strategy = [100.0, 101.0, 102.0, 103.0, 104.0]
        benchmark = [100.0, 100.5, 101.0, 101.5, 102.0]

        result = compute_benchmark(strategy, benchmark)
        assert isinstance(result["beta"], float)
        assert result["beta"] != 0.0

    def test_benchmark_alpha_direction(self):
        """Alpha is positive when strategy beats benchmark."""
        from royaltdn.backtesting.metrics import compute_benchmark

        # Strategy: flat
        # Benchmark: down
        strategy = [100.0, 100.0, 100.0]
        benchmark = [100.0, 95.0, 90.0]

        result = compute_benchmark(strategy, benchmark)
        assert result["alpha"] > 0

    def test_benchmark_negative_alpha(self):
        """Alpha is negative when strategy lags benchmark."""
        from royaltdn.backtesting.metrics import compute_benchmark

        # Strategy: down
        # Benchmark: flat
        strategy = [100.0, 95.0, 90.0]
        benchmark = [100.0, 100.0, 100.0]

        result = compute_benchmark(strategy, benchmark)
        assert result["alpha"] < 0

    def test_benchmark_mismatched_lengths_truncated(self):
        """Unequal lengths → truncated to shortest."""
        from royaltdn.backtesting.metrics import compute_benchmark

        strategy = [100.0, 110.0, 120.0]
        benchmark = [100.0, 105.0]

        result = compute_benchmark(strategy, benchmark)
        # Only first 2 points of strategy used → 10 % return, benchmark 5 %
        assert result["strategy_return"] == pytest.approx(0.10, rel=1e-3)
        assert result["benchmark_return"] == pytest.approx(0.05, rel=1e-3)
        assert result["strategy_outperformed"] is True


# ========================================================================
# Overfitting detection (Monte Carlo)
# ========================================================================


@pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
class TestOverfittingDetection:
    """bt_metrics.detect_overfitting behaviour."""

    def test_overfitting_few_trades_returns_empty(self):
        """< 3 trades → empty result, no crash."""
        from royaltdn.backtesting.metrics import detect_overfitting

        result = detect_overfitting([100.0], n_shuffles=10)
        assert result["overfit_flag"] is False
        assert result["actual_sharpe"] == 0.0

        result = detect_overfitting([], n_shuffles=10)
        assert result["overfit_flag"] is False

    def test_overfitting_returns_expected_keys(self):
        """detect_overfitting returns all expected keys."""
        from royaltdn.backtesting.metrics import detect_overfitting

        pnls = [100.0, -20.0, 50.0, -10.0, 30.0]
        result = detect_overfitting(pnls, n_shuffles=50, seed=42)

        expected_keys = {
            "actual_sharpe", "shuffled_mean_sharpe", "shuffled_std_sharpe",
            "shuffled_p50", "shuffled_p95", "actual_percentile",
            "overfit_flag",
        }
        assert set(result.keys()) == expected_keys

    def test_overfitting_actual_sharpe_finite(self):
        """Actual Sharpe is a finite float."""
        from royaltdn.backtesting.metrics import detect_overfitting

        pnls = [100.0, -20.0, 50.0, -10.0, 30.0, 25.0]
        result = detect_overfitting(pnls, n_shuffles=50, seed=42)
        assert isinstance(result["actual_sharpe"], float)

    def test_overfitting_percentile_in_range(self):
        """Percentile is between 0 and 100."""
        import numpy as np

        from royaltdn.backtesting.metrics import detect_overfitting

        pnls = [100.0, -20.0, 50.0, -10.0, 30.0, 25.0, -5.0, 15.0]
        result = detect_overfitting(pnls, n_shuffles=50, seed=42)
        assert 0 <= result["actual_percentile"] <= 100

    def test_overfitting_seed_determinism(self):
        """Same seed → same result."""
        from royaltdn.backtesting.metrics import detect_overfitting

        pnls = [100.0, -20.0, 50.0, -10.0, 30.0]
        r1 = detect_overfitting(pnls, n_shuffles=50, seed=42)
        r2 = detect_overfitting(pnls, n_shuffles=50, seed=42)
        assert r1["actual_percentile"] == r2["actual_percentile"]
        assert r1["shuffled_mean_sharpe"] == r2["shuffled_mean_sharpe"]


# ========================================================================
# Survivorship bias
# ========================================================================


class TestSurvivorshipBias:
    """bt_metrics.check_survivorship_bias behaviour."""

    def test_known_symbol_after_listing_no_warning(self):
        """Symbol with data after listing date → no warnings."""
        from royaltdn.backtesting.metrics import check_survivorship_bias

        warnings = check_survivorship_bias(["SOLUSDT"], "2022-01-01")
        assert len(warnings) == 0

    def test_known_symbol_before_listing_warning(self):
        """Symbol with data before listing date → warning."""
        from royaltdn.backtesting.metrics import check_survivorship_bias

        warnings = check_survivorship_bias(["SOLUSDT"], "2019-06-01")
        assert len(warnings) == 1
        assert "SOLUSDT" in warnings[0]
        assert "before listing" in warnings[0].lower()

    def test_unknown_symbol_no_warning(self):
        """Unknown symbol (not in registry) → no warning."""
        from royaltdn.backtesting.metrics import check_survivorship_bias

        warnings = check_survivorship_bias(["XXXUSDT"], "2018-01-01")
        assert len(warnings) == 0

    def test_multiple_symbols_one_warning(self):
        """Multiple symbols where only one is pre-listing."""
        from royaltdn.backtesting.metrics import check_survivorship_bias

        warnings = check_survivorship_bias(["BTCUSDT", "ARBUSDT"], "2022-01-01")
        assert len(warnings) == 1
        assert "ARBUSDT" in warnings[0]

    def test_clean_symbol_with_slash(self):
        """Symbol with '/' separator is cleaned before checking."""
        from royaltdn.backtesting.metrics import check_survivorship_bias

        warnings = check_survivorship_bias(["SOL/USDT"], "2019-06-01")
        assert len(warnings) == 1
        assert "SOLUSDT" in warnings[0]

    def test_invalid_date_returns_warning(self):
        """Unparseable date → error warning."""
        from royaltdn.backtesting.metrics import check_survivorship_bias

        warnings = check_survivorship_bias(["BTCUSDT"], "not-a-date")
        assert len(warnings) == 1


# ========================================================================
# BacktestResult new fields
# ========================================================================


class TestBacktestResultEnhanced:
    """BacktestResult dataclass with new benchmark/overfitting fields."""

    def test_backtest_result_defaults(self):
        """New fields default to zero/false/empty."""
        from royaltdn.backtesting.backtester import BacktestResult

        result = BacktestResult(
            trades=[],
            equity_curve=[100_000.0],
            metrics={},
        )

        assert result.benchmark_alpha == 0.0
        assert result.benchmark_beta == 0.0
        assert result.benchmark_return == 0.0
        assert result.strategy_return == 0.0
        assert result.strategy_outperformed is False
        assert result.overfitting_sharpe_percentile == 0.0
        assert result.overfitting_flag is False
        assert result.survivorship_warnings == []

    def test_backtest_result_custom_values(self):
        """New fields store custom values correctly."""
        from royaltdn.backtesting.backtester import BacktestResult

        result = BacktestResult(
            trades=[],
            equity_curve=[100_000.0],
            metrics={},
            benchmark_alpha=0.05,
            benchmark_beta=0.8,
            benchmark_return=0.10,
            strategy_return=0.15,
            strategy_outperformed=True,
            overfitting_sharpe_percentile=95.0,
            overfitting_flag=True,
            survivorship_warnings=["SOLUSDT pre-listing data"],
        )

        assert result.benchmark_alpha == 0.05
        assert result.benchmark_beta == 0.8
        assert result.strategy_outperformed is True
        assert result.overfitting_flag is True
        assert len(result.survivorship_warnings) == 1


# ========================================================================
# Benchmark equity curve helper
# ========================================================================


@pytest.mark.skipif(not _HAS_NUMPY, reason=NUMPY_SKIP_REASON)
class TestBenchmarkEquity:
    """_compute_benchmark_equity helper behaviour."""

    def test_benchmark_equity_simple(self):
        """Buy-and-hold at first close → proportional equity."""
        import pandas as pd

        from royaltdn.backtesting.backtester import _compute_benchmark_equity

        df = pd.DataFrame({"close": [100.0, 110.0, 121.0]})
        curve = _compute_benchmark_equity(df, initial_capital=1000.0)

        assert curve[0] == 1000.0
        # qty = 1000 / 100 = 10
        # bar1: 10 * 110 = 1100
        # bar2: 10 * 121 = 1210
        assert curve[1] == pytest.approx(1100.0, rel=1e-9)
        assert curve[2] == pytest.approx(1210.0, rel=1e-9)

    def test_benchmark_equity_empty(self):
        """Empty DataFrame → just initial capital."""
        import pandas as pd

        from royaltdn.backtesting.backtester import _compute_benchmark_equity

        df = pd.DataFrame({"close": []})
        curve = _compute_benchmark_equity(df, initial_capital=1000.0)
        assert curve == [1000.0]

    def test_benchmark_equity_zero_entry_price(self):
        """Entry price of 0 → flat equity curve."""
        import pandas as pd

        from royaltdn.backtesting.backtester import _compute_benchmark_equity

        df = pd.DataFrame({"close": [0.0, 10.0]})
        curve = _compute_benchmark_equity(df, initial_capital=1000.0)
        # All entries should be initial_capital
        assert all(v == 1000.0 for v in curve)


# ========================================================================
# Bars per year mapping
# ========================================================================


class TestBarsPerYear:
    """bt_metrics.bars_per_year behaviour."""

    def test_bars_per_year_default(self):
        """Default timeframe '1d' → 365 bars/year (crypto 24/7)."""
        from royaltdn.backtesting.metrics import bars_per_year

        assert bars_per_year() == 365

    def test_bars_per_year_hourly(self):
        """1h → 8760."""
        from royaltdn.backtesting.metrics import bars_per_year

        assert bars_per_year("1h") == 8760

    def test_bars_per_year_30m(self):
        """30m → 17520."""
        from royaltdn.backtesting.metrics import bars_per_year

        assert bars_per_year("30m") == 17520

    def test_bars_per_year_unknown_timeframe(self):
        """Unknown timeframe → falls back to 365."""
        from royaltdn.backtesting.metrics import bars_per_year

        assert bars_per_year("unknown") == 365
