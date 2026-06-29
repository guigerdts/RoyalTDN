#!/usr/bin/env python3
"""CLI script to run a professional backtest with benchmark comparison.

Downloads historical OHLCV for a symbol + timeframe + lookback days,
downloads BTCUSDT as the benchmark, runs the strategy through the
full backtesting pipeline, and prints a Rich-formatted report.

Usage::

    python -m royaltdn.scripts.run_backtest --symbol BTCUSDT --strategy scalping_momentum --timeframe 30m --days 90
    python -m royaltdn.scripts.run_backtest --symbol SOLUSDT --strategy scalping_breakout --timeframe 1h --days 180 --commission 0.001 --slippage 0.0005

Crypto-only: benchmarks are always BTCUSDT.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# Ensure project root is on sys.path so that
# ``from royaltdn.backtesting import ...`` works regardless of where
# the script is invoked from.
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger.remove()
logger.add(sys.stderr, level="WARNING")


# ---------------------------------------------------------------------------
# Rich console (16-color ANSI only — no 24-bit hex)
# ---------------------------------------------------------------------------

def _make_console() -> Any:
    """Create a Rich Console configured for 16-color ANSI only."""
    from rich.console import Console
    return Console(color_system="standard")


def _print_header(console: Any, text: str) -> None:
    """Print a styled section header via Rich or plain ASCII."""
    if console:
        console.rule(f"[bold cyan]{text}[/]", style="cyan")
    else:
        print(f"\n{'=' * 60}")
        print(f"  {text}")
        print(f"{'=' * 60}")


def _print_warning(console: Any, text: str) -> None:
    """Print a styled warning message."""
    if console:
        console.print(f"[bold yellow]WARNING:[/] {text}")
    else:
        print(f"WARNING: {text}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the backtest runner."""
    parser = argparse.ArgumentParser(
        description="Run a professional crypto backtest with BTC benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m royaltdn.scripts.run_backtest "
            "--symbol BTCUSDT --strategy scalping_momentum --timeframe 30m\n"
            "  python -m royaltdn.scripts.run_backtest "
            "--symbol SOLUSDT --strategy scalping_breakout --timeframe 1h --days 180\n"
        ),
    )
    parser.add_argument(
        "--symbol", type=str, required=True,
        help="Trading symbol (e.g. BTCUSDT, SOLUSDT)",
    )
    parser.add_argument(
        "--strategy", type=str, required=True,
        help="Strategy name from YAML templates (e.g. scalping_momentum)",
    )
    parser.add_argument(
        "--timeframe", type=str, default="30m",
        choices=["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"],
        help="Kline interval (default: 30m)",
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="Lookback period in days (default: 90)",
    )
    parser.add_argument(
        "--initial-capital", type=float, default=100_000.0,
        help="Starting capital in USDT (default: 100000)",
    )
    parser.add_argument(
        "--commission", type=float, default=0.001,
        help="Commission fraction (default: 0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--slippage", type=float, default=0.0005,
        help="Slippage fraction (default: 0.0005 = 0.05%%)",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Skip saving results to logs/backtest_results.json",
    )
    parser.add_argument(
        "--force-download", action="store_true",
        help="Force re-download of historical data (ignore cache)",
    )
    parser.add_argument(
        "--max-drawdown", type=float, default=0.5,
        help="Maximum drawdown fraction for risk manager (default: 0.5 = 50%%)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _download_ohlcv_range(
    symbol: str,
    timeframe: str,
    days: int,
    force_download: bool = False,
) -> "pd.DataFrame":
    """Download OHLCV data for the given symbol and time range.

    Args:
        symbol: Trading pair (e.g. ``"BTCUSDT"``).
        timeframe: Kline interval.
        days: Number of days of historical data.
        force_download: Ignore cache.

    Returns:
        OHLCV DataFrame with standard columns.
    """
    import pandas as pd

    from royaltdn.data.historical import download_2y_ohlcv, read_cache, write_cache

    df = None
    if not force_download:
        df = read_cache(symbol, timeframe, max_age_hours=24)

    if df is None:
        df = download_2y_ohlcv(symbol, timeframe)
        write_cache(symbol, timeframe, df)

    # Trim to the requested lookback period
    if not df.empty and days > 0:
        cutoff = df["timestamp"].max() - pd.Timedelta(days=days)
        df = df[df["timestamp"] >= cutoff].reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Strategy loading
# ---------------------------------------------------------------------------

def _load_strategy_config(strategy_name: str, symbol: str) -> dict[str, Any] | None:
    """Load a single strategy config from YAML templates by name.

    Args:
        strategy_name: Name field in the YAML (e.g. ``"scalping_momentum"``).
        symbol: Override the symbol in the config (user-supplied).

    Returns:
        Strategy config dict with ``symbol`` set to *symbol*, or None
        if not found.
    """
    from yaml import safe_load_all

    templates_dir = _PROJECT_ROOT / "cells" / "templates"
    for yaml_path in sorted(templates_dir.glob("*.yaml")):
        try:
            with open(yaml_path) as f:
                docs = list(safe_load_all(f))
        except Exception:
            continue

        for item in docs:
            if isinstance(item, dict) and item.get("name") == strategy_name:
                config = dict(item)
                config["symbol"] = symbol
                return config

    return None


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _format_pct(value: float) -> str:
    """Format a ratio as a percentage string."""
    return f"{value * 100:.2f}%"


def _print_result_report(
    console: Any,
    result: Any,
    symbol: str,
    strategy_name: str,
    timeframe: str,
    days: int,
    duration_s: float,
) -> None:
    """Print a Rich-formatted backtest report."""
    metrics = result.metrics

    _print_header(console, "Backtest Results")

    # ── Summary section ────────────────────────────────────────────────
    if console:
        from rich.table import Table
        from rich.text import Text

        table = Table(box=None)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Strategy", strategy_name)
        table.add_row("Symbol", symbol)
        table.add_row("Timeframe", timeframe)
        table.add_row("Period", f"{days} days")
        table.add_row("Duration", f"{duration_s:.2f}s")
        console.print(table)
        console.print()
    else:
        print(f"  Strategy: {strategy_name}")
        print(f"  Symbol: {symbol}  Timeframe: {timeframe}")
        print(f"  Period: {days}d  Duration: {duration_s:.2f}s")
        print()

    # ── Performance metrics ────────────────────────────────────────────
    _print_header(console, "Performance Metrics")

    if console:
        perf = Table(box=None)
        perf.add_column("Metric", style="cyan")
        perf.add_column("Value", justify="right")

        sharpe = f"{metrics.get('sharpe', 0):.2f}"
        sortino = f"{metrics.get('sortino', 0):.2f}"
        calmar = f"{metrics.get('calmar', 0):.2f}"
        mdd = _format_pct(metrics.get("max_drawdown", 0))
        wr = _format_pct(metrics.get("win_rate", 0))
        pf = f"{metrics.get('profit_factor', 0):.2f}"
        exp = f"{metrics.get('expectancy', 0):.2f}"
        trades = len(result.trades)

        sharpe_style = "bold green" if metrics.get("sharpe", 0) > 1.0 else (
            "bold yellow" if metrics.get("sharpe", 0) > 0.0 else "bold red"
        )
        mdd_style = "green" if metrics.get("max_drawdown", 0) < 0.1 else (
            "yellow" if metrics.get("max_drawdown", 0) < 0.2 else "red"
        )

        perf.add_row("Sharpe", Text(sharpe, style=sharpe_style))
        perf.add_row("Sortino", sortino)
        perf.add_row("Calmar", calmar)
        perf.add_row("Max Drawdown", Text(mdd, style=mdd_style))
        perf.add_row("Win Rate", wr)
        perf.add_row("Profit Factor", pf)
        perf.add_row("Expectancy", exp)
        perf.add_row("Total Trades", str(trades))
        perf.add_row("Strategy Return", _format_pct(
            result.strategy_return if hasattr(result, "strategy_return") else 0.0,
        ))
        console.print(perf)
    else:
        print(f"  Sharpe: {metrics.get('sharpe', 0):.2f}")
        print(f"  Sortino: {metrics.get('sortino', 0):.2f}")
        print(f"  Calmar: {metrics.get('calmar', 0):.2f}")
        print(f"  Max DD: {_format_pct(metrics.get('max_drawdown', 0))}")
        print(f"  Win Rate: {_format_pct(metrics.get('win_rate', 0))}")
        print(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        print(f"  Expectancy: {metrics.get('expectancy', 0):.2f}")
        print(f"  Total Trades: {trades}")

    print()

    # ── Benchmark comparison ──────────────────────────────────────────
    _print_header(console, "Benchmark Comparison (BTCUSDT)")

    if console:
        bench = Table(box=None)
        bench.add_column("Metric", style="cyan")
        bench.add_column("Value", justify="right")

        alpha = f"{result.benchmark_alpha:.4f}"
        beta = f"{result.benchmark_beta:.2f}"
        bench_ret = _format_pct(result.benchmark_return)
        strat_ret = _format_pct(result.strategy_return)
        outperformed_text = (
            "YES" if result.strategy_outperformed else "NO"
        )

        alpha_style = "green" if result.benchmark_alpha > 0 else "red"
        outperformed_style = "bold green" if result.strategy_outperformed else "bold red"

        bench.add_row("Alpha", Text(alpha, style=alpha_style))
        bench.add_row("Beta", beta)
        bench.add_row("Benchmark Return (BTC)", bench_ret)
        bench.add_row("Strategy Return", strat_ret)
        bench.add_row("Strategy Outperformed", Text(outperformed_text, style=outperformed_style))
        console.print(bench)
    else:
        print(f"  Alpha: {result.benchmark_alpha:.4f}")
        print(f"  Beta: {result.benchmark_beta:.2f}")
        print(f"  Benchmark Return (BTC): {_format_pct(result.benchmark_return)}")
        print(f"  Strategy Return: {_format_pct(result.strategy_return)}")
        print(f"  Outperformed: {'YES' if result.strategy_outperformed else 'NO'}")

    print()

    # ── Overfitting ────────────────────────────────────────────────────
    _print_header(console, "Overfitting Detection")

    if console:
        of = Table(box=None)
        of.add_column("Metric", style="cyan")
        of.add_column("Value", justify="right")

        of_percentile = f"{result.overfitting_sharpe_percentile:.1f}%"
        of_flag = "OVERFIT" if result.overfitting_flag else "OK"

        of_flag_style = "bold red" if result.overfitting_flag else "bold green"
        of.add_row("Sharpe Percentile", of_percentile)
        of.add_row("Verdict", Text(of_flag, style=of_flag_style))
        console.print(of)
    else:
        print(f"  Sharpe Percentile: {result.overfitting_sharpe_percentile:.1f}%")
        print(f"  Verdict: {'OVERFIT' if result.overfitting_flag else 'OK'}")

    print()

    # ── Survivorship bias ──────────────────────────────────────────────
    if result.survivorship_warnings:
        _print_header(console, "Survivorship Bias Warnings")
        for msg in result.survivorship_warnings:
            _print_warning(console, msg)
        print()


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------

def _save_results(
    result: Any,
    symbol: str,
    strategy_name: str,
    timeframe: str,
    days: int,
) -> None:
    """Save backtest results to ``logs/backtest_results.json``."""
    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "backtest_results.json"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "days": days,
        "metrics": result.metrics,
        "n_trades": len(result.trades),
        "benchmark_alpha": result.benchmark_alpha,
        "benchmark_beta": result.benchmark_beta,
        "benchmark_return": result.benchmark_return,
        "strategy_return": result.strategy_return,
        "strategy_outperformed": result.strategy_outperformed,
        "overfitting_sharpe_percentile": result.overfitting_sharpe_percentile,
        "overfitting_flag": result.overfitting_flag,
        "survivorship_warnings": result.survivorship_warnings,
    }

    existing: list[dict] = []
    if log_path.exists():
        try:
            with open(log_path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, Exception):
            existing = []

    existing.append(entry)

    with open(log_path, "w") as f:
        json.dump(existing, f, indent=2, default=str)

    logger.info("Results saved to {}", log_path)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    """Run the backtest CLI."""
    import time as time_module

    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

    args = parse_args(argv)

    # Suppress INFO-level log spam during backtest
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    # Must be inside main() because pandas/numpy may not import at
    # module level on broken installations
    import pandas as pd  # noqa: F811

    console = _make_console()
    start_ts = time_module.time()

    # ── 1. Download strategy OHLCV ────────────────────────────────────
    _print_header(console, f"Downloading {args.symbol} ({args.timeframe}, {args.days}d)")
    ohlcv = _download_ohlcv_range(
        args.symbol, args.timeframe, args.days,
        force_download=args.force_download,
    )
    n_bars = len(ohlcv)
    if console:
        console.print(f"  Loaded {n_bars} bars from "
                       f"{ohlcv['timestamp'].iloc[0].date()} to "
                       f"{ohlcv['timestamp'].iloc[-1].date()}")
    else:
        print(f"Loaded {n_bars} bars")
    print()

    if n_bars < 30:
        print("ERROR: Insufficient data (< 30 bars). Aborting.")
        sys.exit(1)

    # ── 2. Download benchmark (BTCUSDT) ────────────────────────────────
    _print_header(console, "Downloading benchmark BTCUSDT")
    benchmark_ohlcv = _download_ohlcv_range(
        "BTCUSDT", args.timeframe, args.days,
        force_download=args.force_download,
    )
    n_bench = len(benchmark_ohlcv)
    if console:
        console.print(f"  Loaded {n_bench} bars")
    else:
        print(f"Loaded {n_bench} bars")
    print()

    # ── 3. Load strategy config ────────────────────────────────────────
    _print_header(console, f"Loading strategy '{args.strategy}'")
    strategy_config = _load_strategy_config(args.strategy, args.symbol)
    if strategy_config is None:
        print(f"ERROR: Strategy '{args.strategy}' not found in templates.")
        sys.exit(1)

    strategy_config["timeframe"] = args.timeframe
    # Override risk manager drawdown limit for backtesting
    if "risk" not in strategy_config:
        strategy_config["risk"] = {}
    strategy_config["risk"]["max_drawdown"] = args.max_drawdown
    if console:
        console.print(f"  Strategy: {strategy_config.get('name', args.strategy)}")
        console.print(f"  Symbol: {strategy_config.get('symbol', args.symbol)}")
        console.print(f"  Timeframe: {strategy_config.get('timeframe', '?')}")
    else:
        print(f"Strategy: {strategy_config.get('name', args.strategy)}")
    print()

    # ── 4. Run backtest with benchmark ─────────────────────────────────
    _print_header(console, "Running backtest...")

    from royaltdn.backtesting import run_with_benchmark

    result = asyncio.run(
        run_with_benchmark(
            strategy_config=strategy_config,
            ohlcv=ohlcv,
            benchmark_ohlcv=benchmark_ohlcv,
            initial_capital=args.initial_capital,
            commission=args.commission,
            slippage=args.slippage,
        ),
    )

    duration_s = time_module.time() - start_ts

    # ── 5. Print report ────────────────────────────────────────────────
    _print_result_report(
        console, result,
        symbol=args.symbol,
        strategy_name=args.strategy,
        timeframe=args.timeframe,
        days=args.days,
        duration_s=duration_s,
    )

    # ── 6. Save results ────────────────────────────────────────────────
    if not args.no_save:
        _save_results(result, args.symbol, args.strategy, args.timeframe, args.days)
        if console:
            from rich.text import Text
            console.print(
                Text("Results saved to logs/backtest_results.json", style="green"),
            )


if __name__ == "__main__":
    main()
