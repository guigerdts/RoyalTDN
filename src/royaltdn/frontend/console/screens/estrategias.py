"""Estrategias screen — predefined + user strategies."""

from typing import Any

from rich.layout import Layout

from royaltdn.frontend.console.components.widgets import (
    create_footer,
    create_header,
    create_strategies_table,
)


def render_estrategias(state: dict, log_buffer: Any, status_message: str | None = None) -> Layout:
    """Render the estrategias (strategies) screen.

    Args:
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance (passed but not used here).
        status_message: Optional message shown in the footer bar.

    Returns:
        A ``Layout`` with header, strategies tables, and footer.
    """
    strategies_data = state.get("strategies", {})
    # User strategies could come from a separate file; use same source for now
    user_strategies = state.get("strategies", {})

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )

    layout["header"].update(create_header(state))
    layout["footer"].update(create_footer(active_screen=3, status_message=status_message))

    body = Layout()
    body.update(create_strategies_table(strategies_data, user_strategies))
    layout["body"].update(body)

    return layout
