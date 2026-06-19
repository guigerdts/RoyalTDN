"""Trades screen — trade-level KPIs and a full trade history table."""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static

from royaltdn.frontend.textual.widgets.metrics_grid import MetricsGrid


class TradesScreen(Screen):
    """Displays trade performance metrics and a detailed trade history table."""

    def compose(self) -> ComposeResult:
        """Build the trades layout."""
        yield Label("[bold]Trade Metrics[/]", id="trade-metrics-label")
        yield MetricsGrid(id="trade-metrics")
        yield Label("[bold]Trade History[/]", id="trade-history-label")
        yield DataTable(id="trades-table")

    def on_mount(self) -> None:
        """Configure trade table columns."""
        table = self.query_one("#trades-table", DataTable)
        table.add_columns("ID", "Symbol", "Side", "Qty", "Entry", "Exit", "P&L")

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Refresh trade data from state.

        Args:
            state: ``StateLoader.load_all()`` dict.
            log_buffer: Unfiltered log lines (unused here).
        """
        trades_data = state.get("trades", {})
        self._update_metrics(trades_data)
        self._update_table(trades_data)

    # ── Internal updaters ─────────────────────────────────────────────

    def _update_metrics(self, trades_data: dict[str, Any]) -> None:
        metrics: list[tuple[str, str]] = []

        total_pnl = trades_data.get("total_pnl", trades_data.get("pnl", 0))
        metrics.append(("Total P&L", f"${float(total_pnl):,.2f}" if total_pnl else "\u2014"))

        win_rate = trades_data.get("win_rate", trades_data.get("winrate", None))
        if win_rate is not None:
            metrics.append(("Win Rate", f"{float(win_rate) * 100:.1f}%" if float(win_rate) < 1 else f"{float(win_rate):.1f}%"))

        trades_list = trades_data.get("trades", [])
        metrics.append(("Total Trades", str(len(trades_list)) if isinstance(trades_list, list) else "\u2014"))

        avg_pnl = trades_data.get("avg_pnl", trades_data.get("average_pnl", None))
        if avg_pnl is not None:
            metrics.append(("Avg P&L", f"${float(avg_pnl):,.2f}"))

        self.query_one("#trade-metrics", MetricsGrid).update_metrics(metrics)

    def _update_table(self, trades_data: dict[str, Any]) -> None:
        table = self.query_one("#trades-table", DataTable)
        table.clear()

        trades_list = trades_data.get("trades", [])
        if not isinstance(trades_list, list):
            trades_list = []

        for t in trades_list:
            tid = str(t.get("id", t.get("trade_id", "\u2014")))
            symbol = t.get("symbol", "\u2014")
            side = t.get("side", "\u2014")
            qty = str(t.get("qty", t.get("quantity", "\u2014")))
            entry = f"${t.get('entry_price', 0):,.2f}" if t.get("entry_price") else t.get("entry", "\u2014")
            exit_price = f"${t.get('exit_price', 0):,.2f}" if t.get("exit_price") else t.get("exit", "\u2014")
            pnl = f"${t.get('pnl', t.get('profit_loss', 0)):,.2f}" if t.get("pnl") is not None or t.get("profit_loss") is not None else "\u2014"
            table.add_row(tid, symbol, side, qty, entry, exit_price, pnl)
