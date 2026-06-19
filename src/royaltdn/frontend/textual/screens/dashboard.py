"""Dashboard screen — KPIs, positions, signals, risk, and log panel."""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, ListView, ListItem, Label, Static

from royaltdn.frontend.textual.widgets.log_panel import LogPanel
from royaltdn.frontend.textual.widgets.metrics_grid import MetricsGrid


class DashboardScreen(Screen):
    """Main dashboard: KPI cards, open positions, recent signals, risk summary, logs."""

    def compose(self) -> ComposeResult:
        """Build the dashboard layout."""
        yield MetricsGrid(id="kpi-grid")
        yield Label("[bold]Positions[/]", id="positions-label")
        yield DataTable(id="positions-table")
        yield Label("[bold]Signals[/]", id="signals-label")
        yield Static(id="signals-list")
        yield Label("[bold]Risk[/]", id="risk-label")
        yield Static(id="risk-info")
        yield Label("[bold]Logs[/]", id="logs-label")
        yield LogPanel(id="log-panel", max_lines=50)

    def on_mount(self) -> None:
        """Initial setup: configure table columns."""
        positions_table = self.query_one("#positions-table", DataTable)
        positions_table.add_columns("Symbol", "Qty", "Entry", "P&L", "P&L %")

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Refresh all dashboard widgets from ``state``.

        Args:
            state: ``StateLoader.load_all()`` dict.
            log_buffer: Unfiltered log lines from ``LogBuffer.get_lines()``.
        """
        self._update_kpis(state)
        self._update_positions(state)
        self._update_signals(state)
        self._update_risk(state)
        self._update_logs(log_buffer)

    # ── Internal updaters ─────────────────────────────────────────────

    def _update_kpis(self, state: dict[str, Any]) -> None:
        status = state.get("status", {})
        equity = state.get("equity", {})

        kpis = [
            ("Status", status.get("bot_status", "\u2014")),
            ("Equity", f"${equity.get('current_equity', 0):,.2f}"),
            ("Buy Power", f"${status.get('buying_power', 0):,.2f}"),
            ("Positions", str(len(state.get("positions", {}).get("positions", [])))),
            ("Scanner", state.get("scanner", {}).get("status", "\u2014")),
        ]
        # Safety: last successful trade or last_updated
        last_updated = status.get("last_updated", "")
        if last_updated:
            kpis.append(("Updated", last_updated[-8:] if len(last_updated) > 8 else last_updated))

        self.query_one("#kpi-grid", MetricsGrid).update_metrics(kpis)

    def _update_positions(self, state: dict[str, Any]) -> None:
        table = self.query_one("#positions-table", DataTable)
        table.clear()

        positions = state.get("positions", {}).get("positions", [])
        if not isinstance(positions, list):
            positions = []

        for pos in positions:
            symbol = pos.get("symbol", "\u2014")
            qty = str(pos.get("qty", "\u2014"))
            entry = f"${pos.get('entry_price', 0):,.2f}" if pos.get("entry_price") else "\u2014"
            pnl = f"${pos.get('unrealized_pl', 0):,.2f}" if pos.get("unrealized_pl") is not None else "\u2014"
            pnl_pct = f"{pos.get('unrealized_plpc', 0) * 100:+.2f}%" if pos.get("unrealized_plpc") is not None else "\u2014"
            table.add_row(symbol, qty, entry, pnl, pnl_pct)

    def _update_signals(self, state: dict[str, Any]) -> None:
        signals = state.get("signals", [])
        if not isinstance(signals, list):
            signals = []

        if not signals:
            self.query_one("#signals-list", Static).update("[dim italic]Waiting for bot signals...[/]")
            return

        lines = "\n".join(
            f"• {s.get('symbol', '?')} | {s.get('signal', '?')} | {s.get('confidence', '\u2014')}"
            for s in signals[:10]
        )
        self.query_one("#signals-list", Static).update(lines)

    def _update_risk(self, state: dict[str, Any]) -> None:
        risk = state.get("status", {}).get("risk", {})
        if not risk:
            self.query_one("#risk-info", Static).update("[dim italic]No risk data[/]")
            return

        lines = "\n".join(
            f"• {k}: {v}" for k, v in risk.items()
        )
        self.query_one("#risk-info", Static).update(lines or "[dim italic]No risk data[/]")

    def _update_logs(self, log_buffer: list[str]) -> None:
        self.query_one("#log-panel", LogPanel).update_logs(log_buffer)
