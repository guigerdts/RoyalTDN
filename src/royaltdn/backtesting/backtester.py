"""Backtesting orchestrator for the CellMesh architecture.

Wires ``SimClock`` → ``EventBus`` → ``Portfolio`` → ``RiskManager`` →
``PaperBroker`` → ``Cell`` → ``EventEngine``, replays historical OHLCV
data through the identical production pipeline, and collects performance
metrics.

Usage::

    result = asyncio.run(
        run(config, ohlcv, initial_capital=100_000.0)
    )
    print(result.metrics["sharpe"])
    print(result.trades)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from royaltdn.backtesting import metrics as bt_metrics
from royaltdn.backtesting.replayer import Replayer


@dataclass
class BacktestResult:
    """Result of a single backtest run.

    Attributes:
        trades: List of closed trade dicts (converted from ``Trade``
            dataclass via ``dataclasses.asdict``).  Each dict contains
            at least ``pnl``, ``symbol``, ``direction``, ``entry_price``,
            ``exit_price``, ``qty``.
        equity_curve: Portfolio value recorded after each bar.  The
            first element is ``initial_capital`` (pre-trade), and each
            subsequent element is the mark-to-market value after that
            bar's events were processed.
        metrics: Dict with keys ``sharpe``, ``sortino``, ``calmar``,
            ``max_drawdown``, ``win_rate``, ``profit_factor``,
            ``expectancy``.  Metrics that cannot be computed are ``0.0``.
    """

    trades: list[dict[str, Any]]
    equity_curve: list[float]
    metrics: dict[str, float]


async def run(
    strategy_config: dict[str, Any],
    ohlcv: pd.DataFrame,
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> BacktestResult:
    """Run a full backtest through the production pipeline.

    Creates a fresh pipeline for each call — every component is
    instantiated from scratch so there is no state leakage between
    runs.

    Args:
        strategy_config: Cell configuration dict. Must contain at least
            ``"symbol"``. May also contain ``"risk"`` (``max_positions``,
            ``max_drawdown``) and cell-specific fields such as ``entry``,
            ``exit``, ``name``, etc.  The dict is passed directly to the
            ``Cell`` constructor.
        ohlcv: OHLCV DataFrame with at least ``timestamp``, ``open``,
            ``high``, ``low``, ``close``, ``volume`` columns.  The
            ``timestamp`` column must be parseable by pandas (datetime,
            ``pd.Timestamp``, or ISO string).
        initial_capital: Starting capital in quote currency.  Defaults
            to ``100_000.0``.
        commission: Commission as a fraction of notional value
            (e.g. ``0.001`` = 0.1 %).  Deducted from capital on every
            fill.  Defaults to ``0.001``.
        slippage: Slippage as a fraction of the signal price
            (e.g. ``0.0005`` = 0.05 %).  Applied asymmetrically:
            BUY fills worsen, SELL/SHORT fills improve.  Defaults to
            ``0.0005``.

    Returns:
        ``BacktestResult`` containing the closed trades, per-bar equity
        curve, and computed performance metrics.

    Raises:
        IndexError: If *ohlcv* is non-empty but lacks a ``timestamp``
            column at index 0.
    """
    from dataclasses import asdict

    from royaltdn.cells.base import Cell
    from royaltdn.core.bus import EventBus
    from royaltdn.core.clock import SimClock
    from royaltdn.core.engine import EventEngine
    from royaltdn.core.trade_tracker import TradeTracker
    from royaltdn.execution.paper_broker import PaperBroker
    from royaltdn.inference.engine import InferenceEngine
    from royaltdn.risk.manager import RiskManager
    from royaltdn.risk.portfolio import Portfolio

    # ── Empty OHLCV guard ──────────────────────────────────────────────
    if ohlcv is None or ohlcv.empty:
        return BacktestResult(
            trades=[],
            equity_curve=[float(initial_capital)],
            metrics=bt_metrics.compute_metrics([], equity_curve=None),
        )

    # ── Extract settings from config dict ──────────────────────────────
    # initial_capital can come from the config dict or the explicit param;
    # the config value acts as a convenience override for callers that
    # pass everything in one dict (matching the tasks.md convention).
    initial_capital = float(strategy_config.get("initial_capital", initial_capital))
    symbol: str = strategy_config.get("symbol", "")
    risk_cfg: dict = strategy_config.get("risk", {})
    max_positions: int = int(risk_cfg.get("max_positions", 10))
    max_drawdown: float = float(risk_cfg.get("max_drawdown", 0.03))

    # ── Wire the backtesting pipeline ──────────────────────────────────
    clock = SimClock(ohlcv["timestamp"].iloc[0])
    bus = EventBus()
    portfolio = Portfolio(initial_capital=float(initial_capital))
    risk_manager = RiskManager(
        portfolio=portfolio,
        max_positions=max_positions,
        max_drawdown=max_drawdown,
    )
    broker = PaperBroker(
        portfolio=portfolio,
        commission_pct=float(commission),
        slippage_pct=float(slippage),
    )
    inference = InferenceEngine()
    cell = Cell(strategy_config, inference_engine=inference)
    # High trade limit for backtesting (5+ years of 1 h data can generate
    # thousands of trades).  TradeTracker interprets max_trades as a ring-
    # buffer cap — 0 would evict every trade, so we use a generous bound.
    trade_tracker = TradeTracker(max_trades=99_999)
    engine = EventEngine(
        clock=clock,
        bus=bus,
        risk_manager=risk_manager,
        execution_broker=broker,
        trade_tracker=trade_tracker,
    )
    engine.register(cell)

    # ── Replay loop ────────────────────────────────────────────────────
    equity_curve: list[float] = [portfolio.get_total_value()]
    replayer = Replayer(ohlcv, clock, symbol)

    for event in replayer:
        # Direct async call avoids nested asyncio.run() — the backtester
        # is already running inside an event loop, so calling the sync
        # run_batch() would trigger RuntimeError.  _process_event is the
        # same pipeline that run_batch wraps, just without the sync shim.
        await engine._process_event(event)
        equity_curve.append(portfolio.get_total_value())

    # ── Extract results ────────────────────────────────────────────────
    raw_trades: list[dict[str, Any]] = [
        asdict(t) for t in trade_tracker.trades
    ]

    # Normalize trades to match the old ``simulate()`` format used by
    # ``scripts/optimize.py``: ``symbol``, ``action`` (BUY/SELL),
    # ``entry_price``, ``exit_price``, ``qty``, ``pnl``, ``capital``.
    # ``capital`` is approximated as ``initial_capital + cumulative PnL``
    # up to that trade, which matches the portfolio.capital pattern from
    # the old inline backtest loop.
    cumulative_capital = float(initial_capital)
    normalized_trades: list[dict[str, Any]] = []
    for t in raw_trades:
        cumulative_capital += t["pnl"]
        normalized_trades.append({
            "symbol": t["symbol"],
            "action": "SELL" if t.get("direction", "long") == "long" else "BUY",
            "entry_price": t["entry_price"],
            "exit_price": t["exit_price"],
            "qty": t["qty"],
            "pnl": round(t["pnl"], 2),
            "capital": round(cumulative_capital, 2),
        })

    result_metrics = bt_metrics.compute_metrics(
        normalized_trades, equity_curve=equity_curve,
    )

    return BacktestResult(
        trades=normalized_trades,
        equity_curve=equity_curve,
        metrics=result_metrics,
    )
