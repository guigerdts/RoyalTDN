"""Scanner screen — signals table and scan history."""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static


class ScannerScreen(Screen):
    """Shows scanner results: signal table and historical scans."""

    def compose(self) -> ComposeResult:
        """Build the scanner layout."""
        yield Label("[bold]Scanner Signals[/]", id="scanner-signals-label")
        yield DataTable(id="scanner-signals-table")
        yield Label("[bold]Scan History[/]", id="scanner-history-label")
        yield Static(id="scanner-history")

    def on_mount(self) -> None:
        """Configure columns on mount."""
        table = self.query_one("#scanner-signals-table", DataTable)
        table.add_columns("Symbol", "Signal", "Confidence", "Direction")

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Refresh scanner data from state.

        Args:
            state: ``StateLoader.load_all()`` dict.
            log_buffer: Unfiltered log lines (unused here).
        """
        scanner = state.get("scanner", {})
        self._update_signals(scanner)
        self._update_history(scanner)

    # ── Internal updaters ─────────────────────────────────────────────

    def _update_signals(self, scanner: dict[str, Any]) -> None:
        table = self.query_one("#scanner-signals-table", DataTable)
        table.clear()

        signals = scanner.get("signals", [])
        if not isinstance(signals, list):
            signals = []

        for sig in signals:
            symbol = sig.get("symbol", "\u2014")
            signal_type = sig.get("signal", "\u2014")
            confidence = f"{sig.get('confidence', 0):.1f}" if sig.get("confidence") else "\u2014"
            direction = sig.get("direction", "\u2014")
            table.add_row(symbol, signal_type, confidence, direction)

    def _update_history(self, scanner: dict[str, Any]) -> None:
        history = scanner.get("scan_history", [])
        if not isinstance(history, list) or not history:
            self.query_one("#scanner-history", Static).update(
                "[dim italic]No scan history yet[/]"
            )
            return

        lines = []
        for entry in history[-20:]:  # last 20 scans
            ts = entry.get("timestamp", entry.get("time", ""))
            count = entry.get("signals_count", entry.get("count", 0))
            lines.append(f"• {ts}  |  {count} signals")

        self.query_one("#scanner-history", Static).update("\n".join(lines))
