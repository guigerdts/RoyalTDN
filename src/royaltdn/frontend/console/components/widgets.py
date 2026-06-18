"""Widget renderables — pure Rich components for the console TUI.

Every function in this module is a **pure renderable factory**: it receives
data (dicts / lists) and returns a ``Panel``, ``Table``, or ``Layout``.
None write to the terminal directly.  All handle empty/missing data
gracefully.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

# ── Colour palette (aliases) ──────────────────────────────────────────────
GREEN = "green"
RED = "red"
YELLOW = "yellow"
BLUE = "blue"
CYAN = "cyan"
GRAY = "bright_black"
WHITE = "white"

_SECONDS_FMT = "{:d}h {:02d}m {:02d}s"


def _fmt_duration(seconds: Optional[float]) -> str:
    """Format seconds to ``Xh Ym Zs``."""
    if seconds is None:
        return "—"
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return _SECONDS_FMT.format(h, m, s)


def _fmt_pnl(value: Optional[float], suffix: str = "") -> Text:
    """Return a coloured ``Text`` for a P&L value."""
    if value is None:
        return Text("—", style=GRAY)
    sign = "+" if value >= 0 else ""
    colour = GREEN if value >= 0 else RED
    return Text(f"{sign}{value:.2f}{suffix}", style=colour)


def _fmt_time(ts: Any) -> str:
    """Format a timestamp to ``HH:MM:SS`` or return ``—``."""
    if not ts:
        return "—"
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%H:%M:%S")
        return str(ts)
    except (ValueError, TypeError):
        return str(ts)


def _val_or_dash(value: Any, fmt: str = "{}") -> str:
    """Return a formatted value or ``—`` if ``None`` / empty / 0-length."""
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        if fmt == "{:.2f}":
            return f"{value:.2f}"
        if fmt == "{:.0f}":
            return f"{value:.0f}"
        return fmt.format(value)
    if isinstance(value, str) and value.strip() == "":
        return "—"
    if isinstance(value, (list, dict)) and not value:
        return "—"
    return str(value)


# ── Widget implementations ───────────────────────────────────────────────


def create_header(state: dict) -> Panel:
    """Build the top header panel.

    Displays the bot title, operating mode, status badge (colour-coded),
    uptime, and scanner next-scan countdown.
    """
    status = state.get("status", {})

    mode = status.get("mode", "—").upper()
    bot_status = status.get("bot_status", "OFFLINE")
    uptime_sec = status.get("uptime_seconds")
    scanner_enabled = status.get("scanner_enabled", False)

    # Status badge
    status_colour = {  # noqa: F841 – used below
        "ONLINE": GREEN,
        "OFFLINE": RED,
        "KILLED": YELLOW,
    }.get(bot_status, RED)
    badge = f"[{status_colour} bold]{bot_status}[/]"

    # Uptime
    uptime_str = _fmt_duration(uptime_sec) if uptime_sec else "—"

    # Scanner countdown (approximate from status timestamp)
    scanner_info = "Activo" if scanner_enabled else "Inactivo"
    mode_colour = CYAN if mode == "MODULAR" else YELLOW

    title_text = (
        f"[bold white]⚡ ROYALTDN BOT[/]\n"
        f"[{mode_colour}]{mode}[/]  |  Estado: {badge}\n"
        f"Uptime: [white]{uptime_str}[/]  |  Scanner: {scanner_info}"
    )

    return Panel(title_text, style=WHITE, border_style=CYAN)


def create_kpi_cards(state: dict) -> Table:
    """Render KPI summary row: Capital, P&L Día, Drawdown, Win Rate."""
    equity = state.get("equity", {})
    trades = state.get("trades", {})

    capital = equity.get("current_equity")
    capital_str = _val_or_dash(capital, "{:.2f}")
    capital_style = GREEN if (capital or 0) > 0 else (RED if (capital or 0) < 0 else WHITE)

    pnl_day = equity.get("pnl_day")
    pnl_str = _val_or_dash(pnl_day, "{:.2f}")
    pnl_style = GREEN if (pnl_day or 0) > 0 else (RED if (pnl_day or 0) < 0 else WHITE)

    dd_pct = equity.get("drawdown_pct")
    dd_str = _val_or_dash(dd_pct, "{:.2f}%")
    dd_style = RED if (dd_pct or 0) < -5 else (YELLOW if (dd_pct or 0) < 0 else WHITE)

    win_rate = trades.get("win_rate")
    wr_str = _val_or_dash(win_rate, "{:.1f}%")

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="center")
    table.add_column(justify="center")
    table.add_column(justify="center")
    table.add_column(justify="center")

    table.add_row(
        f"[{capital_style} bold]{capital_str}[/]",
        f"[{pnl_style} bold]{pnl_str}[/]",
        f"[{dd_style} bold]{dd_str}[/]",
        f"[white bold]{wr_str}[/]",
    )
    # Sub-header row
    table.add_row(
        "[dim]Capital[/]",
        "[dim]P&L Día[/]",
        "[dim]Drawdown[/]",
        "[dim]Win Rate[/]",
    )
    return table


def create_positions_table(state: dict) -> Table:
    """Render open positions (Symbol, Qty, Entry P, Current P, P&L, Duration)."""
    positions_data = state.get("positions", {})
    positions = positions_data.get("open_positions", [])

    table = Table(
        title="Posiciones Abiertas",
        title_style="bold white",
        header_style=CYAN,
        border_style=GRAY,
    )
    table.add_column("Symbol", style=WHITE)
    table.add_column("Qty", justify="right")
    table.add_column("Entry P", justify="right")
    table.add_column("Current P", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("Duration", justify="center")

    if not positions:
        table.add_row("[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]")
        return table

    now = datetime.now(timezone.utc)

    for pos in positions:
        qty = pos.get("qty", 0)
        entry_p = pos.get("entry_price")
        curr_p = pos.get("current_price")
        pnl = pos.get("pnl_unrealized")
        entry_at = pos.get("entry_at")

        # Duration
        duration = "—"
        if entry_at:
            try:
                entry_dt = datetime.fromisoformat(entry_at)
                if entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                delta = now - entry_dt
                duration = _fmt_duration(delta.total_seconds())
            except (ValueError, TypeError):
                pass

        pnl_text = _fmt_pnl(pnl)

        table.add_row(
            str(pos.get("symbol", "—")),
            str(qty),
            _val_or_dash(entry_p, "{:.2f}"),
            _val_or_dash(curr_p, "{:.2f}"),
            pnl_text,
            duration,
        )

    return table


def create_signals_table(signals: list) -> Table:
    """Render a signals list (Time, Symbol, Action, Price, Strategy)."""
    table = Table(
        title="Últimas Señales",
        title_style="bold white",
        header_style=CYAN,
        border_style=GRAY,
    )
    table.add_column("Time", justify="center")
    table.add_column("Symbol", style=WHITE)
    table.add_column("Action", justify="center")
    table.add_column("Price", justify="right")
    table.add_column("Strategy")

    if not signals:
        table.add_row("[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]")
        return table

    for sig in signals[:10]:  # show at most 10
        action = sig.get("action", "").upper()
        action_style = GREEN if action in ("BUY", "COMPRA", "LONG") else RED
        table.add_row(
            _fmt_time(sig.get("time")),
            str(sig.get("symbol", "—")),
            f"[{action_style} bold]{action}[/]",
            _val_or_dash(sig.get("price"), "{:.4f}"),
            str(sig.get("strategy", "—")),
        )

    return table


def create_risk_panel(state: dict) -> Panel:
    """Render a risk summary with drawdown progress bar and consecutive losses."""
    equity = state.get("equity", {})
    dd_pct = equity.get("drawdown_pct", 0) or 0
    dd_abs = equity.get("drawdown", 0) or 0
    trades_data = state.get("trades", {})

    # Count consecutive losses from trades list
    trades_list = trades_data.get("trades", [])
    consec_losses = 0
    for t in reversed(trades_list):
        pnl = t.get("pnl", 0)
        if pnl < 0:
            consec_losses += 1
        else:
            break

    # Drawdown progress bar (show as positive percentage for visual)
    dd_bar_pct = min(abs(dd_pct) / 100.0, 1.0)  # normalise 0–100 → 0–1
    bar_colour = RED if abs(dd_pct) > 5 else YELLOW if abs(dd_pct) > 2 else GREEN
    bar = ProgressBar(total=1.0, completed=dd_bar_pct, width=40)

    consec_style = RED if consec_losses >= 3 else YELLOW if consec_losses >= 1 else GREEN

    # Build content via Table.grid (acts as a vertical container for mixed renderables)
    content = Table.grid(padding=(0, 0))
    content.add_column()
    content.add_row(Text("Daily Drawdown", style="bold"))
    content.add_row(bar)
    content.add_row(Text(f"{abs(dd_pct):.2f}%  ({abs(dd_abs):.2f} USD)"))
    content.add_row(Text(""))
    content.add_row(
        Text.assemble(
            ("Consecutive Losses: ", "bold"),
            (str(consec_losses), consec_style),
        )
    )
    if abs(dd_pct) > 5:
        content.add_row(Text("⚠️  CRITICAL DRAWDOWN — review risk settings", style="bold red"))

    return Panel(content, title="[bold white]Riesgo[/]", border_style=bar_colour)


def create_scanner_table(scanner_data: dict) -> Table:
    """Render scanner results table (Symbol, Strategy, Action, Price, Score, Time)."""
    last_scan = scanner_data.get("last_scan", {})
    signals = last_scan.get("top_signals", []) if last_scan else []

    last_scan_time = last_scan.get("timestamp", "—") if last_scan else "—"
    total_signals = last_scan.get("total_signals", 0) if last_scan else 0

    table = Table(
        title=f"Scanner — Último: {_fmt_time(last_scan_time)}  |  Señales: {total_signals}",
        title_style="bold white",
        header_style=CYAN,
        border_style=GRAY,
    )
    table.add_column("Symbol", style=WHITE)
    table.add_column("Strategy")
    table.add_column("Action", justify="center")
    table.add_column("Price", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Time", justify="center")

    if not signals:
        table.add_row("[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]")
        return table

    for sig in signals:
        action = sig.get("action", "").upper()
        action_style = GREEN if action in ("BUY", "COMPRA", "LONG") else RED
        score = sig.get("score")
        score_str = f"{score:.2f}" if score is not None else "—"

        table.add_row(
            str(sig.get("symbol", "—")),
            str(sig.get("strategy", "—")),
            f"[{action_style} bold]{action}[/]",
            _val_or_dash(sig.get("price"), "{:.4f}"),
            score_str,
            _fmt_time(sig.get("time")),
        )

    return table


def create_strategies_table(strategies_data: dict, user_strategies: dict) -> Table:
    """Render all strategies (predefined + user) in one table.

    Columns: Name, Status, Params.
    """
    table = Table(
        title="Estrategias",
        title_style="bold white",
        header_style=CYAN,
        border_style=GRAY,
    )
    table.add_column("Nombre", style=WHITE)
    table.add_column("Estado", justify="center")
    table.add_column("Parámetros")

    has_rows = False

    # Predefined strategies
    predefined = strategies_data.get("strategies", []) if strategies_data else []
    for strat in predefined:
        has_rows = True
        name = strat.get("name", "—")
        active = strat.get("active", False)
        validated = strat.get("validation", True)
        params = strat.get("params", {})

        if not validated:
            status = "[red bold]❌[/]"
        elif active:
            status = f"[{GREEN} bold]✅ Activa[/]"
        else:
            status = "[dim]Inactiva[/]"

        params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "[dim]—[/]"
        table.add_row(name, status, params_str)

    # User strategies
    user_list = user_strategies.get("strategies", []) if user_strategies else []
    for strat in user_list:
        has_rows = True
        name = strat.get("name", "—")
        active = strat.get("active", False)
        params = strat.get("params", {})

        status = f"[{GREEN} bold]✅[/]" if active else "[dim]Inactiva[/]"
        params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "[dim]—[/]"
        table.add_row(f"  ⤷ {name}", status, params_str)

    if not has_rows:
        table.add_row("[dim]—[/]", "[dim]—[/]", "[dim]—[/]")

    return table


def create_trades_table(trades: list) -> Table:
    """Render closed trades (Entry/Exit Time, Symbol, Strategy, Prices, P&L)."""
    table = Table(
        title="Trades Cerrados",
        title_style="bold white",
        header_style=CYAN,
        border_style=GRAY,
    )
    table.add_column("Entry Time", justify="center")
    table.add_column("Exit Time", justify="center")
    table.add_column("Symbol", style=WHITE)
    table.add_column("Strategy")
    table.add_column("Entry P", justify="right")
    table.add_column("Exit P", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("P&L%", justify="right")

    if not trades:
        table.add_row(
            "[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]",
            "[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]",
        )
        return table

    for t in trades:
        pnl = t.get("pnl")
        entry_p = t.get("entry_price")
        exit_p = t.get("exit_price")

        # P&L %
        pnl_pct = None
        if pnl is not None and entry_p and entry_p != 0:
            pnl_pct = (pnl / entry_p) * 100

        table.add_row(
            _fmt_time(t.get("entry_at")),
            _fmt_time(t.get("exit_at")),
            str(t.get("symbol", "—")),
            str(t.get("strategy", "—")),
            _val_or_dash(entry_p, "{:.2f}"),
            _val_or_dash(exit_p, "{:.2f}"),
            _fmt_pnl(pnl),
            _fmt_pnl(pnl_pct, "%"),
        )

    return table


def create_trade_metrics(trades: list) -> Panel:
    """Render aggregate trade metrics (Profit Factor, Best, Worst, Sharpe)."""
    if not trades:
        return Panel(
            "[dim]No hay trades para calcular métricas[/]",
            title="[bold white]Métricas de Trading[/]",
            border_style=GRAY,
        )

    total_pnl = sum(t.get("pnl", 0) for t in trades)
    gross_profit = sum(t.get("pnl", 0) for t in trades if (t.get("pnl") or 0) > 0)
    gross_loss = abs(sum(t.get("pnl", 0) for t in trades if (t.get("pnl") or 0) < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)

    best_trade = max(trades, key=lambda t: t.get("pnl", 0))
    worst_trade = min(trades, key=lambda t: t.get("pnl", 0))

    # Simple sharpe (approximate from trade returns)
    returns = [t.get("pnl", 0) for t in trades]
    avg_ret = sum(returns) / len(returns) if returns else 0
    std_ret = (sum((r - avg_ret) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 0
    sharpe = avg_ret / std_ret if std_ret > 0 else 0

    content = Text.assemble(
        ("Profit Factor: ", "bold"),
        (f"{profit_factor:.2f}" if profit_factor else "—", WHITE),
        ("\n", ""),
        ("Best Trade:    ", "bold"),
        _fmt_pnl(best_trade.get("pnl")),
        (f"  ({best_trade.get('symbol', '—')})", GRAY),
        ("\n", ""),
        ("Worst Trade:   ", "bold"),
        _fmt_pnl(worst_trade.get("pnl")),
        (f"  ({worst_trade.get('symbol', '—')})", GRAY),
        ("\n", ""),
        ("Sharpe Ratio:  ", "bold"),
        (f"{sharpe:.2f}" if sharpe != 0 else "—", WHITE),
        ("\n\n", ""),
        ("Total P&L:     ", "bold"),
        _fmt_pnl(total_pnl),
    )

    return Panel(content, title="[bold white]Métricas de Trading[/]", border_style=CYAN)


def create_log_panel(
    log_buffer: Any,
    level_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
    text_filter: Optional[str] = None,
) -> Panel:
    """Render log lines from a ``LogBuffer`` with per-level colouring.

    Colour scheme:
        DEBUG → gray, INFO → blue, WARNING → yellow,
        ERROR → red, CRITICAL → red + bold.
    """
    if log_buffer is None:
        return Panel("[dim]No hay buffer de logs[/]", title="Logs", border_style=GRAY)

    lines = log_buffer.get_lines(
        level_filter=level_filter,
        module_filter=module_filter,
        text_filter=text_filter,
        last_n=30,
    )

    if not lines:
        content = Text("[dim]No logs aún[/]", style=GRAY)
    else:
        content = Text()
        for line in lines[-30:]:
            styled_line = _colorize_log_line(line)
            content.append(styled_line)
            content.append("\n")

    filter_info = ""
    if level_filter:
        filter_info += f" [bold]{level_filter}[/]"
    if module_filter:
        filter_info += f" mod={module_filter}"
    if text_filter:
        filter_info += f" text={text_filter}"
    if not filter_info:
        filter_info = " [dim](todos los niveles)[/]"

    return Panel(
        content,
        title=f"[bold white]Logs{filter_info}[/]",
        border_style=BLUE,
        height=12,
    )


def _colorize_log_line(line: str) -> Text:
    """Apply per-level colouring to a raw log line string.

    Heuristic: scans for ``| LEVEL |`` in the formatted Loguru line.
    """
    level_map = {
        "DEBUG": GRAY,
        "INFO": BLUE,
        "WARNING": YELLOW,
        "ERROR": RED,
        "CRITICAL": "bold red",
    }
    for level, colour in level_map.items():
        marker = f"| {level} |"
        if marker in line:
            # Split the line at the level marker to keep the prefix visible
            prefix, _, rest = line.partition(marker)
            return Text.assemble(
                (prefix, GRAY),
                (f"| {level} |", colour),
                (rest, WHITE),
            )
    return Text(line, style=WHITE)


def create_footer(active_screen: int = 1) -> Panel:
    """Render keyboard shortcut bar with active screen indicator."""

    def _screen_btn(num: int, label: str) -> str:
        if num == active_screen:
            return f"[reverse bold]{num}[/reverse bold]{label}"
        return str(num) + label

    shortcuts = (
        f"  {_screen_btn(1, 'Dashboard')}  "
        f"{_screen_btn(2, 'Scanner')}  "
        f"{_screen_btn(3, 'Strategies')}  "
        f"{_screen_btn(4, 'Trades')}  "
        f"{_screen_btn(5, 'Logs')}  |  "
        "[p][dim]Pause[/] [r][dim]Resume[/] [s][dim]Scan[/]  |  "
        "[q][dim]Quit[/]"
    )

    return Panel(shortcuts, border_style=CYAN)


def create_empty_state(message: str) -> Panel:
    """Render a centered placeholder message."""
    return Panel(
        Text(message, justify="center", style=GRAY),
        border_style=GRAY,
    )
