"""Scanner screen — last scan info, signals table, and scan history."""

from typing import Any

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from royaltdn.frontend.console.components.widgets import (
    create_empty_state,
    create_footer,
    create_header,
    create_scanner_table,
)


def _fmt_time(ts: Any) -> str:
    """Format a timestamp to ``HH:MM:SS`` or return ``—``."""
    if not ts:
        return "—"
    try:
        if isinstance(ts, str):
            from datetime import datetime
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%H:%M:%S")
        return str(ts)
    except (ValueError, TypeError):
        return str(ts)


def render_scanner(state: dict, log_buffer: Any) -> Layout:
    """Render the scanner screen.

    Args:
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance (passed but not used here).

    Returns:
        A ``Layout`` with header, scan info, signals table, history, and footer.
    """
    scanner_data = state.get("scanner", {})
    last_scan = scanner_data.get("last_scan", {})
    scan_history = scanner_data.get("scan_history", [])

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )

    layout["header"].update(create_header(state))
    layout["footer"].update(create_footer(active_screen=2))

    # Body
    if not last_scan and not scan_history:
        layout["body"].update(
            Layout(create_empty_state("Scanner no ha ejecutado aún"))
        )
        return layout

    body = Layout()
    body.split_column(
        Layout(name="signals_table", ratio=60),
        Layout(name="history_table", ratio=40),
    )

    body["signals_table"].update(create_scanner_table(scanner_data))

    # Scan history table
    history_table = Table(
        title="Historial de Escaneos",
        title_style="bold white",
        header_style="cyan",
        border_style="bright_black",
    )
    history_table.add_column("Time", justify="center")
    history_table.add_column("Symbols", justify="right")
    history_table.add_column("Passed", justify="right")
    history_table.add_column("Signals", justify="right")

    if not scan_history:
        history_table.add_row("[dim]—[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]")
    else:
        for entry in scan_history[-5:]:
            history_table.add_row(
                _fmt_time(entry.get("timestamp")),
                str(entry.get("total_symbols", "—")),
                str(entry.get("passed_symbols", "—")),
                str(entry.get("signals_count", "—")),
            )

    body["history_table"].update(history_table)
    layout["body"].update(body)

    return layout
