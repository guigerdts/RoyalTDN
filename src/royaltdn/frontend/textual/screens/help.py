"""HelpScreen — static command reference table with key bindings."""

from typing import Any

from rich.table import Table
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class HelpScreen(Screen):
    """Help overlay showing all key bindings in a Rich-formatted table."""

    def compose(self) -> ComposeResult:
        """Render the help table as a single Static widget."""
        table = Table(
            title="ROYALTDN — Ayuda",
            title_style="bold white",
            border_style="cyan",
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Atajos de Teclado", justify="center", width=30)

        table.add_row("")
        table.add_row("  1  │ Dashboard")
        table.add_row("  2  │ Scanner")
        table.add_row("  3  │ Estrategias")
        table.add_row("  4  │ Trades")
        table.add_row("  5  │ Logs")
        table.add_row("  6  │ Builder")
        table.add_row("")
        table.add_row("  p  │ Pausar bot")
        table.add_row("  r  │ Reanudar bot")
        table.add_row("  s  │ Disparar scanner manual")
        table.add_row("  h  │ Esta ayuda")
        table.add_row("  q  │ Salir")

        yield Static(table, id="help-content")

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """No-op — HelpScreen is static and does not refresh."""
        pass
