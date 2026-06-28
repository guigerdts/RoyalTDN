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

from dataclasses import dataclass, field
from typing import Any

from royaltdn.backtesting import metrics as bt_metrics

# pandas is imported lazily inside functions that need it (it depends on
# numpy, which may be broken on some platforms).


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
        benchmark_alpha: Excess return over benchmark (annualised).
            ``0.0`` when no benchmark comparison was run.
        benchmark_beta: Correlation of strategy returns to benchmark
            returns.  ``0.0`` when no benchmark comparison was run.
        benchmark_return: Total return of the benchmark buy-and-hold.
            ``0.0`` when no benchmark comparison was run.
        strategy_return: Total return of the strategy.  ``0.0`` when
            no benchmark comparison was run.
        strategy_outperformed: ``True`` if strategy return exceeds
            benchmark return.
        overfitting_sharpe_percentile: Percentile of the actual Sharpe
            within the shuffled (Monte Carlo) distribution.
            ``0.0`` when overfitting detection was not run.
        overfitting_flag: ``True`` if the actual Sharpe is below the
            95th percentile of shuffled Sharpes (likely overfit).
        survivorship_warnings: List of survivorship bias warning
            strings.  Empty when no warnings triggered.
    """

    trades: list[dict[str, Any]]
    equity_curve: list[float]
    metrics: dict[str, float]

    # Benchmark comparison
    benchmark_alpha: float = 0.0
    benchmark_beta: float = 0.0
    benchmark_return: float = 0.0
    strategy_return: float = 0.0
    strategy_outperformed: bool = False

    # Overfitting detection
    overfitting_sharpe_percentile: float = 0.0
    overfitting_flag: bool = False

    # Survivorship bias
    survivorship_warnings: list[str] = field(default_factory=list)


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
    initial_capital = float(strategy_config.get("initial_capital", initial_capital))
    symbol: str = strategy_config.get("symbol", "")
    risk_cfg: dict = strategy_config.get("risk", {})
    max_positions: int = int(risk_cfg.get("max_positions", 10))
    max_drawdown: float = float(risk_cfg.get("max_drawdown", 0.03))
    timeframe: str = str(strategy_config.get("timeframe", "1d"))

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
        await engine._process_event(event)
        equity_curve.append(portfolio.get_total_value())

    # ── Extract results ────────────────────────────────────────────────
    raw_trades: list[dict[str, Any]] = [
        asdict(t) for t in trade_tracker.trades
    ]

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
        normalized_trades, equity_curve=equity_curve, timeframe=timeframe,
    )

    return BacktestResult(
        trades=normalized_trades,
        equity_curve=equity_curve,
        metrics=result_metrics,
    )


async def run_with_benchmark(
    strategy_config: dict[str, Any],
    ohlcv: pd.DataFrame,
    benchmark_ohlcv: pd.DataFrame,
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> BacktestResult:
    """Run a backtest with benchmark comparison and overfitting detection.

    Downloads BTCUSDT (or custom) benchmark data for the same period,
    runs the strategy backtest, then enriches the result with benchmark
    metrics and overfitting analysis.

    Args:
        strategy_config: Cell configuration dict (see :func:`run`).
        ohlcv: Strategy OHLCV DataFrame.
        benchmark_ohlcv: Benchmark OHLCV DataFrame (e.g. BTCUSDT) for
            the same period.  Must have the same columns as *ohlcv*.
        initial_capital: Starting capital.
        commission: Commission fraction.
        slippage: Slippage fraction.

    Returns:
        Enhanced ``BacktestResult`` with benchmark comparison and
        overfitting fields populated.
    """
    timeframe: str = str(strategy_config.get("timeframe", "1d"))

    # Run the core backtest
    result = await run(
        strategy_config=strategy_config,
        ohlcv=ohlcv,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
    )

    # Build benchmark equity curve (buy-and-hold BTC)
    if not benchmark_ohlcv.empty and len(result.equity_curve) >= 2:
        # Align lengths — benchmark may differ from strategy if one
        # has fewer bars (e.g. different download timings).
        n_bars = min(len(benchmark_ohlcv), len(ohlcv))
        if n_bars >= 2:
            bench_equity = _compute_benchmark_equity(
                benchmark_ohlcv.iloc[:n_bars],
                initial_capital,
            )
            # Strategy equity curve has (n_bars + 1) points (initial + per bar)
            # so we take the first (n_bars + 1) elements.
            strat_curve = result.equity_curve[: n_bars + 1]

            bench_result = bt_metrics.compute_benchmark(
                strat_curve, bench_equity, timeframe=timeframe,
            )
            result.benchmark_alpha = bench_result["alpha"]
            result.benchmark_beta = bench_result["beta"]
            result.benchmark_return = bench_result["benchmark_return"]
            result.strategy_return = bench_result["strategy_return"]
            result.strategy_outperformed = bench_result["strategy_outperformed"]

    # Overfitting detection on trade PnLs
    trade_pnls = [t.get("pnl", 0.0) for t in result.trades]
    if len(trade_pnls) >= 3:
        of_result = bt_metrics.detect_overfitting(trade_pnls)
        result.overfitting_sharpe_percentile = of_result["actual_percentile"]
        result.overfitting_flag = of_result["overfit_flag"]

    # Survivorship bias warning
    symbols: list[str] = strategy_config.get("symbols", [])
    single_sym = strategy_config.get("symbol", "")
    if single_sym and single_sym not in symbols:
        symbols.append(single_sym)
    if symbols and not ohlcv.empty:
        start_date = str(ohlcv["timestamp"].iloc[0].date())
        warnings = bt_metrics.check_survivorship_bias(symbols, start_date)
        result.survivorship_warnings = warnings

    return result


# ── Internal helpers ────────────────────────────────────────────────────────


def _compute_benchmark_equity(
    benchmark_ohlcv: pd.DataFrame,
    initial_capital: float = 100_000.0,
) -> list[float]:
    """Build a buy-and-hold equity curve from benchmark OHLCV.

    Buys at the first bar's close, holds until the last bar's close.
    No commissions or slippage (pure spot buy-and-hold).

    Args:
        benchmark_ohlcv: OHLCV DataFrame with at least ``close``.
        initial_capital: Starting capital.

    Returns:
        List of portfolio values starting with *initial_capital*
        followed by mark-to-market after each bar.
    """
    closes = benchmark_ohlcv["close"].values
    if len(closes) == 0:
        return [initial_capital]

    entry_price = float(closes[0])
    if entry_price == 0.0:
        return [initial_capital] * (len(closes) + 1)

    qty = initial_capital / entry_price
    curve = [initial_capital]
    for close in closes:
        curve.append(qty * float(close))
    return curve


# Late import to break circular dependency
from royaltdn.backtesting.replayer import Replayer  # noqa: E402
