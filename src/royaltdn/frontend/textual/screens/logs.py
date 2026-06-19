"""Logs screen — level filter input and coloured log output."""

from typing import Any, Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Label

from royaltdn.frontend.textual.widgets.log_panel import LogPanel


class LogsScreen(Screen):
    """Displays log entries with level-based colouring and a filter input.

    Type one of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR`` into the filter
    ``Input`` widget to restrict the displayed log level.
    """

    def compose(self) -> ComposeResult:
        """Build the logs layout."""
        yield Label("[bold]Log Level Filter[/]", id="log-filter-label")
        yield Input(
            placeholder="Filter: DEBUG | INFO | WARNING | ERROR | CLEAR",
            id="log-filter-input",
        )
        yield LogPanel(id="log-panel", max_lines=200)

    def on_mount(self) -> None:
        """Focus the filter input on mount."""
        self.query_one("#log-filter-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle filter input submission.

        Recognised values: ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
        or ``CLEAR`` / empty to reset the filter.
        """
        value = event.value.strip().upper()
        panel = self.query_one("#log-panel", LogPanel)

        if value in ("CLEAR", "", "ALL"):
            panel.set_level(None)
            self.notify("Log filter: ALL")
        elif value in LogPanel.LEVELS:
            panel.set_level(value)
            self.notify(f"Log filter: {value}")
        else:
            self.notify(f"Unknown level: {value}", severity="warning")

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Refresh log entries.

        Args:
            state: ``StateLoader.load_all()`` dict (unused here).
            log_buffer: Log lines from ``LogBuffer.get_lines()``.
        """
        panel = self.query_one("#log-panel", LogPanel)
        panel.update_logs(log_buffer)
