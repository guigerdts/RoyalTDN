"""Backtesting engine for DynamicStrategy.

Downloads data via yfinance, generates signals via DynamicStrategy,
simulates portfolio returns, and computes metrics.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd


# ── Timeframe mapping ───────────────────────────────────────────────────

YF_PERIOD_MAP: dict[str, str] = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "730d",
    "1H": "730d",
    "4H": "730d",
    "1d": "5y",
    "1D": "5y",
}

YF_INTERVAL_MAP: dict[str, str] = {
    "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
    "1H": "1h", "4H": "1h",
    "1D": "1d",
}

PERIOD_DAYS_MAP: dict[str, int] = {
    "1 month": 30, "3 months": 90, "6 months": 180,
    "1 year": 365, "2 years": 730, "5 years": 1825,
}


def _download_data(
    symbol: str, timeframe: str, period: str, max_retries: int = 2,
) -> Optional[pd.DataFrame]:
    """Download OHLCV data from yfinance."""
    import yfinance as yf

    interval = YF_INTERVAL_MAP.get(timeframe, "1d")
    yf_period = YF_PERIOD_MAP.get(interval, "1y")

    # Map user period to exact number of days for start
    days = PERIOD_DAYS_MAP.get(period, 365)
    start = pd.Timestamp.now() - pd.Timedelta(days=days)

    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, interval=interval, auto_adjust=True)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                # Rename 'adj close' to 'close' if present
                if "adj close" in df.columns:
                    df["close"] = df["adj close"]
                # Ensure standard columns
                required = {"open", "high", "low", "close", "volume"}
                if required.issubset(df.columns):
                    return df
        except Exception:
            if attempt == max_retries - 1:
                raise
    return None


def _compute_metrics(pf_close: pd.Series, trades_df: pd.DataFrame) -> dict:
    """Compute performance metrics from portfolio equity and trades."""
    if pf_close.empty or len(pf_close) < 2:
        return {"error": "Insufficient data for metrics"}

    # Total return
    total_return = (pf_close.iloc[-1] / pf_close.iloc[0]) - 1

    # CAGR
    years = len(pf_close) / 252  # trading days per year
    cagr = (pf_close.iloc[-1] / pf_close.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0

    # Daily returns
    daily_returns = pf_close.pct_change().dropna()

    # Sharpe (risk-free = 0, annualized)
    sharpe = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() > 0 else 0.0

    # Sortino (downside deviation)
    downside = daily_returns[daily_returns < 0]
    sortino = np.sqrt(252) * daily_returns.mean() / downside.std() if len(downside) > 0 and downside.std() > 0 else 0.0

    # Max drawdown
    cummax = pf_close.cummax()
    drawdown = (pf_close - cummax) / cummax
    max_dd = drawdown.min()

    # Trade stats
    num_trades = len(trades_df) if trades_df is not None else 0

    if trades_df is not None and num_trades > 0:
        win_rate = (trades_df["pnl"] > 0).mean()
        avg_win = trades_df.loc[trades_df["pnl"] > 0, "pnl"].mean() if (trades_df["pnl"] > 0).any() else 0.0
        avg_loss = trades_df.loc[trades_df["pnl"] < 0, "pnl"].mean() if (trades_df["pnl"] < 0).any() else 0.0
        profit_factor = abs(
            trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum()
            / trades_df.loc[trades_df["pnl"] < 0, "pnl"].sum()
        ) if (trades_df["pnl"] < 0).any() else float("inf")
        avg_trade = trades_df["pnl"].mean()
        max_win = trades_df["pnl"].max()
        max_loss = trades_df["pnl"].min()
        total_fees = trades_df["fees"].sum() if "fees" in trades_df.columns else 0.0
    else:
        win_rate = avg_win = avg_loss = profit_factor = avg_trade = 0.0
        max_win = max_loss = total_fees = 0.0

    # Compute new metrics
    # sortino_ratio (same as sortino, keep as alias)
    sortino_ratio = float(sortino)

    # calmar_ratio: CAGR / abs(max_drawdown)
    if max_dd != 0:
        calmar_ratio = float(cagr) / abs(float(max_dd))
    else:
        calmar_ratio = float(cagr)

    # expectancy: (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
    if num_trades > 0:
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
    else:
        expectancy = 0.0

    # avg_trade_duration: mean of (exit_date - entry_date) in hours
    avg_trade_duration = 0.0
    if trades_df is not None and num_trades > 0:
        durations = []
        for _, row in trades_df.iterrows():
            entry_str = row.get("entry_date")
            exit_str = row.get("exit_date")
            if entry_str and exit_str:
                try:
                    entry_dt = pd.Timestamp(entry_str)
                    exit_dt = pd.Timestamp(exit_str)
                    delta_hours = (exit_dt - entry_dt).total_seconds() / 3600
                    durations.append(delta_hours)
                except Exception:
                    continue
        if durations:
            avg_trade_duration = float(sum(durations) / len(durations))

    return {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "sortino_ratio": float(sortino_ratio),
        "calmar_ratio": float(calmar_ratio),
        "expectancy": float(expectancy),
        "avg_trade_duration": float(avg_trade_duration),
        "max_drawdown": float(max_dd),
        "num_trades": int(num_trades),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
        "avg_trade": float(avg_trade),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "max_win": float(max_win),
        "max_loss": float(max_loss),
        "total_fees": float(total_fees),
    }


def run_backtest(
    config: dict,
    symbol: str = "SPY",
    timeframe: str = "1D",
    period: str = "2 years",
    init_cash: float = 10_000.0,
    fee_pct: float = 0.001,  # 0.1%
    slippage_pct: float = 0.0005,  # 0.05%
) -> dict:
    """Run a full backtest for a DynamicStrategy config.

    Args:
        config: Strategy config dict.
        symbol: Ticker symbol.
        timeframe: Timeframe (1min, 5min, 15min, 1H, 1D).
        period: User-friendly period string.
        init_cash: Initial capital.
        fee_pct: Fee per trade as fraction.
        slippage_pct: Slippage per trade as fraction.

    Returns:
        Dict with keys: metrics (dict), equity_series (list), drawdown_series (list),
        trades (list), daily_returns (list), buy_hold_equity (list), error (str, optional).
    """
    from royaltdn.strategy.dynamic import DynamicStrategy

    # Validate config
    from royaltdn.strategy.schema import validate_config
    ok, err = validate_config(config)
    if not ok:
        return {"error": f"Invalid config: {err}"}

    # Download data
    df = _download_data(symbol, timeframe, period)
    if df is None or df.empty:
        return {"error": f"Could not download data for {symbol}"}

    # Ensure enough data
    min_bars = 50
    if len(df) < min_bars:
        return {"error": f"Insufficient data: {len(df)} bars, need at least {min_bars}"}

    # Instantiate strategy
    try:
        strat = DynamicStrategy(config)
    except Exception as e:
        return {"error": f"Strategy instantiation failed: {e}"}

    # Generate signals iteratively (walk forward)
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)

    in_position = False
    from tqdm import tqdm
    for i in tqdm(
        range(1, len(df)),
        desc=f"{symbol} {timeframe} ({period})",
        bar_format="{desc} — {n}/{total} barras {bar} {percentage:.0f}% [{elapsed}<{remaining}]",
        file=sys.stdout,
    ):
        window = df.iloc[: i + 1]
        try:
            signal = strat.generate_signal(window)
        except Exception:
            signal = None

        if signal is not None:
            if signal["action"] == "BUY" and not in_position:
                entries.iloc[i] = True
                in_position = True
            elif signal["action"] == "SELL" and in_position:
                exits.iloc[i] = True
                in_position = False

    # Force close at end
    if in_position:
        exits.iloc[-1] = True

    # No trades
    if not entries.any():
        return {
            "error": "No trades generated — strategy rules did not trigger",
            "metrics": _compute_metrics(pd.Series([init_cash] * len(df), index=df.index), None),
            "equity_series": [init_cash] * len(df),
            "drawdown_series": [0.0] * len(df),
            "trades": [],
            "daily_returns": [0.0] * len(df),
            "buy_hold_equity": (df["close"] / df["close"].iloc[0] * init_cash).tolist(),
        }

    # Simulate portfolio
    close = df["close"]
    equity = np.zeros(len(df))
    equity[0] = init_cash
    cash = init_cash
    position = 0.0
    entry_price = 0.0
    trades_list = []

    for i in tqdm(
        range(1, len(df)),
        desc="Simulando cartera",
        bar_format="{desc} — {n}/{total} barras {bar} {percentage:.0f}% [{elapsed}<{remaining}]",
        file=sys.stdout,
    ):
        price = close.iloc[i]

        if entries.iloc[i]:
            # Buy with slippage
            buy_price = price * (1 + slippage_pct)
            fee = cash * fee_pct
            position = (cash - fee) / buy_price
            entry_price = buy_price
            cash = 0.0

        elif exits.iloc[i]:
            # Sell with slippage
            sell_price = price * (1 - slippage_pct)
            gross = position * sell_price
            fee = gross * fee_pct
            pnl = gross - fee - (position * entry_price)
            cash = gross - fee
            trades_list.append({
                "entry_date": str(df.index[i]),
                "exit_date": str(df.index[i]),
                "entry_price": float(entry_price),
                "exit_price": float(sell_price),
                "pnl": float(pnl),
                "return_pct": float(pnl / (position * entry_price) * 100) if position * entry_price > 0 else 0.0,
                "fees": float(fee),
            })
            position = 0.0
            entry_price = 0.0

        equity[i] = cash + (position * price) if position > 0 else cash

    # Fix first position entry_date if we entered on bar 1
    # Actually entries trigger at specific bars, we capture pnl on exit
    # Better: log entry events too

    # Rebuild trades with entry/exit dates
    equity_series = pd.Series(equity, index=df.index)
    daily_returns = equity_series.pct_change().fillna(0)

    # Drawdown
    cummax = equity_series.cummax()
    drawdown = (equity_series - cummax) / cummax

    # Buy & hold
    bh_equity = close / close.iloc[0] * init_cash

    # Compute metrics
    metrics = _compute_metrics(equity_series, pd.DataFrame(trades_list) if trades_list else None)

    # Attach entry dates to trades
    entry_indices = entries[entries].index.tolist()
    exit_indices = exits[exits].index.tolist()
    for idx, trade in enumerate(trades_list):
        if idx < len(entry_indices):
            trade["entry_date"] = str(entry_indices[idx])
        if idx < len(exit_indices):
            trade["exit_date"] = str(exit_indices[idx])

    return {
        "metrics": metrics,
        "equity_series": equity.tolist(),
        "drawdown_series": drawdown.fillna(0).tolist(),
        "trades": trades_list,
        "daily_returns": daily_returns.tolist(),
        "buy_hold_equity": bh_equity.tolist(),
        "dates": [str(d) for d in df.index],
        "prices": close.tolist(),
    }


def _display_backtest_trades(trades: list, console) -> None:
    """Render a Rich table with backtest trade details.

    Columns: #, Entry Date, Exit Date, Entry Price, Exit Price, P&L, Return %, Duration, Fees.
    P&L >= 0 in green, P&L < 0 in red.
    Duration = (exit_date - entry_date) in days with 1 decimal.
    Empty list shows a yellow warning message.
    """
    from rich.table import Table

    if not trades:
        console.print("[bold yellow]\u26a0\ufe0f No se generaron trades en este per\u00edodo.[/]")
        return

    table = Table(
        title=None,
        border_style="white",
        header_style="bold white",
    )
    table.add_column("#", style="bold cyan")
    table.add_column("Entry Date")
    table.add_column("Exit Date")
    table.add_column("Entry Price", justify="right")
    table.add_column("Exit Price", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("Return %", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Fees", justify="right")

    for idx, t in enumerate(trades, start=1):
        if not isinstance(t, dict):
            continue
        entry_date = t.get("entry_date", "")
        exit_date = t.get("exit_date", "")
        entry_price = f"${float(t.get('entry_price', 0)):.2f}"
        exit_price = f"${float(t.get('exit_price', 0)):.2f}"
        pnl_raw = float(t.get("pnl", 0))
        pnl_style = "bold green" if pnl_raw >= 0 else "bold red"
        pnl_str = f"${pnl_raw:+,.2f}"
        return_pct = f"{float(t.get('return_pct', 0)):.2f}%"

        # Duration in days
        duration_str = "\u2014"
        if entry_date and exit_date:
            try:
                from datetime import datetime as _dt
                ed = _dt.fromisoformat(str(entry_date).replace("Z", "+00:00"))
                xd = _dt.fromisoformat(str(exit_date).replace("Z", "+00:00"))
                delta_days = (xd - ed).total_seconds() / 86400
                duration_str = f"{delta_days:.1f}d"
            except (ValueError, TypeError):
                pass

        fees = f"${float(t.get('fees', 0)):.2f}"

        table.add_row(
            str(idx),
            entry_date,
            exit_date,
            entry_price,
            exit_price,
            f"[{pnl_style}]{pnl_str}[/]",
            return_pct,
            duration_str,
            fees,
        )

    console.print(table)


def _display_buy_hold_comparison(
    buy_hold_equity: list | None, metrics: dict, console,
) -> None:
    """Render a Buy & Hold comparison panel.

    Computes BH return, BH CAGR, and strategy vs BH difference.
    Shows "No disponible" in gray if data is missing.
    """
    from rich.panel import Panel
    from rich.table import Table

    if not buy_hold_equity or len(buy_hold_equity) < 2:
        console.print(Panel(
            "[dim]No disponible[/]",
            title="\U0001f4ca  Comparaci\u00f3n: Estrategia vs Buy & Hold",
            border_style="white",
        ))
        return

    bh_return = (buy_hold_equity[-1] / buy_hold_equity[0]) - 1
    # BH CAGR annualized
    years = len(buy_hold_equity) / 252
    bh_cagr = (buy_hold_equity[-1] / buy_hold_equity[0]) ** (1 / years) - 1 if years > 0 else 0.0
    strat_return = metrics.get("total_return", 0)
    diff = strat_return - bh_return

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right")
    table.add_row("Buy & Hold Return", f"{bh_return * 100:.2f}%")
    table.add_row("Buy & Hold CAGR", f"{bh_cagr * 100:.2f}%")
    table.add_row("Estrategia vs B&H", f"{diff * 100:+.2f}%")

    console.print(Panel(
        table,
        title="\U0001f4ca  Comparaci\u00f3n: Estrategia vs Buy & Hold",
        border_style="white",
    ))


def config_hash(config: dict, symbol: str, timeframe: str, period: str) -> str:
    """Create a deterministic hash for caching."""
    raw = json.dumps(config, sort_keys=True) + f"|{symbol}|{timeframe}|{period}"
    return hashlib.sha256(raw.encode()).hexdigest()
