"""Trades screen — trade metrics summary and closed trades table."""

from typing import Any

from rich.layout import Layout

from royaltdn.frontend.console.components.widgets import (
    create_empty_state,
    create_footer,
    create_header,
    create_trade_metrics,
    create_trades_table,
)


def render_trades(state: dict, log_buffer: Any) -> Layout:
    """Render the trades screen.

    Args:
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance (passed but not used here).

    Returns:
        A ``Layout`` with header, metrics panel, trades table, and footer.
    """
    trades_data = state.get("trades", {})
    trades_list = trades_data.get("trades", [])

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="metrics", size=7),
        Layout(name="table"),
        Layout(name="footer", size=3),
    )

    layout["header"].update(create_header(state))
    layout["footer"].update(create_footer(active_screen=4))

    if not trades_list:
        layout["metrics"].update(
            create_empty_state("No trades recorded yet — the bot hasn't closed any positions")
        )
        layout["table"].update(create_empty_state(""))
        return layout

    layout["metrics"].update(create_trade_metrics(trades_list))
    layout["table"].update(create_trades_table(trades_list))

    return layout
