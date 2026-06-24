#!/usr/bin/env python3
"""Optuna-based strategy optimization for CellMesh.

Downloads historical OHLCV data (2 years), runs Bayesian hyperparameter
optimization per strategy, and optionally writes best params back to YAML.

Usage:
    python scripts/optimize.py --strategy scalping_momentum --trials 50
    python scripts/optimize.py --strategy all --trials 20
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os

from loguru import logger

# ---------------------------------------------------------------------------
# Telegram notifications
# ---------------------------------------------------------------------------

def send_telegram(message: str) -> bool:
    """Send a Telegram notification via the Bot API.

    Args:
        message: Text to send (HTML supported).

    Returns:
        True if sent successfully, False otherwise.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping notification")
        return False

    from httpx import post

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.debug("Telegram notification sent")
        return True
    except Exception as exc:
        logger.warning("Telegram notification failed: {}", exc)
        return False


# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger.remove()
logger.add(sys.stderr, level="WARNING")

# ---------------------------------------------------------------------------
# Rich helpers (optional)
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich.text import Text

    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

# Lazy imports (used inside functions)
#   from cells.base import Cell
#   from inference.engine import InferenceEngine
#   from risk.portfolio import Portfolio
#   from risk.manager import RiskManager
#   from data.historical import download_2y_ohlcv, read_cache, write_cache
#   from scripts.backtest import compute_metrics


# ---------------------------------------------------------------------------
# Argument parsing  (Task 2.1)
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Optuna-based strategy optimization",
    )
    parser.add_argument(
        "--strategy", type=str, default=None,
        help="Strategy name or 'all'",
    )
    parser.add_argument(
        "--trials", type=int, default=100,
        help="Number of Optuna trials per strategy",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Don't update YAML with best params",
    )
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated symbols to filter",
    )
    parser.add_argument(
        "--force-download", action="store_true",
        help="Force re-download of historical data",
    )
    parser.add_argument(
        "--metric", type=str, default="sharpe",
        choices=["sharpe", "profit_factor", "sortino"],
        help="Objective metric to maximize",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Run validation on hold-out data after optimization",
    )
    parser.add_argument(
        "--no-telegram", action="store_true",
        help="Disable Telegram notifications",
    )
    parser.add_argument(
        "--walk-forward", action="store_true",
        help="Run walk-forward validation instead of optimization",
    )
    parser.add_argument(
        "--walk-forward-integrated", action="store_true",
        help="Optimize using walk-forward objective (avg OOS Sharpe across 3 windows)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Strategy loading
# ---------------------------------------------------------------------------

def load_all_strategies() -> list[dict[str, Any]]:
    """Load all strategy configs from YAML template files.

    Each YAML file contains a list of strategy dicts (no document separators).

    Returns:
        Flat list of all strategy config dicts across all template files.
        Each dict is tagged with a ``_source_file`` key.
    """
    from yaml import safe_load
    templates_dir = _PROJECT_ROOT / "cells" / "templates"
    strategies: list[dict[str, Any]] = []
    for yaml_path in sorted(templates_dir.glob("*.yaml")):
        try:
            with open(yaml_path) as f:
                doc = safe_load(f)
            if isinstance(doc, list):
                for item in doc:
                    if isinstance(item, dict):
                        item["_source_file"] = str(yaml_path)
                        strategies.append(item)
            elif isinstance(doc, dict):
                doc["_source_file"] = str(yaml_path)
                strategies.append(doc)
        except Exception as exc:
            logger.error("Error loading {}: {}", yaml_path, exc)
    return strategies


def find_strategy(name: str, strategies: list[dict[str, Any]]) -> dict | None:
    """Find a strategy by name in the flattened list.

    Args:
        name: Strategy name to match (``name`` field).
        strategies: Flat list of strategy config dicts.

    Returns:
        The matching strategy dict or ``None``.
    """
    for s in strategies:
        if s.get("name") == name:
            return s
    return None


def filter_strategies(
    strategies: list[dict],
    strategy_name: str | None,
    symbols_filter: str | None,
) -> list[dict]:
    """Filter strategies by name and/or symbol list.

    Args:
        strategies: Flat list of strategy dicts.
        strategy_name: Single strategy name or ``"all"`` / ``None``.
        symbols_filter: Comma-separated symbol whitelist or ``None``.

    Returns:
        Filtered list of strategy dicts.
    """
    result = strategies

    if strategy_name and strategy_name != "all":
        s = find_strategy(strategy_name, result)
        return [s] if s else []

    if symbols_filter:
        allowed = {sym.strip().upper() for sym in symbols_filter.split(",")}
        result = [s for s in result if s.get("symbol", "").upper() in allowed]

    return result


# ---------------------------------------------------------------------------
# Data loading with cache  (Task 1.3 integration)
# ---------------------------------------------------------------------------

def get_ohlcv(
    symbol: str,
    timeframe: str,
    force_download: bool = False,
) -> "pd.DataFrame":
    """Load OHLCV data from cache or download fresh.

    Args:
        symbol: Trading pair (e.g. ``"BTCUSDT"``).
        timeframe: Kline interval.
        force_download: Ignore cache and re-download.

    Returns:
        DataFrame with standard OHLCV columns.
    """
    from data.historical import download_2y_ohlcv, read_cache, write_cache

    df = None
    if not force_download:
        df = read_cache(symbol, timeframe)

    if df is None:
        df = download_2y_ohlcv(symbol, timeframe)
        write_cache(symbol, timeframe, df)

    return df


# ---------------------------------------------------------------------------
# Parameter mapping  (Task 2.2)
# ---------------------------------------------------------------------------

# Default range table for parameter names
_PARAM_RANGES: dict[str, tuple] = {
    # (type, low, high, step)  — type is "int" or "float"
    "period": ("int", 2, 50, None),
    "factor": ("float", 0.5, 5.0, 0.1),
    "multiplier": ("float", 0.5, 5.0, 0.1),
    "atr_multiplier": ("float", 0.5, 6.0, 0.1),
    "pct": ("float", 0.1, 10.0, 0.1),
    "max_pct": ("float", 0.1, 10.0, 0.1),
    "max_spread_pct": ("float", 0.01, 1.0, 0.01),
    "sizing": ("float", 0.005, 0.1, 0.005),
    "zscore_threshold": ("float", 0.1, 2.0, 0.1),
    "operator_threshold": ("int", 10, 40, None),
    "lookback": ("int", 10, 200, None),
    "touch_count": ("int", 1, 5, None),
    "max_positions": ("int", 1, 5, None),
    "fast": ("int", 5, 30, None),
    "slow": ("int", 15, 50, None),
    "signal": ("int", 5, 15, None),
    "tenkan": ("int", 5, 20, None),
    "kijun": ("int", 10, 50, None),
    "senkou_b": ("int", 20, 70, None),
    # Operator threshold extraction (e.g. "< -2.5" -> threshold -2.5)
}

# Param names that should NOT be optimized (structural, not numeric tuning)
_EXCLUDED_PARAMS: set[str] = {"indicator", "operator", "type", "logic", "conditions"}


def _get_param_range(param_name: str) -> tuple | None:
    """Look up the optimisation range for a parameter by name.

    Falls back to a sensible default for unknown numeric params.

    Args:
        param_name: Parameter name to look up (e.g. ``"period"``).

    Returns:
        Tuple of ``(type, low, high, step)`` or ``None``.
    """
    if param_name in _PARAM_RANGES:
        return _PARAM_RANGES[param_name]
    # Try prefix matching for compound names
    for key, rng in _PARAM_RANGES.items():
        if param_name.startswith(key) or key.endswith(param_name):
            return rng
    return None


def _extract_operator_threshold(operator_str: str) -> float | None:
    """Extract a numeric threshold from an operator string like ``"< -2.5"``.

    Returns the numeric value or None if parsing fails.
    """
    from re import search
    match = search(r"[-+]?\d*\.?\d+", operator_str)
    if match:
        return float(match.group())
    return None


def suggest_params(trial: Any, strategy_config: dict) -> dict[str, Any]:
    """Build a flat param dict by suggesting values via Optuna trial.

    Walks ``entry.conditions[].params``, ``exit[].params``, and ``risk``
    sections to identify tunable numeric parameters.

    Args:
        trial: An Optuna ``Trial`` object.
        strategy_config: Full strategy config dict from YAML.

    Returns:
        Flat dict mapping ``{param_key: suggested_value}``.
    """
    params: dict[str, Any] = {}

    # ── Entry conditions ───────────────────────────────────────────────
    entry = strategy_config.get("entry", {})
    conditions = entry.get("conditions", [])
    for cond_idx, cond in enumerate(conditions):
        indicator = cond.get("indicator", "")
        cond_params = cond.get("params", {})
        operator = cond.get("operator", "")

        for pname, pval in cond_params.items():
            if pname in _EXCLUDED_PARAMS:
                continue
            if not isinstance(pval, (int, float)):
                continue
            rng = _get_param_range(pname)
            if rng is None:
                continue
            ptype, low, high, step = rng
            key = f"entry.{cond_idx}.{indicator}.{pname}"
            if ptype == "int":
                params[key] = trial.suggest_int(key, int(low), int(high))
            else:
                params[key] = trial.suggest_float(key, low, high, step=step if step else None)

        # Suggest operator threshold if numeric
        op_val = _extract_operator_threshold(operator)
        if op_val is not None and isinstance(op_val, (int, float)):
            key = f"entry.{cond_idx}.{indicator}.operator_threshold"
            op_rng = _get_param_range("operator_threshold")
            if op_rng:
                params[key] = trial.suggest_int(key, int(op_rng[1]), int(op_rng[2]))

    # ── Exit rules ─────────────────────────────────────────────────────
    exit_rules = strategy_config.get("exit", [])
    for exit_idx, rule in enumerate(exit_rules):
        rule_type = rule.get("type", "")
        rule_params = rule.get("params", {})
        for pname, pval in rule_params.items():
            if pname in _EXCLUDED_PARAMS:
                continue
            if not isinstance(pval, (int, float)):
                continue
            rng = _get_param_range(pname)
            if rng is None:
                continue
            ptype, low, high, step = rng
            key = f"exit.{exit_idx}.{rule_type}.{pname}"
            if ptype == "int":
                params[key] = trial.suggest_int(key, int(low), int(high))
            else:
                params[key] = trial.suggest_float(key, low, high, step=step if step else None)

    # ── Risk section ───────────────────────────────────────────────────
    risk = strategy_config.get("risk", {})
    for pname, pval in risk.items():
        if pname in _EXCLUDED_PARAMS:
            continue
        if not isinstance(pval, (int, float)):
            continue
        rng = _get_param_range(pname)
        if rng is None:
            continue
        ptype, low, high, step = rng
        key = f"risk.{pname}"
        if ptype == "int":
            params[key] = trial.suggest_int(key, int(low), int(high))
        else:
            params[key] = trial.suggest_float(key, low, high, step=step if step else None)

    return params


def apply_params(config: dict, param_dict: dict) -> dict[str, Any]:
    """Return a new config dict with optimized params merged in.

    Args:
        config: Original strategy config dict.
        param_dict: Flat dict from ``suggest_params()`` or best params.

    Returns:
        Deep-copied config with params applied.
    """
    new_config = copy.deepcopy(config)

    for key, value in param_dict.items():
        parts = key.split(".")
        if parts[0] == "entry":
            cond_idx = int(parts[1])
            pname = parts[3] if parts[3] != "operator_threshold" else parts[3]
            if pname == "operator_threshold":
                # Update the operator string threshold
                conditions = new_config.get("entry", {}).get("conditions", [])
                if cond_idx < len(conditions):
                    old_op = conditions[cond_idx].get("operator", "")
                    from re import sub
                    conditions[cond_idx]["operator"] = sub(
                        r"[-+]?\d*\.?\d+", f"{value:.1f}", old_op, count=1,
                    )
            else:
                # Update param value
                conditions = new_config.get("entry", {}).get("conditions", [])
                if cond_idx < len(conditions):
                    conditions[cond_idx].setdefault("params", {})[pname] = value

        elif parts[0] == "exit":
            exit_idx = int(parts[1])
            pname = parts[3]
            exit_rules = new_config.get("exit", [])
            if exit_idx < len(exit_rules):
                exit_rules[exit_idx].setdefault("params", {})[pname] = value

        elif parts[0] == "risk":
            pname = parts[1]
            new_config.setdefault("risk", {})[pname] = value

    return new_config


# ---------------------------------------------------------------------------
# Historical simulation  (Task 2.3)
# ---------------------------------------------------------------------------

async def simulate(
    strategy_config: dict,
    ohlcv: "pd.DataFrame",
    initial_capital: float = 100_000.0,
) -> list[dict[str, Any]]:
    """Run a bar-by-bar simulation of the strategy against OHLCV data.

    Args:
        strategy_config: Strategy config dict (with params applied).
        ohlcv: DataFrame with columns ``timestamp``, ``open``, ``high``,
            ``low``, ``close``, ``volume``.
        initial_capital: Starting capital.

    Returns:
        List of closed trade dicts, each with ``symbol``, ``action``,
        ``entry_price``, ``exit_price``, ``qty``, ``pnl``, ``capital``.
    """
    from cells.base import Cell
    from inference.engine import InferenceEngine
    from risk.portfolio import Portfolio
    from risk.manager import RiskManager

    cell = Cell(strategy_config, inference_engine=InferenceEngine())
    portfolio = Portfolio(initial_capital=initial_capital)
    risk_manager = RiskManager(portfolio, max_positions=strategy_config.get("risk", {}).get("max_positions", 5))

    symbol = strategy_config.get("symbol", "")
    trades: list[dict[str, Any]] = []
    warmup_bars = 20  # minimum bars before entry evaluation

    for idx, (_, bar) in enumerate(ohlcv.iterrows()):
        close = float(bar["close"])
        event = {
            "symbol": symbol,
            "type": "tick",
            "price": close,
            "data": {
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": close,
                "volume": float(bar["volume"]),
            },
        }

        # Feed bar even during warmup
        signal = await cell.handle(event)

        if signal is None:
            continue

        if signal["action"] == "BUY":
            if idx < warmup_bars:
                continue
            approved = risk_manager.approve(signal)
            if approved is not None:
                portfolio.update(approved)

        elif signal["action"] == "SELL":
            # Route through risk_manager to get proper qty
            approved = risk_manager.approve(signal)
            if approved is not None:
                qty = approved.get("qty", 0.0)
                entry_price = float(signal.get("entry_price", 0) or 0)
                pnl = (close - entry_price) * qty if qty > 0 else 0.0
                portfolio.update(approved)
                trades.append({
                    "symbol": symbol,
                    "action": "SELL",
                    "entry_price": entry_price,
                    "exit_price": close,
                    "qty": qty,
                    "pnl": round(pnl, 2),
                    "capital": round(portfolio.capital, 2),
                })

    return trades


# ---------------------------------------------------------------------------
# Metrics integration  (Task 2.4)
# ---------------------------------------------------------------------------

def compute_objective(trades: list[dict], metric: str = "sharpe") -> float:
    """Compute the objective value from a list of closed trades.

    Args:
        trades: List of trade dicts from ``simulate()``.
        metric: Which metric to extract (``"sharpe"``, ``"sortino"``,
            ``"profit_factor"``).

    Returns:
        Scalar value for Optuna to maximize. Returns ``-999.0`` when there
        are no trades.
    """
    if not trades:
        return -999.0

    from scripts.backtest import compute_metrics

    metrics = compute_metrics(trades)

    metric_key_map = {
        "sharpe": "sharpe_ratio",
        "sortino": "sortino_ratio",
        "profit_factor": "profit_factor",
    }
    key = metric_key_map.get(metric, "sharpe_ratio")
    result = metrics.get(key)

    if result is None:
        return -999.0

    # compute_metrics returns tuples (value, is_good)
    if isinstance(result, (list, tuple)):
        value = result[0]
    else:
        value = result

    # Handle non-numeric values
    if not isinstance(value, (int, float)) or math.isinf(value) or math.isnan(value):
        return -999.0

    return value


# ---------------------------------------------------------------------------
# Optuna study loop  (Task 2.5)
# ---------------------------------------------------------------------------

def optimize_strategy(
    strategy_name: str,
    strategy_config: dict,
    ohlcv: "pd.DataFrame",
    n_trials: int = 100,
    metric: str = "sharpe",
    console: Any = None,
) -> dict[str, Any]:
    """Run an Optuna study for a single strategy.

    Args:
        strategy_name: Human-readable name for logging.
        strategy_config: Full strategy config dict.
        ohlcv: OHLCV DataFrame for simulation.
        n_trials: Number of Optuna trials.
        metric: Objective metric name.
        console: Rich Console instance (optional).

    Returns:
        Dict with keys ``best_params``, ``best_value``, ``best_trial``,
        ``best_metrics``.
    """
    from optuna import create_study
    from optuna.pruners import MedianPruner
    from optuna.samplers import TPESampler

    study = create_study(
        direction="maximize",
        sampler=TPESampler(seed=42),
        pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=10, interval_steps=5),
    )

    # Prepare progress tracking
    progress_bar = None
    progress_task = None
    if _HAS_RICH and console:
        progress_bar = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        progress_bar.start()
        progress_task = progress_bar.add_task(
            f"[cyan]{strategy_name}[/]", total=n_trials,
        )

    def objective(trial: Any) -> float:
        params = suggest_params(trial, strategy_config)
        modified_config = apply_params(strategy_config, params)
        trades = asyncio.run(simulate(modified_config, ohlcv))
        obj_value = compute_objective(trades, metric)

        # Store all metrics for reporting
        if trades:
            from scripts.backtest import compute_metrics
            full_metrics = compute_metrics(trades)
            # Map compute_metrics keys to schema keys
            metric_map = {
                "sharpe_ratio": "sharpe_ratio",
                "profit_factor": "profit_factor",
                "win_rate": "win_rate",
                "max_drawdown": "max_drawdown",
                "pnl_total": "total_pnl",
                "total_trades": "n_trades",
            }
            for src_key, dst_key in metric_map.items():
                if src_key in full_metrics:
                    val, _ = (
                        full_metrics[src_key]
                        if isinstance(full_metrics[src_key], (list, tuple))
                        else (full_metrics[src_key], None)
                    )
                    trial.set_user_attr(dst_key, val)
        else:
            trial.set_user_attr("sharpe_ratio", -999.0)

        if progress_task is not None and progress_bar is not None:
            progress_bar.update(progress_task, advance=1)

        return obj_value

    # Handle KeyboardInterrupt gracefully
    original_sigint = signal.getsignal(signal.SIGINT)
    interrupted = False

    def _sigint_handler(signum: int, frame: Any) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            logger.warning("Interrupt received — stopping study after current trial...")
            study.stop()
        signal.signal(signal.SIGINT, original_sigint)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        study.optimize(objective, n_trials=n_trials)
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        if progress_bar is not None:
            progress_bar.stop()

    # Collect best-trial metrics
    best_metrics: dict[str, Any] = {}
    worst_metrics: dict[str, Any] = {}
    if study.best_trial is not None:
        for k, v in study.best_trial.user_attrs.items():
            best_metrics[k] = v

    # Track worst trial as well
    worst_trial = None
    worst_value = float("inf")
    for t in study.trials:
        if t.value is not None and t.value < worst_value:
            worst_value = t.value
            worst_trial = t
    if worst_trial is not None:
        for k, v in worst_trial.user_attrs.items():
            worst_metrics[k] = v

    return {
        "best_params": study.best_params,
        "best_value": study.best_value,
        "best_trial": study.best_trial.number if study.best_trial is not None else -1,
        "best_metrics": best_metrics,
        "worst_metrics": worst_metrics,
        "trials_completed": len(study.trials),
    }


# ---------------------------------------------------------------------------
# Walk-forward integrated optimization
# ---------------------------------------------------------------------------

def optimize_strategy_wf_integrated(
    strategy_name: str,
    strategy_config: dict,
    ohlcv: "pd.DataFrame",
    n_trials: int = 100,
    metric: str = "sharpe",
    console: Any = None,
    n_windows: int = 3,
) -> dict[str, Any]:
    """Run Optuna study with walk-forward integrated objective.

    Each trial evaluates the average out-of-sample Sharpe across multiple
    non-overlapping test windows, rewarding params that generalize.

    Args:
        strategy_name: Human-readable name for logging.
        strategy_config: Full strategy config dict.
        ohlcv: OHLCV DataFrame for simulation.
        n_trials: Number of Optuna trials.
        metric: Objective metric name.
        console: Rich Console instance (optional).
        n_windows: Number of walk-forward windows.

    Returns:
        Dict with keys ``best_params``, ``best_value``, ``best_trial``,
        ``best_metrics``.
    """
    from optuna import create_study
    from optuna.pruners import MedianPruner
    from optuna.samplers import TPESampler

    study = create_study(
        direction="maximize",
        sampler=TPESampler(seed=42),
        pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=10, interval_steps=5),
    )

    # Prepare progress tracking
    progress_bar = None
    progress_task = None
    if _HAS_RICH and console:
        progress_bar = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        progress_bar.start()
        progress_task = progress_bar.add_task(
            f"[cyan]WF-INT {strategy_name}[/]", total=n_trials,
        )

    def objective(trial: Any) -> float:
        params = suggest_params(trial, strategy_config)
        modified_config = apply_params(strategy_config, params)

        total = len(ohlcv)
        step = int(total * 0.2)  # 20% step between windows

        test_sharpes = []
        for w in range(n_windows):
            train_start = w * step
            train_end = train_start + int(total * 0.6)
            val_start = train_end
            val_end = val_start + int(total * 0.4)

            if val_end > total:
                val_end = total
            if val_end - val_start < 100:
                continue  # skip windows with tiny test sets

            # Simulate on test portion only
            test_data = ohlcv.iloc[val_start:val_end].reset_index(drop=True)
            trades = asyncio.run(simulate(modified_config, test_data))
            sh = compute_objective(trades, metric)
            if sh > -990:  # Only count windows that generated trades
                test_sharpes.append(sh)

        if not test_sharpes:
            return -999.0

        avg_sharpe = sum(test_sharpes) / len(test_sharpes)

        # Store metrics in trial user attrs
        trial.set_user_attr("avg_oos_sharpe", avg_sharpe)
        trial.set_user_attr("n_windows_valid", len(test_sharpes))
        trial.set_user_attr("window_sharpes", test_sharpes)

        if progress_task is not None and progress_bar is not None:
            progress_bar.update(progress_task, advance=1)

        return avg_sharpe

    # Handle KeyboardInterrupt gracefully
    original_sigint = signal.getsignal(signal.SIGINT)
    interrupted = False

    def _sigint_handler(signum: int, frame: Any) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            logger.warning("Interrupt received — stopping study after current trial...")
            study.stop()
        signal.signal(signal.SIGINT, original_sigint)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        study.optimize(objective, n_trials=n_trials)
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        if progress_bar is not None:
            progress_bar.stop()

    # Collect best-trial metrics
    best_metrics: dict[str, Any] = {}
    worst_metrics: dict[str, Any] = {}
    if study.best_trial is not None:
        for k, v in study.best_trial.user_attrs.items():
            best_metrics[k] = v

    # Track worst trial as well
    worst_trial = None
    worst_value = float("inf")
    for t in study.trials:
        if t.value is not None and t.value < worst_value:
            worst_value = t.value
            worst_trial = t
    if worst_trial is not None:
        for k, v in worst_trial.user_attrs.items():
            worst_metrics[k] = v

    return {
        "best_params": study.best_params,
        "best_value": study.best_value,
        "best_trial": study.best_trial.number if study.best_trial is not None else -1,
        "best_metrics": best_metrics,
        "worst_metrics": worst_metrics,
        "trials_completed": len(study.trials),
    }


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def walk_forward_validate(
    strategy_name: str,
    strategy_config: dict,
    ohlcv: "pd.DataFrame",
    n_trials: int = 100,
    metric: str = "sharpe",
    console: Any = None,
) -> dict[str, Any]:
    """Run walk-forward validation across 5 sequential windows.

    Args:
        strategy_name: Human-readable name for logging.
        strategy_config: Full strategy config dict.
        ohlcv: OHLCV DataFrame for simulation.
        n_trials: Number of Optuna trials PER WINDOW.
        metric: Objective metric name.
        console: Rich Console instance (optional).

    Returns:
        Dict with per-window results and aggregated metrics + verdict.
    """
    total = len(ohlcv)
    step = total // 5  # 20% step

    windows: list[dict[str, Any]] = []

    for w in range(5):
        train_start = w * step
        train_end = min(train_start + int(step * 3.5), total)  # ~70%
        val_start = train_end
        val_end = min(val_start + int(step * 1.5), total)  # ~30%

        train_bars = train_end - train_start
        val_bars = val_end - val_start

        if train_bars < 100:
            logger.warning("Window {}: insufficient training data ({} bars), skipping", w, train_bars)
            continue
        if val_bars < 20:
            logger.warning("Window {}: insufficient validation data ({} bars), skipping", w, val_bars)
            continue

        train_ohlcv = ohlcv.iloc[train_start:train_end].reset_index(drop=True)
        val_ohlcv = ohlcv.iloc[val_start:val_end].reset_index(drop=True)

        if _HAS_RICH and console:
            console.print(
                f"  Window {w+1}/5: train=[{train_start}:{train_end}] "
                f"({train_bars} bars), val=[{val_start}:{val_end}] ({val_bars} bars)"
            )
        else:
            print(
                f"  Window {w+1}/5: train=[{train_start}:{train_end}] "
                f"({train_bars} bars), val=[{val_start}:{val_end}] ({val_bars} bars)"
            )

        # Run Optuna optimization on the training period
        opt_result = optimize_strategy(
            strategy_name=f"{strategy_name}_w{w}",
            strategy_config=strategy_config,
            ohlcv=train_ohlcv,
            n_trials=n_trials,
            metric=metric,
            console=console,
        )

        best_params = opt_result.get("best_params", {})

        # Evaluate best params on the validation period
        modified_config = apply_params(strategy_config, best_params)
        val_trades = asyncio.run(simulate(modified_config, val_ohlcv))

        is_best_value = opt_result.get("best_value", -999.0)
        is_metrics = opt_result.get("best_metrics", {})

        # Compute validation metrics
        val_objective = compute_objective(val_trades, metric)
        val_metrics_raw: dict = {}
        if val_trades:
            from scripts.backtest import compute_metrics
            val_metrics_raw = compute_metrics(val_trades)

        val_metrics: dict[str, Any] = {}
        for k, v in val_metrics_raw.items():
            if isinstance(v, (list, tuple)):
                val_metrics[k] = v[0]
            else:
                val_metrics[k] = v

        window_result = {
            "window": w,
            "train_bars": train_bars,
            "val_bars": val_bars,
            "is_sharpe": is_best_value,
            "is_profit_factor": is_metrics.get("profit_factor", -999),
            "is_win_rate": is_metrics.get("win_rate", -999),
            "is_trades": is_metrics.get("n_trades", 0),
            "oos_sharpe": val_objective,
            "oos_profit_factor": val_metrics.get("profit_factor", -999),
            "oos_win_rate": val_metrics.get("win_rate", -999),
            "oos_trades": val_metrics.get("total_trades", len(val_trades)),
            "best_params": best_params,
        }
        windows.append(window_result)

        # Per-window one-liner
        win_sharpe = window_result["oos_sharpe"]
        win_pf = window_result["oos_profit_factor"]
        win_wr = window_result["oos_win_rate"]
        win_trades = window_result["oos_trades"]

        if _HAS_RICH and console:
            sharpe_style = "green" if win_sharpe > 0.5 else ("yellow" if win_sharpe > 0 else "red")
            console.print(
                f"    IS Sharpe: {is_best_value:.2f}  |  "
                f"OOS Sharpe: [bold {sharpe_style}]{win_sharpe:.2f}[/]  |  "
                f"OOS PF: {win_pf if isinstance(win_pf, float) else 'N/A'}  |  "
                f"OOS Trades: {win_trades}"
            )
        else:
            print(
                f"    IS Sharpe: {is_best_value:.2f}  |  "
                f"OOS Sharpe: {val_objective:.2f}  |  "
                f"OOS Trades: {win_trades}"
            )

    # ── Aggregate across windows ─────────────────────────────────────
    if not windows:
        return {
            "strategy_name": strategy_name,
            "symbol": strategy_config.get("symbol", ""),
            "timeframe": strategy_config.get("timeframe", ""),
            "walk_windows": [],
            "avg_is_sharpe": -999.0,
            "avg_oos_sharpe": -999.0,
            "sharpe_drop_pct": 0.0,
            "avg_oos_pf": 0.0,
            "avg_oos_wr": 0.0,
            "total_oos_trades": 0,
            "verdict": "SIN SEÑALES",
        }

    # Filter out -999 sentinel values for averaging
    is_sharpes = [
        w["is_sharpe"] for w in windows
        if isinstance(w["is_sharpe"], (int, float)) and w["is_sharpe"] != -999.0
    ]
    oos_sharpes = [
        w["oos_sharpe"] for w in windows
        if isinstance(w["oos_sharpe"], (int, float)) and w["oos_sharpe"] != -999.0
    ]
    oos_pfs = [
        w["oos_profit_factor"] for w in windows
        if isinstance(w["oos_profit_factor"], (int, float)) and w["oos_profit_factor"] != -999
    ]
    oos_wrs = [
        w["oos_win_rate"] for w in windows
        if isinstance(w["oos_win_rate"], (int, float)) and w["oos_win_rate"] != -999
    ]
    total_oos_trades = sum(
        w["oos_trades"] for w in windows if isinstance(w["oos_trades"], (int, float))
    )

    avg_is_sharpe = sum(is_sharpes) / len(is_sharpes) if is_sharpes else -999.0
    avg_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else -999.0

    sharpe_drop_pct = 0.0
    if avg_is_sharpe != -999.0 and avg_is_sharpe != 0:
        sharpe_drop_pct = (avg_is_sharpe - avg_oos_sharpe) / abs(avg_is_sharpe) * 100
    elif avg_is_sharpe == -999.0:
        sharpe_drop_pct = 100.0

    avg_oos_pf = sum(oos_pfs) / len(oos_pfs) if oos_pfs else 0.0
    avg_oos_wr = sum(oos_wrs) / len(oos_wrs) if oos_wrs else 0.0

    verdict = walk_forward_verdict(avg_oos_sharpe, sharpe_drop_pct, total_oos_trades, avg_is_sharpe)

    return {
        "strategy_name": strategy_name,
        "symbol": strategy_config.get("symbol", ""),
        "timeframe": strategy_config.get("timeframe", ""),
        "walk_windows": windows,
        "avg_is_sharpe": avg_is_sharpe,
        "avg_oos_sharpe": avg_oos_sharpe,
        "sharpe_drop_pct": sharpe_drop_pct,
        "avg_oos_pf": avg_oos_pf,
        "avg_oos_wr": avg_oos_wr,
        "total_oos_trades": total_oos_trades,
        "verdict": verdict,
    }


def walk_forward_verdict(
    avg_oos_sharpe: float,
    sharpe_drop_pct: float,
    total_oos_trades: int,
    avg_is_sharpe: float,
) -> str:
    """Classify walk-forward result into a verdict string.

    Args:
        avg_oos_sharpe: Average out-of-sample Sharpe ratio.
        sharpe_drop_pct: Percentage drop from IS to OOS Sharpe.
        total_oos_trades: Total number of OOS trades across all windows.
        avg_is_sharpe: Average in-sample Sharpe ratio.

    Returns:
        ``"ROBUSTO"``, ``"SOBREAJUSTADO"``, or ``"SIN SEÑALES"``.
    """
    if total_oos_trades == 0:
        return "SIN SEÑALES"
    if avg_is_sharpe == -999.0:
        return "SIN SEÑALES"
    if avg_oos_sharpe > 0.5 and sharpe_drop_pct < 50:
        return "ROBUSTO"
    if avg_oos_sharpe < 0 or sharpe_drop_pct >= 50:
        return "SOBREAJUSTADO"
    return "SOBREAJUSTADO"


def _print_walk_forward_table(
    console: Any,
    results: list[dict],
) -> None:
    """Print a Rich summary table with walk-forward results for all strategies."""
    if not _HAS_RICH or not console:
        print(f"\n{'=' * 60}")
        print("  WALK-FORWARD RESULTS")
        print(f"{'=' * 60}")
        for r in results:
            print(f"  Strategy: {r['strategy_name']}")
            print(f"    Verdict: {r['verdict']}")
            print(f"    IS Sharpe: {r['avg_is_sharpe']:.2f}  OOS Sharpe: {r['avg_oos_sharpe']:.2f}")
            print(f"    Drop: {r['sharpe_drop_pct']:.1f}%  OOS PF: {r['avg_oos_pf']:.2f}")
            print(f"    OOS WR: {r['avg_oos_wr']:.1f}%  Trades: {r['total_oos_trades']}")
            print()
        return

    table = Table(title="Walk-Forward Validation Results", box=None)
    table.add_column("Strategy", style="cyan")
    table.add_column("Symbol", style="yellow")
    table.add_column("TF")
    table.add_column("IS Sharpe", justify="right")
    table.add_column("OOS Sharpe", justify="right")
    table.add_column("Drop %", justify="right")
    table.add_column("OOS PF", justify="right")
    table.add_column("OOS WR", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Veredicto")

    verdict_styles = {
        "ROBUSTO": "green",
        "SOBREAJUSTADO": "red",
        "SIN SEÑALES": "white",
    }

    for r in results:
        verdict = r.get("verdict", "?")
        vstyle = verdict_styles.get(verdict, "")

        is_sharpe = r.get("avg_is_sharpe", -999)
        oos_sharpe = r.get("avg_oos_sharpe", -999)
        drop = r.get("sharpe_drop_pct", 0)
        pf = r.get("avg_oos_pf", 0)
        wr = r.get("avg_oos_wr", 0)
        trades = r.get("total_oos_trades", 0)

        is_str = f"{is_sharpe:.2f}" if is_sharpe != -999 else "N/A"
        oos_str = f"{oos_sharpe:.2f}" if oos_sharpe != -999 else "N/A"
        drop_str = f"{drop:.1f}%" if is_sharpe != -999 else "N/A"
        pf_str = f"{pf:.2f}" if pf != -999 else "N/A"
        wr_str = f"{wr:.1f}%" if wr != -999 else "N/A"

        table.add_row(
            r["strategy_name"],
            r.get("symbol", ""),
            r.get("timeframe", ""),
            is_str,
            oos_str,
            drop_str,
            pf_str,
            wr_str,
            str(trades),
            Text(verdict, style=vstyle) if vstyle else verdict,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Progress display helpers
# ---------------------------------------------------------------------------

def _print_header(console: Any, text: str) -> None:
    """Print a styled section header.

    Uses Rich ``console.rule()`` when available, falls back to ASCII.

    Args:
        console: Rich Console instance or ``None``.
        text: Header text to display.
    """
    if _HAS_RICH and console:
        console.rule(f"[bold cyan]{text}[/]", style="cyan")
    else:
        print(f"\n{'=' * 60}")
        print(f"  {text}")
        print(f"{'=' * 60}")


def _print_results_table(
    console: Any,
    results: list[dict],
    metric: str,
) -> None:
    """Print a Rich summary table with optimization results."""
    if not _HAS_RICH or not console:
        print(f"\n{'=' * 60}")
        print("  OPTIMIZATION RESULTS")
        print(f"{'=' * 60}")
        for r in results:
            bm = r.get("best_metrics", {})
            win_rate = bm.get("win_rate", "N/A")
            pf = bm.get("profit_factor", "N/A")
            dd = bm.get("max_drawdown", "N/A")

            print(f"  Strategy: {r['strategy']}")
            print(f"    Symbol: {r['symbol']}  Timeframe: {r['timeframe']}")
            print(f"    Trials: {r.get('trials_completed', '?')}")
            print(f"    Best {metric}: {r.get('best_value', 0):.4f}")
            if win_rate != "N/A":
                print(f"    Win Rate: {win_rate:.1f}%  Profit Factor: {pf:.2f}  Max DD: {dd:.1f}%")
            print(f"    Duration: {r.get('duration_seconds', 0):.1f}s")
            print()
        return

    table = Table(title="Optimization Results", box=None)
    table.add_column("Strategy", style="cyan")
    table.add_column("Symbol", style="yellow")
    table.add_column("TF")
    table.add_column("Trials")
    table.add_column(f"Best {metric}", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Profit Factor", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Duration", justify="right")

    for r in results:
        bv = r.get("best_value", 0)
        bm = r.get("best_metrics", {})
        val_style = "green" if bv > 0 else "red"

        wr = bm.get("win_rate", "N/A")
        pf = bm.get("profit_factor", "N/A")
        dd = bm.get("max_drawdown", "N/A")

        wr_str = f"{wr:.1f}%" if isinstance(wr, (int, float)) else "N/A"
        pf_str = f"{pf:.2f}" if isinstance(pf, (int, float)) else "N/A"
        dd_str = f"{dd:.1f}%" if isinstance(dd, (int, float)) else "N/A"
        dd_style = "green" if (isinstance(dd, (int, float)) and dd > -10) else "red"

        table.add_row(
            r["strategy"],
            r["symbol"],
            r["timeframe"],
            str(r.get("trials_completed", "?")),
            Text(f"{bv:.4f}", style=val_style),
            wr_str,
            pf_str,
            Text(dd_str, style=dd_style) if dd_str != "N/A" else "N/A",
            f"{r.get('duration_seconds', 0):.1f}s",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Saving helpers (Phase C stubs — will be used in PR 2)
# ---------------------------------------------------------------------------

def _update_strategy_yaml(strategy_config: dict, best_params: dict) -> bool:
    """Write best params back to the strategy's YAML file.

    Args:
        strategy_config: Original strategy config dict (must have ``_source_file``).
        best_params: Flat dict of best params from ``optimize_strategy()``.

    Returns:
        True if the YAML was updated, False on error.
    """
    from yaml import safe_load, dump
    src = strategy_config.get("_source_file")
    if not src:
        logger.warning("No _source_file for strategy — cannot update YAML")
        return False

    yaml_path = Path(src)
    if not yaml_path.exists():
        logger.warning("YAML file not found: {}", yaml_path)
        return False

    # Read the YAML file (list of strategy dicts)
    try:
        with open(yaml_path) as f:
            docs = safe_load(f)
    except Exception as exc:
        logger.error("Error reading {}: {}", yaml_path, exc)
        return False

    if not isinstance(docs, list):
        logger.warning("{} is not a list — cannot update", yaml_path)
        return False

    strategy_name = strategy_config.get("name", "")
    updated = False
    for doc in docs:
        if isinstance(doc, dict) and doc.get("name") == strategy_name:
            # Apply best params using apply_params logic
            merged = apply_params(doc, best_params)
            doc.clear()
            doc.update(merged)
            updated = True
            break

    if not updated:
        logger.warning("Strategy '{}' not found in {}", strategy_name, yaml_path)
        return False

    # Create .bak backup
    bak_path = yaml_path.with_suffix(".yaml.bak")
    try:
        shutil.copy2(str(yaml_path), str(bak_path))
    except Exception as exc:
        logger.warning("Could not create .bak backup: {}", exc)

    # Write updated YAML
    try:
        with open(yaml_path, "w") as f:
            dump(docs, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception as exc:
        logger.error("Error writing {}: {}", yaml_path, exc)
        return False

    logger.info("Updated {} with best params for '{}'", yaml_path.name, strategy_name)
    return True


def _save_partial_results(all_results: list[dict]) -> None:
    """Append optimization results to JSON log.

    Args:
        all_results: List of result dicts to append to the log file.
    """
    log_dir = _PROJECT_ROOT / "logs" / "optimization"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "optimization_results.json"

    existing: list[dict] = []
    if log_path.exists():
        try:
            with open(log_path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, Exception):
            existing = []

    existing.extend(all_results)

    with open(log_path, "w") as f:
        json.dump(existing, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the optimization script.

    Parses CLI arguments, loads/filters strategies, runs optimization or
    walk-forward validation per strategy, saves results, and sends Telegram
    notifications.
    """
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

    args = parse_args()

    console = Console(color_system="standard") if _HAS_RICH else None

    if args.validate:
        print("  [WARNING] --validate is not yet implemented (deferred to PR 2). "
              "Results will be from optimization only.")

    if args.walk_forward_integrated:
        print("  [WALK-FORWARD INTEGRATED] Using walk-forward objective "
              "(avg OOS Sharpe across 3 windows)")

    _print_header(console, "Loading strategies...")
    strategies = load_all_strategies()
    filtered = filter_strategies(strategies, args.strategy, args.symbols)

    if not filtered:
        print("No strategies matched. Available strategies:")
        for s in strategies:
            print(f"  - {s.get('name')} ({s.get('symbol')})")
        sys.exit(1)

    if _HAS_RICH and console:
        mode_desc = "walk-forward validation" if args.walk_forward else "walk-forward integrated" if args.walk_forward_integrated else "optimization"
        console.print(f"Loaded [cyan]{len(strategies)}[/] strategies, "
                      f"selected [green]{len(filtered)}[/] for {mode_desc}")

    # ── Walk-forward mode (replaces regular optimization) ────────────
    if args.walk_forward:
        _print_header(console, "WALK-FORWARD VALIDATION")

        wf_results: list[dict[str, Any]] = []
        wf_robustas: list[dict] = []
        wf_sobre: list[dict] = []
        wf_sin: list[dict] = []
        telegram_enabled = not args.no_telegram

        for strat_idx, strategy in enumerate(filtered, 1):
            name = strategy.get("name", f"strategy_{strat_idx}")
            symbol = strategy.get("symbol", "")
            timeframe = strategy.get("timeframe", "")
            n_trials = args.trials

            _print_header(console, f"({strat_idx}/{len(filtered)}) {name} — {symbol} {timeframe}")

            # Milestone: WF START
            if telegram_enabled:
                send_telegram(
                    f"[WF] VALIDACION WALK-FORWARD INICIADA\n"
                    f"Estrategia: {name}\n"
                    f"Ventanas: 5 ({n_trials} trials c/u)\n"
                    f"Símbolo: {symbol} | TF: {timeframe}"
                )

            # Data loading (same as regular mode)
            ohlcv = get_ohlcv(symbol, timeframe, force_download=args.force_download)
            if len(ohlcv) < 100:
                logger.warning("Insufficient data for {} — skipping", name)
                if telegram_enabled:
                    send_telegram(
                        f"[AVISO] WALK-FORWARD SIN DATOS\n"
                        f"Estrategia: {name}\n"
                        f"Error: datos insuficientes ({len(ohlcv)} velas)"
                    )
                continue

            if len(ohlcv) > 20_000:
                ohlcv = ohlcv.iloc[-20_000:].reset_index(drop=True)
                logger.info("Trimmed OHLCV to {} rows for performance", len(ohlcv))

            # Run walk-forward validation
            try:
                wf_result = walk_forward_validate(
                    strategy_name=name,
                    strategy_config=strategy,
                    ohlcv=ohlcv,
                    n_trials=n_trials,
                    metric=args.metric,
                    console=console,
                )
            except KeyboardInterrupt:
                print("\nWalk-forward interrupted by user.")
                break
            except Exception as exc:
                logger.exception("Walk-forward failed for {}: {}", name, exc)
                continue

            wf_results.append(wf_result)
            verdict = wf_result["verdict"]

            # Classify
            if verdict == "ROBUSTO":
                wf_robustas.append(wf_result)
            elif verdict == "SOBREAJUSTADO":
                wf_sobre.append(wf_result)
            else:
                wf_sin.append(wf_result)

            # Per-strategy console summary
            is_sharpe = wf_result["avg_is_sharpe"]
            oos_sharpe = wf_result["avg_oos_sharpe"]
            drop = wf_result["sharpe_drop_pct"]
            oos_pf = wf_result["avg_oos_pf"]
            oos_wr = wf_result["avg_oos_wr"]
            trades = wf_result["total_oos_trades"]

            if _HAS_RICH and console:
                vstyle = {"ROBUSTO": "green", "SOBREAJUSTADO": "red", "SIN SEÑALES": "white"}.get(verdict, "")
                console.print(
                    f"  Verdict: [bold {vstyle}]{verdict}[/]  |  "
                    f"IS Sharpe: {is_sharpe:.2f}  |  "
                    f"OOS Sharpe: {oos_sharpe:.2f}  |  "
                    f"Drop: {drop:.1f}%"
                )
            else:
                print(f"  Verdict: {verdict} | IS Sharpe: {is_sharpe:.2f} | OOS Sharpe: {oos_sharpe:.2f}")

            # Per-strategy Telegram notification
            if telegram_enabled:
                emoji = "[ROBUSTO]" if verdict == "ROBUSTO" else ("[SOBREAJUSTADO]" if verdict == "SOBREAJUSTADO" else "[SIN_TRADES]")
                send_telegram(
                    f"{emoji} <b>WALK-FORWARD: {verdict}</b>\n"
                    f"Estrategia: {name}\n"
                    f"IS Sharpe: {is_sharpe:.2f}\n"
                    f"OOS Sharpe: {oos_sharpe:.2f}\n"
                    f"Drop: {drop:.1f}%\n"
                    f"OOS PF: {oos_pf:.2f}\n"
                    f"OOS WR: {oos_wr:.1f}%\n"
                    f"Trades OOS: {trades}"
                )

        # ── End of walk-forward: summary, saving, YAML update ────────
        _print_walk_forward_table(console, wf_results)

        # Save full walk-forward results to JSON
        log_dir = _PROJECT_ROOT / "logs" / "optimization"
        log_dir.mkdir(parents=True, exist_ok=True)
        wf_path = log_dir / "walk_forward_results.json"
        with open(wf_path, "w") as f:
            json.dump(wf_results, f, indent=2, default=str)
        print(f"  Walk-forward results saved to {wf_path}")

        # Update YAML only for ROBUSTO strategies (last window's best params)
        yaml_count = 0
        for r in wf_robustas:
            strat_name = r["strategy_name"]
            strategy = find_strategy(strat_name, filtered)
            if strategy is None:
                continue
            windows = r.get("walk_windows", [])
            if not windows:
                continue
            last_params = windows[-1].get("best_params", {})
            if last_params:
                ok = _update_strategy_yaml(strategy, last_params)
                if ok:
                    yaml_count += 1

        if yaml_count > 0:
            print(f"  YAML updated for {yaml_count} ROBUSTO strategy(s).")

        # Final Telegram summary
        total_wf = len(wf_results)
        if telegram_enabled and total_wf > 0:
            send_telegram(
                f"[FIN] WALK-FORWARD COMPLETADO — {total_wf} estrategias\n"
                f"  Robusta: {len(wf_robustas)}\n"
                f"  Sobreajustada: {len(wf_sobre)}\n"
                f"  Sin trades: {len(wf_sin)}\n"
                f"YAMLs actualizados: {yaml_count}"
            )

        print(f"\nDone. {total_wf} strategy(s) validated via walk-forward.")
        return

    # ── Regular optimization mode ─────────────────────────────────────
    all_results: list[dict[str, Any]] = []
    telegram_enabled = not args.no_telegram
    strategies_ok: list[str] = []
    strategies_no_signals: list[str] = []
    strategies_failed: list[str] = []
    best_global_sharpe = -999.0
    best_global_strategy = ""
    total_start = time.time()

    for strat_idx, strategy in enumerate(filtered, 1):
        name = strategy.get("name", f"strategy_{strat_idx}")
        symbol = strategy.get("symbol", "")
        timeframe = strategy.get("timeframe", "1d")
        n_trials = args.trials

        _print_header(console, f"({strat_idx}/{len(filtered)}) {name} — {symbol} {timeframe}")

        # ── Milestone 1: STRATEGY START ─────────────────────────────────
        if telegram_enabled:
            send_telegram(
                f"[INICIO] OPTIMIZACION INICIADA\n"
                f"Estrategia: {name}\n"
                f"Timeframe: {timeframe} | Trials: {n_trials}\n"
                f"Símbolo: {symbol}\n"
                f"Inicio: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
            )

        # Data loading
        data_start = time.time()
        _print_header(console, f"Loading data for {symbol}...")
        ohlcv = get_ohlcv(symbol, timeframe, force_download=args.force_download)
        if len(ohlcv) < 100:
            logger.warning("Insufficient data for {} — skipping", name)
            if telegram_enabled:
                send_telegram(
                    f"[AVISO] OPTIMIZACION SIN DATOS\n"
                    f"Estrategia: {name}\n"
                    f"Error: datos insuficientes ({len(ohlcv)} velas)"
                )
            strategies_failed.append(name)
            continue

        # Reduce data size for faster optuna if very large (10k+ bars)
        if len(ohlcv) > 20_000:
            # Resample to a reasonable size: keep last 20k bars
            ohlcv = ohlcv.iloc[-20_000:].reset_index(drop=True)
            logger.info("Trimmed OHLCV to {} rows for performance", len(ohlcv))

        # Run optimization
        opt_start = time.time()

        try:
            if args.walk_forward_integrated:
                result = optimize_strategy_wf_integrated(
                    strategy_name=name,
                    strategy_config=strategy,
                    ohlcv=ohlcv,
                    n_trials=n_trials,
                    metric=args.metric,
                    console=console,
                )
            else:
                result = optimize_strategy(
                    strategy_name=name,
                    strategy_config=strategy,
                    ohlcv=ohlcv,
                    n_trials=n_trials,
                    metric=args.metric,
                    console=console,
                )
        except KeyboardInterrupt:
            print("\nOptimization interrupted by user.")
            break
        except Exception as exc:
            logger.exception("Optimization failed for {}: {}", name, exc)
            # ── Milestone 4: STRATEGY FAILED ────────────────────────────
            if telegram_enabled:
                send_telegram(
                    f"[ERROR] OPTIMIZACION FALLIDA\n"
                    f"Estrategia: {name}\n"
                    f"Error: {exc}\n"
                    f"Parámetros: se mantienen los actuales"
                )
            strategies_failed.append(name)
            continue

        opt_duration = time.time() - opt_start

        result_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": name,
            "symbol": symbol,
            "timeframe": timeframe,
            "trials_completed": result.get("trials_completed", n_trials),
            "best_trial_number": result.get("best_trial", -1),
            "best_params": result.get("best_params", {}),
            "best_metrics": result.get("best_metrics", {}),
            "worst_metrics": result.get("worst_metrics", {}),
            "duration_seconds": round(opt_duration, 1),
        }
        all_results.append(result_entry)

        # Print per-strategy summary
        bv = result.get("best_value", -999)
        bm = result.get("best_metrics", {})

        if _HAS_RICH and console:
            style = "green" if bv > 0 else "red"
            console.print(f"[green]OK[/] {name} — best {args.metric}: "
                          f"[bold {style}]{bv:.4f}[/] "
                          f"({opt_duration:.1f}s)")
        else:
            print(f"  OK {name} — best {args.metric}: "
                  f"{bv:.4f} "
                  f"({opt_duration:.1f}s)")

        # Track best global
        if bv > best_global_sharpe:
            best_global_sharpe = bv
            best_global_strategy = name

        # ── Milestones 2 & 3: SUCCESS vs NO SIGNALS ─────────────────────
        if bv <= -999.0:
            if telegram_enabled:
                send_telegram(
                    f"[AVISO] OPTIMIZACION SIN SENIALES\n"
                    f"Estrategia: {name}\n"
                    f"Trials: {result.get('trials_completed', n_trials)}/{n_trials}\n"
                    f"Resultado: 0 trades en todos los trials\n"
                    f"Parámetros: se mantienen los actuales"
                )
            strategies_no_signals.append(name)
        else:
            wr = bm.get("win_rate", "N/A")
            pf = bm.get("profit_factor", "N/A")
            dd = bm.get("max_drawdown", "N/A")
            wr_str = f"{wr:.1f}%" if isinstance(wr, (int, float)) else "N/A"
            pf_str = f"{pf:.2f}" if isinstance(pf, (int, float)) else "N/A"
            dd_str = f"{dd:.1f}%" if isinstance(dd, (int, float)) else "N/A"
            if telegram_enabled:
                send_telegram(
                    f"[OK] OPTIMIZACION COMPLETA\n"
                    f"Estrategia: {name}\n"
                    f"Trials: {result.get('trials_completed', n_trials)}/{n_trials}\n"
                    f"Mejor {args.metric}: {bv:.4f}\n"
                    f"Win Rate: {wr_str}\n"
                    f"Profit Factor: {pf_str}\n"
                    f"Max DD: {dd_str}\n"
                    f"Parametros actualizados: {'OK' if not args.no_save else 'NO (--no-save)'}\n"
                    f"Duracion: {opt_duration:.0f}s"
                )
            strategies_ok.append(name)

    # ── Final summary ──────────────────────────────────────────────────
    _print_results_table(console, all_results, args.metric)
    _save_partial_results(all_results)

    # ── YAML auto-update ───────────────────────────────────────────────
    yaml_updated = 0
    yaml_failed = 0
    for r in all_results:
        strategy_name = r["strategy"]
        strategy = find_strategy(strategy_name, filtered)
        if strategy is None:
            continue
        best_params = r.get("best_params", {})
        if not best_params:
            continue

        if not args.no_save:
            ok = _update_strategy_yaml(strategy, best_params)
            if ok:
                yaml_updated += 1
            else:
                yaml_failed += 1

    if yaml_updated > 0:
        print(f"  YAML updated for {yaml_updated} strategy(s).")
    if yaml_failed > 0:
        print(f"  YAML update FAILED for {yaml_failed} strategy(s).")
    if args.no_save:
        print("  (--no-save: YAML not modified)")
    elif yaml_updated == 0 and yaml_failed == 0:
        print("  (No strategies had best_params to save)")

    # ── Milestone 5: FINAL SUMMARY ─────────────────────────────────────
    total_duration = time.time() - total_start
    total_min = int(total_duration // 60)
    total_sec = int(total_duration % 60)
    if telegram_enabled and all_results:
        best_global_name = best_global_strategy or "—"
        best_global_val = f"{best_global_sharpe:.4f}" if best_global_sharpe > -999 else "ninguno (sin señales)"
        send_telegram(
            f"[FIN] OPTIMIZACION COMPLETA — {len(all_results)}/{len(filtered)} estrategias\n"
            f"  Optimizadas: {len(strategies_ok)}\n"
            f"  Sin seniales: {len(strategies_no_signals)}\n"
            f"  Fallidas: {len(strategies_failed)}\n"
            f"Mejor {args.metric} global: {best_global_val} ({best_global_name})\n"
            f"Duración total: {total_min}m {total_sec}s\n"
            f"YAMLs actualizados: {yaml_updated if not args.no_save else 0}\n"
            f"Hot reload: activo"
        )

    print(f"\nDone. {len(all_results)} strategy(s) optimized.")


if __name__ == "__main__":
    main()
