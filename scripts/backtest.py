#!/usr/bin/env python3
"""Professional backtester for CellMesh.

Reads ``logs/trading.log`` (JSON Lines), extracts all completed
trades (``position:closed``), computes comprehensive performance
metrics, and displays them in a Rich-formatted panel.

Usage:
    python scripts/backtest.py
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------

def load_trades(log_path: str = "logs/trading.log") -> list[dict[str, Any]]:
    """Load all closed-trade events from a JSON Lines file.

    Returns:
        List of position:closed event dicts sorted by timestamp.
    """
    path = Path(log_path)
    if not path.exists():
        print(f"⚠  No se encuentra {log_path}")
        return []

    trades: list[dict[str, Any]] = []
    all_positions: list[dict[str, Any]] = []  # for capital timeline

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("type") != "position":
                continue
            all_positions.append(event)
            if event.get("status") in ("closed", "close"):
                trades.append(event)

    trades.sort(key=lambda t: t.get("timestamp", ""))
    return trades


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_metrics(
    trades: list[dict[str, Any]],
    initial_capital: float = 100_000.0,
) -> dict[str, Any]:
    """Compute all backtesting metrics from a list of closed trades.

    Args:
        trades: List of ``position:closed`` event dicts.
        initial_capital: Starting capital.

    Returns:
        Dict of metric name → (value, is_good) for colour-coding.
    """
    n = len(trades)
    metrics: dict[str, Any] = {}

    if n == 0:
        metrics["total_trades"] = (0, None)
        metrics["message"] = ("No hay trades cerrados para analizar.", None)
        return metrics

    # ── Basic counts ──────────────────────────────────────────────────
    metrics["total_trades"] = (n, None)

    pnls = [_safe_float(t.get("pnl", 0)) for t in trades]
    capitals = [_safe_float(t.get("capital", 0)) for t in trades]

    total_pnl = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    n_wins = len(wins)
    n_losses = len(losses)

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = n_wins / n * 100 if n > 0 else 0.0

    metrics["pnl_total"] = (total_pnl, total_pnl >= 0)
    metrics["win_rate"] = (win_rate, win_rate >= 50)
    metrics["profit_factor"] = (
        gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        gross_profit >= gross_loss,
    )
    metrics["gross_profit"] = (gross_profit, True)
    metrics["gross_loss"] = (gross_loss, False)
    metrics["best_trade"] = (max(pnls) if n > 0 else 0, max(pnls) >= 0)
    metrics["worst_trade"] = (min(pnls) if n > 0 else 0, min(pnls) >= 0)

    # ── Expectancy ────────────────────────────────────────────────────
    avg_win = (sum(wins) / n_wins) if n_wins > 0 else 0.0
    avg_loss = (abs(sum(losses)) / n_losses) if n_losses > 0 else 0.0
    expectancy = win_rate / 100 * avg_win - (1 - win_rate / 100) * avg_loss
    metrics["expectancy"] = (expectancy, expectancy >= 0)

    # ── Sharpe & Sortino (trade-based) ────────────────────────────────
    # Returns per trade: r_i = pnl_i / capital_before_trade
    # We approximate capital_before_trade from the trade's capital field
    #   capital_before ≈ capital - pnl (since capital is post-trade)
    returns = []
    for i, t in enumerate(trades):
        pnl = pnls[i]
        cap = capitals[i]
        cap_before = cap - pnl
        if cap_before > 0:
            returns.append(pnl / cap_before)
        else:
            returns.append(0.0)

    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(var_r) if var_r > 0 else 0.0

        # Negative returns only (for Sortino)
        neg_returns = [r for r in returns if r < 0]
        if neg_returns:
            downside_var = (
                sum(r ** 2 for r in neg_returns) / len(neg_returns)
            )
            downside_std = math.sqrt(downside_var)
        else:
            downside_std = 0.0

        # Annualization factor: sqrt of estimated trades per year
        # Use trading days (252) as a proxy since we have intra-day data
        # Scale by (n_trades / days) for better annualization
        timestamps = [_parse_ts(t.get("timestamp")) for t in trades]
        valid_ts = [ts for ts in timestamps if ts is not None]
        if len(valid_ts) >= 2:
            days_span = (valid_ts[-1] - valid_ts[0]).total_seconds() / 86400
            days_span = max(days_span, 1)
            trades_per_year = n / days_span * 365
        else:
            trades_per_year = n  # fallback

        ann_factor = math.sqrt(trades_per_year) if trades_per_year > 0 else 1.0

        sharpe = (mean_r * ann_factor / std_r) if std_r > 0 else 0.0
        sortino = (
            (mean_r * ann_factor / downside_std) if downside_std > 0 else 0.0
        )
    else:
        sharpe = 0.0
        sortino = 0.0

    metrics["sharpe_ratio"] = (sharpe, sharpe >= 1.0)
    metrics["sortino_ratio"] = (sortino, sortino >= 1.0)

    # ── Max Drawdown (capital-based) ──────────────────────────────────
    # Build equity curve from ALL position events (opened + closed)
    log_path = Path("logs/trading.log")
    equity: list[float] = [initial_capital]
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                if ev.get("type") == "position":
                    cap = _safe_float(ev.get("capital", 0))
                    if cap > 0:
                        equity.append(cap)

    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = (val - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    metrics["max_drawdown"] = (max_dd * 100, max_dd >= -10)

    # ── CAGR (if enough time span) ────────────────────────────────────
    timestamps = [_parse_ts(t.get("timestamp")) for t in trades]
    valid_ts = [ts for ts in timestamps if ts is not None]
    if len(valid_ts) >= 2:
        days_span = (valid_ts[-1] - valid_ts[0]).total_seconds() / 86400
        if days_span >= 30:
            years = days_span / 365.0
            if years > 0 and equity[-1] > 0 and initial_capital > 0:
                cagr = (equity[-1] / initial_capital) ** (1.0 / years) - 1
            else:
                cagr = 0.0
            metrics["cagr"] = (cagr * 100, cagr >= 0)
        else:
            metrics["cagr"] = (f"N/A (< 30 días de datos)", None)
    else:
        metrics["cagr"] = ("N/A", None)

    # ── Average duration (if we can pair open/close by trade_id) ──────
    durations: list[float] = []
    if log_path.exists():
        # Build a dict of position:opened events by trade_id
        opened_by_id: dict[str, str] = {}
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                if (
                    ev.get("type") == "position"
                    and ev.get("status") == "opened"
                    and ev.get("trade_id")
                ):
                    opened_by_id[ev["trade_id"]] = ev.get("timestamp", "")
        # Pair each closed trade with its opening event
        for t in trades:
            tid = t.get("trade_id", "")
            close_ts = _parse_ts(t.get("timestamp"))
            open_ts = _parse_ts(opened_by_id.get(tid))
            if open_ts and close_ts and close_ts > open_ts:
                durations.append(
                    (close_ts - open_ts).total_seconds()
                )

    if durations:
        avg_duration_sec = sum(durations) / len(durations)
        metrics["avg_duration"] = (_fmt_duration(avg_duration_sec), None)
    else:
        metrics["avg_duration"] = ("N/A (sin pairing)", None)

    return metrics


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def _fmt_money(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:,.2f}"


def _fmt_pct(val: float) -> str:
    return f"{val:+.2f}%" if val != 0 else "0.00%"


def _fmt_ratio(val: float) -> str:
    if math.isinf(val):
        return "∞"
    return f"{val:.2f}"


# ---------------------------------------------------------------------------
# Rich display
# ---------------------------------------------------------------------------

def display_results(metrics: dict[str, Any]) -> None:
    """Print a professional Rich panel with backtest results.

    Falls back to plain text when Rich is unavailable.
    """
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console(color_system="standard")
        table = Table(show_header=False, box=None, padding=(0, 2))

        rows = []

        def add_row(label: str, value: Any, *, is_good: bool | None = None) -> None:
            if is_good is True:
                style = "green"
            elif is_good is False:
                style = "red"
            else:
                style = ""
            val_str = str(value)
            table.add_row(Text(label, style="bold cyan"), Text(val_str, style=style))
            rows.append((label, value))

        # ── Summary metrics ───────────────────────────────────────────
        for key, nice_label in [
            ("total_trades", "Total trades"),
            ("pnl_total", "P&L total"),
            ("win_rate", "Win Rate"),
            ("profit_factor", "Profit Factor"),
        ]:
            if key in metrics:
                val, good = metrics[key]
                if key == "win_rate":
                    add_row(nice_label, f"{val:.1f}%", is_good=good)
                elif key == "profit_factor":
                    add_row(nice_label, _fmt_ratio(val), is_good=good)
                elif key == "pnl_total":
                    add_row(nice_label, _fmt_money(val), is_good=good)
                else:
                    add_row(nice_label, str(val), is_good=good)

        add_row("", "")  # spacer

        for key, nice_label in [
            ("gross_profit", "Ganancias totales"),
            ("gross_loss", "Pérdidas totales"),
            ("best_trade", "Mejor trade"),
            ("worst_trade", "Peor trade"),
        ]:
            if key in metrics:
                val, good = metrics[key]
                add_row(nice_label, _fmt_money(val), is_good=good)

        add_row("", "")  # spacer

        for key, nice_label in [
            ("sharpe_ratio", "Sharpe Ratio"),
            ("sortino_ratio", "Sortino Ratio"),
            ("max_drawdown", "Max Drawdown"),
            ("cagr", "CAGR"),
            ("expectancy", "Expectancy"),
            ("avg_duration", "Duración media"),
        ]:
            if key in metrics:
                val, good = metrics[key]
                if key == "max_drawdown":
                    add_row(nice_label, _fmt_pct(val), is_good=good)
                elif key == "sharpe_ratio":
                    add_row(nice_label, _fmt_ratio(val), is_good=good)
                elif key == "sortino_ratio":
                    add_row(nice_label, _fmt_ratio(val), is_good=good)
                elif key == "expectancy":
                    add_row(nice_label, _fmt_money(val), is_good=good)
                elif key == "cagr":
                    add_row(nice_label, _fmt_pct(val) if isinstance(val, float) else val, is_good=good)
                else:
                    add_row(nice_label, str(val), is_good=good)

        panel = Panel(
            table,
            title="[bold]Backtesting[/bold]",
            border_style="cyan",
        )
        console.print(panel)

    except ImportError:
        # Plain-text fallback
        print("╭─────────────────────── Backtesting ───────────────────────╮")
        for key, nice_label in [
            ("total_trades", "Total trades"),
            ("pnl_total", "P&L total"),
            ("win_rate", "Win Rate"),
            ("profit_factor", "Profit Factor"),
            ("", ""),
            ("gross_profit", "Ganancias totales"),
            ("gross_loss", "Pérdidas totales"),
            ("best_trade", "Mejor trade"),
            ("worst_trade", "Peor trade"),
            ("", ""),
            ("sharpe_ratio", "Sharpe Ratio"),
            ("sortino_ratio", "Sortino Ratio"),
            ("max_drawdown", "Max Drawdown"),
            ("cagr", "CAGR"),
            ("expectancy", "Expectancy"),
            ("avg_duration", "Duración media"),
        ]:
            if not nice_label:
                print("│" + " " * 54 + "│")
                continue
            if key in metrics:
                val, good = metrics[key]
                if key == "win_rate":
                    display = f"{val:.1f}%"
                elif key in ("profit_factor", "sharpe_ratio", "sortino_ratio"):
                    display = _fmt_ratio(val)
                elif key in ("pnl_total", "gross_profit", "gross_loss",
                             "best_trade", "worst_trade", "expectancy"):
                    display = _fmt_money(val)
                elif key == "max_drawdown":
                    display = _fmt_pct(val)
                elif key == "cagr":
                    display = _fmt_pct(val) if isinstance(val, float) else str(val)
                else:
                    display = str(val)
                print(f"│ {nice_label:20s} {display:>30s} │")
        print("╰" + "─" * 54 + "╯")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_results(metrics: dict[str, Any], path: str = "logs/backtest_results.json") -> None:
    """Save backtest metrics to a JSON file."""
    serializable: dict[str, Any] = {}
    for key, (val, _good) in metrics.items():
        if isinstance(val, float) and (math.isinf(val) or math.isnan(val)):
            serializable[key] = str(val)
        else:
            serializable[key] = val

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\n📁 Resultados guardados en {path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    trades = load_trades()
    if not trades:
        print("⚠  No hay trades cerrados en logs/trading.log")
        return

    metrics = compute_metrics(trades)
    display_results(metrics)
    save_results(metrics)


if __name__ == "__main__":
    main()
