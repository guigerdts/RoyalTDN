"""Live 6-panel dashboard for the CellMesh crypto trading bot.

Uses Rich Layout with six live panels at 2 fps:
  1. KPI Bar       — Capital, Drawdown, Win Rate, Sharpe, positions
  2. Open Positions — Per-position table with unrealised P&L
  3. Closed Trades  — Last 10 closed trades from TradeTracker
  4. Professional Metrics  — PF, Expectancy, Best/Worst, Avg Hold, etc.
  5. Bot Status    — Mode, Uptime, Running/Stopped, cell count
  6. Events        — Color-coded scrolling event log

Falls back to structured logging via loguru when Rich is unavailable.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from loguru import logger


class Dashboard:
    """Professional 6-panel Rich Live dashboard.

    Injects three data sources — Portfolio, TradeTracker, EventEngine —
    and renders a terminal UI at 2 fps via ``rich.live.Live``.
    """

    def __init__(self, portfolio: Any, trade_tracker: Any, engine: Any) -> None:
        """Initialise the dashboard with live data sources.

        Args:
            portfolio: Portfolio instance for positions, capital, drawdown.
            trade_tracker: TradeTracker instance for closed-trade metrics.
            engine: EventEngine instance for bus, mode, status.
        """
        self._portfolio = portfolio
        self._trade_tracker = trade_tracker
        self._engine = engine
        self.bus = engine.bus
        self._running = False
        self._events: deque[dict[str, Any]] = deque(maxlen=50)
        self._queue: asyncio.Queue | None = None

    # ── Lifecycle ──────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the dashboard loop.

        Attempts Rich Live display.  Falls back to ``logger.info``
        when Rich is not installed.
        """
        self._running = True
        self._queue = self.bus.subscribe()

        try:
            import rich  # noqa: F401
            await self._run_rich()
        except ImportError:
            logger.warning("Rich no disponible — usando fallback por logger")
            await self._run_logger()

    async def _run_rich(self) -> None:
        """Run the 6-panel Rich Live display at 2 fps.

        Layout::

            ┌───────────────────────┬───────────────────┐
            │       KPI Bar         │    Bot Status     │
            ├───────────────────────┴───────────────────┤
            │              Open Positions               │
            ├───────────────────────┬───────────────────┤
            │    Closed Trades      │ Prof Metrics      │
            ├───────────────────────┴───────────────────┤
            │                 Events                    │
            └───────────────────────────────────────────┘
        """
        from rich.console import Console
        from rich.layout import Layout
        from rich.live import Live

        console = Console(color_system="standard")
        layout = Layout()
        layout.split_column(
            Layout(name="top", size=3),
            Layout(name="positions", size=8),
            Layout(name="middle", size=11),
            Layout(name="events"),
        )
        layout["top"].split_row(
            Layout(name="kpi_bar"),
            Layout(name="bot_status", size=42),
        )
        layout["middle"].split_row(
            Layout(name="closed_trades"),
            Layout(name="prof_metrics", size=46),
        )

        with Live(layout, console=console, refresh_per_second=2, screen=True) as live:
            while self._running:
                self._drain_events()

                layout["kpi_bar"].update(self._build_kpi_bar_panel())
                layout["positions"].update(self._build_open_positions_panel())
                layout["closed_trades"].update(self._build_closed_trades_panel())
                layout["prof_metrics"].update(self._build_prof_metrics_panel())
                layout["bot_status"].update(self._build_bot_status_panel())
                layout["events"].update(self._build_events_panel())

                await asyncio.sleep(0.5)

        logger.info("Dashboard Live cerrado")

    async def _run_logger(self) -> None:
        """Fallback: log events via loguru when Rich is unavailable."""
        while self._running:
            self._drain_events()
            await asyncio.sleep(0.5)

    def _drain_events(self) -> None:
        """Pull all pending events from the subscribed queue into the ring buffer."""
        if self._queue is None:
            return
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                self._events.append(event)
            except asyncio.QueueEmpty:
                break

    # ── Panel: KPI Bar ─────────────────────────────────────────────

    def _build_kpi_bar_panel(self) -> Any:
        """Build the KPI bar panel — key portfolio + performance numbers."""
        from rich.panel import Panel
        from rich.text import Text

        portfolio = self._portfolio
        tt = self._trade_tracker

        capital = portfolio.capital
        total_value = portfolio.get_total_value()
        total_return = total_value - portfolio.initial_capital
        dd = portfolio.get_drawdown()
        open_count = len(portfolio.positions)
        wr = tt.win_rate if tt is not None else 0.0
        sharpe = tt.sharpe_ratio if tt is not None else 0.0

        content = (
            f" Capital: ${capital:,.2f}"
            f"  |  Total: ${total_value:,.2f}"
            f"  |  P&L: ${total_return:+,.2f}"
            f"  |  Drawdown: {dd:.2%}"
            f"  |  Win Rate: {wr:.0%}"
            f"  |  Sharpe: {sharpe:.2f}"
            f"  |  Open: {open_count}"
        )
        return Panel(Text(content, no_wrap=True), title="KPI Bar", style="bold white")

    # ── Panel: Open Positions ──────────────────────────────────────

    def _build_open_positions_panel(self) -> Any:
        """Build the Open Positions table — symbol, direction, P&L, duration."""
        from rich.panel import Panel
        from rich.table import Table

        table = Table(title="Open Positions", expand=True, box=None)
        table.add_column("Symbol", style="cyan", no_wrap=True)
        table.add_column("Dir", style="green", width=4)
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("Unreal. P&L", justify="right")
        table.add_column("P&L %", justify="right")

        portfolio = self._portfolio
        rows_added = False

        for sym, qty in portfolio.positions.items():
            if qty <= 0:
                continue
            entry = portfolio._position_costs.get(sym, 0.0)
            current = portfolio._mtm_prices.get(sym, entry)
            upnl = (current - entry) * qty
            pnl_pct = ((current - entry) / entry * 100.0) if entry != 0.0 else 0.0
            pnl_style = "green" if upnl >= 0 else "red"

            table.add_row(
                sym,
                "LONG",
                f"{qty:.4f}",
                f"${entry:.2f}",
                f"${current:.2f}",
                f"[{pnl_style}]${upnl:+,.2f}[/]",
                f"[{pnl_style}]{pnl_pct:+.2f}%[/]",
            )
            rows_added = True

        if not rows_added:
            table.add_row("—", "", "", "", "", "", "")

        return Panel(table, title="Open Positions")

    # ── Panel: Closed Trades ───────────────────────────────────────

    def _build_closed_trades_panel(self) -> Any:
        """Build the Closed Trades table — last 10 trades from TradeTracker."""
        from rich.panel import Panel
        from rich.table import Table

        table = Table(title="Closed Trades (Last 10)", expand=True, box=None)
        table.add_column("Symbol", no_wrap=True)
        table.add_column("Dir", width=4)
        table.add_column("Entry→Exit", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Duration", justify="right")

        rows_added = False

        if self._trade_tracker is not None:
            for trade in self._trade_tracker.trades[-10:]:
                pnl_style = "green" if trade.pnl >= 0 else "red"
                duration = self._fmt_duration(trade.duration_seconds)
                table.add_row(
                    trade.symbol,
                    trade.direction[:4],
                    f"${trade.entry_price:.2f}→${trade.exit_price:.2f}",
                    f"[{pnl_style}]${trade.pnl:+,.2f}[/]",
                    duration,
                )
                rows_added = True

        if not rows_added:
            table.add_row("—", "", "", "", "")

        return Panel(table, title="Closed Trades")

    # ── Panel: Professional Metrics ────────────────────────────────

    def _build_prof_metrics_panel(self) -> Any:
        """Build the Professional Metrics panel — aggregated stats."""
        from rich.panel import Panel
        from rich.table import Table

        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        tt = self._trade_tracker
        if tt is not None and tt.total_trades > 0:
            pf = tt.profit_factor
            pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"
            best = tt.best_trade
            worst = tt.worst_trade
            hold = self._fmt_duration(tt.avg_holding_time)

            table.add_row("Total Trades", str(tt.total_trades))
            table.add_row("Win Rate", f"{tt.win_rate:.0%}")
            table.add_row("Profit Factor", pf_str)
            table.add_row("Expectancy", f"${tt.expectancy:+,.2f}")
            table.add_row("Total P&L", f"${tt.total_pnl:+,.2f}")
            table.add_row("Sharpe Ratio", f"{tt.sharpe_ratio:.2f}")
            table.add_row("Avg Hold Time", hold)
            table.add_row("Best Trade", f"${best.pnl:+,.2f}" if best else "-")
            table.add_row("Worst Trade", f"${worst.pnl:+,.2f}" if worst else "-")
        else:
            table.add_row("Status", "No trades recorded")

        return Panel(table, title="Professional Metrics")

    # ── Panel: Bot Status ──────────────────────────────────────────

    def _build_bot_status_panel(self) -> Any:
        """Build the Bot Status panel — mode, uptime, running state."""
        from datetime import datetime, timezone
        from rich.panel import Panel
        from rich.table import Table

        engine = self._engine
        mode = getattr(engine, "mode", "unknown")
        start_time = getattr(engine, "start_time", None)
        running = getattr(engine, "_running", False)
        cells = getattr(engine, "cells", [])

        if start_time is not None:
            uptime = datetime.now(timezone.utc) - start_time
            uptime_str = self._fmt_duration(uptime.total_seconds())
        else:
            uptime_str = "-"

        status = "Running" if running else "Stopped"
        status_style = "green" if running else "red"

        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Field", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Mode", str(mode).capitalize())
        table.add_row("Status", f"[{status_style}]{status}[/]")
        table.add_row("Uptime", uptime_str)
        table.add_row("Cells", str(len(cells)))

        return Panel(table, title="Bot Status")

    # ── Panel: Events ──────────────────────────────────────────────

    def _build_events_panel(self) -> Any:
        """Build the color-coded Events panel — scrolling event log."""
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        EVENT_STYLES: dict[str, str] = {
            "signal": "yellow",
            "approved": "green",
            "rejected": "red",
            "executed": "cyan",
            "position_opened": "blue",
            "position_closed": "magenta",
        }

        table = Table(title="Events", expand=True, box=None)
        table.add_column("Type", no_wrap=True, width=18)
        table.add_column("Symbol", no_wrap=True)
        table.add_column("Details")

        for event in list(self._events)[-15:]:
            etype = event.get("type", "")
            symbol = event.get("symbol", "")

            # Map internal event type to display type for colouring
            if etype == "position":
                status = event.get("status", "")
                display_type = "position_opened" if status == "opened" else "position_closed"
            elif etype == "trade":
                display_type = "executed"
            else:
                display_type = etype

            style = EVENT_STYLES.get(display_type, "white")
            details = self._fmt_event_detail(event, etype)
            label = display_type.replace("_", " ").title()

            type_cell = Text(label, style=style)
            table.add_row(type_cell, symbol, details)

        if not table.rows:
            table.add_row("—", "", "")

        return Panel(table, title="Events")

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        """Format a duration in seconds to a human-friendly string."""
        if seconds <= 0.0:
            return "-"
        if seconds >= 86400:
            return f"{seconds / 86400:.1f}d"
        if seconds >= 3600:
            return f"{seconds / 3600:.1f}h"
        if seconds >= 60:
            return f"{seconds / 60:.0f}m"
        return f"{seconds:.0f}s"

    @staticmethod
    def _fmt_event_detail(event: dict[str, Any], etype: str) -> str:
        """Format event details based on event type."""
        if etype == "tick":
            price = event.get("price", 0.0)
            return f"${price:.2f}" if price else "-"

        if etype == "signal":
            action = event.get("action", "")
            price = event.get("price", 0.0)
            return f"{action} @ ${price:.2f}"

        if etype == "approved":
            return str(event.get("detail", "risk_approved"))

        if etype == "rejected":
            return str(event.get("detail", "risk_rejected"))

        if etype == "executed":
            qty = event.get("qty", 0)
            price = event.get("price", 0.0)
            return f"{qty} @ ${price:.2f}"

        if etype == "trade":
            action = event.get("action", "")
            qty = event.get("qty", 0)
            price = event.get("price", 0.0)
            return f"{action} {qty} @ ${price:.2f}"

        if etype == "position":
            if event.get("status") == "opened":
                cap = event.get("capital", 0)
                return f"capital=${cap:,.2f}"
            pnl = event.get("pnl", 0.0)
            return f"PnL=${pnl:+,.2f}"

        return "-"

    async def stop(self) -> None:
        """Gracefully stop the dashboard loop."""
        self._running = False
        logger.info("Dashboard detenido")
