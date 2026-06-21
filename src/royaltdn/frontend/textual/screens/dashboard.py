"""Dashboard screen — renders the entire dashboard as Rich content
inside a single RichLog widget, bypassing Textual widget composition
issues on low-color terminals (Termux, TEXTUAL_COLORS=16).

All rendering is done via Rich Tables, Panels, and Text — the same
approach that worked in the old console-based TUI.
"""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import RichLog


class DashboardScreen(Screen):
    """Main dashboard: KPIs, positions, signals, trade summary, logs.

    Uses a single ``RichLog`` widget and renders everything as Rich
    renderables via ``update_data()``.  This avoids Textual widget
    height/color/composition bugs that appear in 16-color Termux.
    """

    # ── Rich-styles constants ────────────────────────────────────────

    STYLE_HEADER = "bold white on #000080"
    STYLE_LABEL = "bold white"
    STYLE_VALUE = "bold cyan"
    STYLE_GREEN = "bold green"
    STYLE_RED = "bold red"
    STYLE_YELLOW = "bold yellow"
    STYLE_DIM = "dim white"
    STYLE_BORDER = "white"

    # ── Lifecycle ───────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Single RichLog — no child widgets to compose."""
        yield RichLog(id="dashboard-content", highlight=True, max_lines=1000)

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Rebuild the entire dashboard as Rich renderables.

        Args:
            state: ``StateLoader.load_all()`` dict with keys matching
                ``logs/*.json`` filenames.
            log_buffer: Unfiltered log lines from ``LogBuffer.get_lines()``.
        """
        from rich.text import Text
        from rich.table import Table
        from rich.panel import Panel
        from rich.console import Group

        sections: list[object] = []

        self._append_kpis(state, sections, Panel, Table, Text)
        self._append_positions(state, sections, Panel, Table, Text)
        self._append_signals(state, sections, Panel, Table, Text)
        self._append_summary(state, sections, Panel, Table, Text)
        self._append_logs(log_buffer, sections, Panel, Text)

        content = Group(*sections)
        log = self.query_one("#dashboard-content", RichLog)
        log.clear()
        log.write(content)

    # ── Section builders ────────────────────────────────────────────

    @staticmethod
    def _append_kpis(
        state: dict,
        sections: list,
        Panel: type,
        Table: type,
        Text: type,
    ) -> None:
        status = state.get("status", {})
        equity = state.get("equity", {})
        trades = state.get("trades", {})
        positions = state.get("positions", {})

        pos_list = positions.get("open_positions", []) if isinstance(positions, dict) else []
        if not isinstance(pos_list, list):
            pos_list = []

        scanner_info = "\u2014"
        scanner = state.get("scanner_results", {})
        if isinstance(scanner, dict):
            last = scanner.get("last_scan", {})
            if isinstance(last, dict) and last.get("timestamp"):
                scanner_info = str(last["timestamp"])[-8:]

        rows = [
            ("Status", status.get("bot_status", "\u2014"), "bold white"),
            ("Equity", f"${float(equity.get('current_equity', 0)):,.2f}", "bold cyan"),
            ("P&L D\u00eda", f"${float(equity.get('pnl_day', 0)):+,.2f}",
             "bold green" if float(equity.get('pnl_day', 0)) >= 0 else "bold red"),
            ("DD", f"{float(equity.get('drawdown_pct', 0)):+.2f}%", "bold yellow"),
            ("WR", f"{float(trades.get('win_rate', 0)):.1f}%", "bold cyan"),
            ("Pos", str(len(pos_list)), "bold white"),
            ("Scan", scanner_info, "bold white"),
        ]

        table = Table.grid(padding=(0, 2))
        table.add_column(justify="center", ratio=1)
        cells = []
        for label, value, style in rows:
            cells.append(Text.assemble((f"{label}\n", "bold white"), (str(value), style)))
        table.add_row(*cells)

        sections.append(Panel(table, title="KPIs", border_style="white"))

    @staticmethod
    def _append_positions(
        state: dict,
        sections: list,
        Panel: type,
        Table: type,
        Text: type,
    ) -> None:
        positions_data = state.get("positions", {})
        if not isinstance(positions_data, dict):
            sections.append(Panel(Text("No position data", style="dim white"),
                                  title="Open Positions", border_style="white"))
            return

        positions = positions_data.get("open_positions", [])
        if not isinstance(positions, list) or not positions:
            sections.append(Panel(Text("No open positions", style="dim white"),
                                  title="Open Positions", border_style="white"))
            return

        table = Table(title=None, border_style="white", header_style="bold white")
        table.add_column("Symbol", style="bold white")
        table.add_column("Side")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Broker", style="yellow")

        for pos in positions:
            symbol = str(pos.get("symbol", "\u2014"))
            side = str(pos.get("side", pos.get("direction", "\u2014")))
            qty_raw = pos.get("qty", pos.get("quantity", "\u2014"))
            qty = f"{qty_raw:.2f}" if isinstance(qty_raw, (int, float)) else str(qty_raw)
            entry_raw = pos.get("entry_price", pos.get("avg_entry_price", 0))
            entry = f"${float(entry_raw):,.2f}" if entry_raw else "\u2014"
            pnl_raw = pos.get("unrealized_pl", pos.get("pnl", 0))
            pnl = f"${float(pnl_raw):+,.2f}" if isinstance(pnl_raw, (int, float)) else "\u2014"
            pnl_style = "green" if (isinstance(pnl_raw, (int, float)) and pnl_raw >= 0) else "red"
            broker = str(pos.get("broker", "\u2014"))
            table.add_row(symbol, side, qty, entry, f"[{pnl_style}]{pnl}[/]", broker)

        sections.append(Panel(table, title="Open Positions", border_style="white"))

    @staticmethod
    def _append_signals(
        state: dict,
        sections: list,
        Panel: type,
        Table: type,
        Text: type,
    ) -> None:
        signals_data = state.get("signals", {})
        if not isinstance(signals_data, dict):
            sections.append(Panel(Text("No signal data", style="dim white"),
                                  title="Last Signals", border_style="white"))
            return

        last_signals = signals_data.get("last_signals", [])
        if not isinstance(last_signals, list) or not last_signals:
            count = signals_data.get("today_count", 0)
            text = f"No signals today ({count} total)" if count else "Waiting for bot signals..."
            sections.append(Panel(Text(text, style="dim white"),
                                  title="Last Signals", border_style="white"))
            return

        table = Table(title=None, border_style="white", header_style="bold white")
        table.add_column("Action")
        table.add_column("Symbol", style="bold white")
        table.add_column("Price", justify="right")
        table.add_column("Strategy")
        table.add_column("Time")

        for s in last_signals[:10]:
            action = s.get("action", "?")
            action_style = "green" if action == "BUY" else ("red" if action == "SELL" else "white")
            symbol = str(s.get("symbol", "?"))
            price_raw = s.get("price", "")
            price = f"${float(price_raw):,.2f}" if price_raw else "\u2014"
            strategy = str(s.get("strategy", ""))
            ts = str(s.get("timestamp", ""))[-8:] if s.get("timestamp") else ""
            table.add_row(f"[{action_style}]{action}[/]", symbol, price, strategy, ts)

        sections.append(Panel(table, title="Last Signals", border_style="white"))

    @staticmethod
    def _append_summary(
        state: dict,
        sections: list,
        Panel: type,
        Table: type,
        Text: type,
    ) -> None:
        trades = state.get("trades", {})
        if not isinstance(trades, dict) or not trades.get("total_trades"):
            sections.append(Panel(Text("No trades executed yet", style="dim white"),
                                  title="Trade Summary", border_style="white"))
            return

        total = trades.get("total_trades", 0)
        win_rate = trades.get("win_rate", 0)
        profit_factor = trades.get("profit_factor", 0)
        total_pnl = trades.get("total_pnl", 0)

        table = Table.grid(padding=(0, 3))
        table.add_column(justify="center", ratio=1)
        pnl_style = "green" if float(total_pnl) >= 0 else "red"
        cells = [
            Text.assemble(("Total\n", "bold white"), (str(total), "bold white")),
            Text.assemble(("Win Rate\n", "bold white"), (f"{float(win_rate):.1f}%", "bold cyan")),
            Text.assemble(("Profit Factor\n", "bold white"), (f"{float(profit_factor):.2f}", "bold cyan")),
            Text.assemble(("Total P&L\n", "bold white"), (f"${float(total_pnl):+,.2f}", pnl_style)),
        ]
        table.add_row(*cells)

        sections.append(Panel(table, title="Trade Summary", border_style="white"))

    @staticmethod
    def _append_logs(
        log_buffer: list[str],
        sections: list,
        Panel: type,
        Text: type,
    ) -> None:
        if not log_buffer:
            sections.append(Panel(Text("No log entries", style="dim white"),
                                  title="Logs", border_style="white"))
            return

        lines = []
        for line in log_buffer[-20:]:
            style = "white"
            if "CRITICAL" in line or "ERROR" in line:
                style = "bold red"
            elif "WARNING" in line or "WARN" in line:
                style = "yellow"
            elif "INFO" in line:
                style = "green"
            elif "DEBUG" in line:
                style = "dim white"
            lines.append(Text(line.strip(), style=style))

        from rich.console import Group as RichGroup
        sections.append(Panel(RichGroup(*lines), title="Logs", border_style="white"))
