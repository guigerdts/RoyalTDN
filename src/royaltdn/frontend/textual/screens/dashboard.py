"""Dashboard screen — KPIs, positions, signals, equity summary, and log panel."""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static

from royaltdn.frontend.textual.widgets.log_panel import LogPanel
from royaltdn.frontend.textual.widgets.metrics_grid import MetricsGrid


class DashboardScreen(Screen):
    """Main dashboard: KPI cards, open positions, last signals, equity summary, logs."""

    def compose(self) -> ComposeResult:
        """Build the dashboard layout."""
        yield MetricsGrid(id="kpi-grid")
        yield Label("[bold white]Open Positions[/]", id="positions-label")
        yield DataTable(id="positions-table")
        yield Label("[bold white]Last Signals[/]", id="signals-label")
        yield Static("[dim]Waiting for bot signals...[/]", id="signals-list")
        yield Label("[bold white]Trade Summary[/]", id="summary-label")
        yield Static("[dim]No trade data yet[/]", id="summary-info")
        yield Label("[bold white]Logs[/]", id="logs-label")
        yield LogPanel(id="log-panel", max_lines=50)

    def on_mount(self) -> None:
        """Initial setup: configure table columns."""
        positions_table = self.query_one("#positions-table", DataTable)
        positions_table.add_columns("Symbol", "Side", "Qty", "Entry", "P&L")

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Refresh all dashboard widgets from ``state``.

        Args:
            state: ``StateLoader.load_all()`` dict with keys matching
                ``logs/*.json`` filenames.
            log_buffer: Unfiltered log lines from ``LogBuffer.get_lines()``.
        """
        self._update_kpis(state)
        self._update_positions(state)
        self._update_signals(state)
        self._update_summary(state)
        self._update_logs(log_buffer)

    # ── Internal updaters ─────────────────────────────────────────────

    def _update_kpis(self, state: dict[str, Any]) -> None:
        status = state.get("status", {})
        equity = state.get("equity", {})
        trades = state.get("trades", {})
        positions = state.get("positions", {})

        pos_list = positions.get("open_positions", []) if isinstance(positions, dict) else []
        if not isinstance(pos_list, list):
            pos_list = []

        kpis = [
            ("Status", status.get("bot_status", "OFFLINE")),
            ("Equity", f"${float(equity.get('current_equity', 0)):,.2f}"),
            ("P&L D\u00eda", f"${float(equity.get('pnl_day', 0)):+,.2f}"),
            ("Drawdown", f"{float(equity.get('drawdown_pct', 0)):+.2f}%"),
            ("Win Rate", f"{float(trades.get('win_rate', 0)):.1f}%"),
            ("Positions", str(len(pos_list))),
        ]
        # Add scanner info if available
        scanner = state.get("scanner_results", {})
        if isinstance(scanner, dict) and scanner.get("last_scan"):
            last = scanner["last_scan"]
            kpis.append(("Scanner", last.get("timestamp", "")[-8:] if isinstance(last.get("timestamp"), str) else "\u2014"))

        self.query_one("#kpi-grid", MetricsGrid).update_metrics(kpis)

    def _update_positions(self, state: dict[str, Any]) -> None:
        table = self.query_one("#positions-table", DataTable)
        table.clear()

        positions_data = state.get("positions", {})
        if not isinstance(positions_data, dict):
            table.add_row("\u2014", "\u2014", "\u2014", "\u2014", "\u2014")
            return

        positions = positions_data.get("open_positions", [])
        if not isinstance(positions, list) or not positions:
            table.add_row("\u2014", "\u2014", "\u2014", "\u2014", "\u2014")
            return

        for pos in positions:
            symbol = pos.get("symbol", "\u2014")
            side = pos.get("side", pos.get("direction", "\u2014"))
            qty = str(pos.get("qty", pos.get("quantity", "\u2014")))
            entry_px = pos.get("entry_price", pos.get("avg_entry_price", 0))
            entry = f"${float(entry_px):,.2f}" if entry_px else "\u2014"
            pnl = pos.get("unrealized_pl", pos.get("pnl", 0))
            pnl_str = f"${float(pnl):+,.2f}" if pnl is not None else "\u2014"
            table.add_row(symbol, side, qty, entry, pnl_str)

    def _update_signals(self, state: dict[str, Any]) -> None:
        signals_data = state.get("signals", {})
        if not isinstance(signals_data, dict):
            self.query_one("#signals-list", Static).update("[dim]No signals data[/]")
            return

        last_signals = signals_data.get("last_signals", [])
        if not isinstance(last_signals, list) or not last_signals:
            # Show placeholder
            today_count = signals_data.get("today_count", 0)
            count_str = f"({today_count} today)" if today_count else ""
            self.query_one("#signals-list", Static).update(
                f"[white]No recent signals {count_str}[/]"
            )
            return

        lines = []
        for s in last_signals[:10]:
            action = s.get("action", "?")
            symbol = s.get("symbol", "?")
            price = s.get("price", "")
            strategy = s.get("strategy", "")
            ts = str(s.get("timestamp", ""))[-8:] if s.get("timestamp") else ""
            price_str = f" @ ${float(price):,.2f}" if price else ""
            lines.append(f"  {action:5s} {symbol:6s}{price_str}  [{strategy}]  {ts}")

        self.query_one("#signals-list", Static).update("\n".join(lines) if lines else "[dim]No signal data[/]")

    def _update_summary(self, state: dict[str, Any]) -> None:
        trades = state.get("trades", {})
        if not isinstance(trades, dict):
            self.query_one("#summary-info", Static).update("[dim]No trade data[/]")
            return

        total = trades.get("total_trades", 0)
        win_rate = trades.get("win_rate", 0)
        profit_factor = trades.get("profit_factor", 0)
        total_pnl = trades.get("total_pnl", 0)

        if total:
            lines = [
                f"Total Trades: {total}",
                f"Win Rate:     {float(win_rate):.1f}%",
                f"Profit Fact: {float(profit_factor):.2f}",
                f"Total P&L:    ${float(total_pnl):+,.2f}",
            ]
            self.query_one("#summary-info", Static).update("\n".join(lines))
        else:
            self.query_one("#summary-info", Static).update("[dim]No trades executed yet[/]")

    def _update_logs(self, log_buffer: list[str]) -> None:
        self.query_one("#log-panel", LogPanel).update_logs(log_buffer)
