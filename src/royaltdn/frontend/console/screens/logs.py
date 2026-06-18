"""Logs screen — filter bar + colourised log panel."""

from typing import Any, Optional

from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from royaltdn.frontend.console.components.widgets import (
    create_footer,
    create_header,
    create_log_panel,
)


def _build_filter_bar(
    level_filter: Optional[str],
    module_filter: Optional[str],
    text_filter: Optional[str],
) -> Panel:
    """Build a small filter-bar panel showing active filters."""
    parts = []

    # Level indicator
    if level_filter:
        parts.append(f"[bold white]Level:[/] [cyan]{level_filter}[/]")
    else:
        parts.append("[dim]Level: ALL[/]")

    if module_filter:
        parts.append(f"[bold white]Module:[/] [cyan]{module_filter}[/]")

    if text_filter:
        parts.append(f"[bold white]Text:[/] [cyan]{text_filter}[/]")

    if not module_filter and not text_filter and not level_filter:
        parts.append("[dim](no filters active)[/]")

    help_text = "  |  [i]INFO  [w]WARN  [e]ERROR  [a]ALL"
    bar_text = "  ".join(parts) + help_text

    return Panel(Text(bar_text), border_style="cyan", height=3)


def render_logs(
    state: dict,
    log_buffer: Any,
    level_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
    text_filter: Optional[str] = None,
) -> Layout:
    """Render the logs screen.

    Args:
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance.
        level_filter: Optional log level to show (e.g. ``"INFO"``).
        module_filter: Optional module name filter.
        text_filter: Optional free-text filter.

    Returns:
        A ``Layout`` with header, filter bar, log panel, and footer.
    """
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="filter_bar", size=3),
        Layout(name="log_panel"),
        Layout(name="footer", size=3),
    )

    layout["header"].update(create_header(state))
    layout["filter_bar"].update(
        _build_filter_bar(level_filter, module_filter, text_filter)
    )
    layout["log_panel"].update(
        create_log_panel(log_buffer, level_filter, module_filter, text_filter)
    )
    layout["footer"].update(create_footer(active_screen=5))

    return layout
