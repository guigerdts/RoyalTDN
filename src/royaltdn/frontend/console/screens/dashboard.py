"""Dashboard screen — main overview with KPIs, positions, signals, risk and logs."""

from typing import Any

from rich.layout import Layout
from rich.panel import Panel

from royaltdn.frontend.console.components.widgets import (
    create_empty_state,
    create_footer,
    create_header,
    create_kpi_cards,
    create_log_panel,
    create_positions_table,
    create_risk_panel,
    create_signals_table,
)


def _get_terminal_size() -> tuple[int, int]:
    """Return ``(columns, lines)``, defaulting to ``(80, 24)`` on error."""
    import shutil

    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return 80, 24


def render_dashboard(state: dict, log_buffer: Any) -> Layout:
    """Render the main dashboard.

    Args:
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance for the log panel.

    Returns:
        A ``Layout`` with header, body (60/40 split), and footer.
    """
    cols, rows = _get_terminal_size()
    if cols < 80 or rows < 24:
        msg = (
            f"[bold yellow]Terminal too small[/]\n\n"
            f"Current size: {cols}x{rows}\n"
            f"Minimum required: 80x24\n\n"
            "[dim]Please resize your terminal window[/]"
        )
        return Layout(Panel(msg, border_style="red"))

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )

    # ── Header ──
    layout["header"].update(create_header(state))

    # ── Body (60/40 split) ──
    body_layout = Layout()
    body_layout.split_row(
        Layout(name="left", ratio=60),
        Layout(name="right", ratio=40),
    )

    signals = state.get("scanner", {}).get("last_scan", {}).get("top_signals", [])

    left = Layout()
    left.split_column(
        Layout(name="kpi", size=4),
        Layout(name="positions", ratio=60),
        Layout(name="signals", ratio=40),
    )
    left["kpi"].update(create_kpi_cards(state))
    left["positions"].update(create_positions_table(state))
    left["signals"].update(create_signals_table(signals))

    right = Layout()
    right.split_column(
        Layout(name="risk", ratio=50),
        Layout(name="logs", ratio=50),
    )
    right["risk"].update(create_risk_panel(state))
    right["logs"].update(create_log_panel(log_buffer))

    body_layout["left"].update(left)
    body_layout["right"].update(right)
    layout["body"].update(body_layout)

    # ── Footer ──
    layout["footer"].update(create_footer(active_screen=1))

    return layout
