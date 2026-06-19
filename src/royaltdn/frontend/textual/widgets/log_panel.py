"""Log panel widget — wraps RichLog with level-based colouring and filtering."""

from typing import Optional

from textual.widgets import RichLog


class LogPanel(RichLog):
    """A RichLog wrapper that colours log lines by severity level.

    Colours:
        - ``DEBUG``: dim
        - ``INFO``: green
        - ``WARNING`` / ``WARN``: yellow
        - ``ERROR``: red
        - ``CRITICAL``: bold red

    Supports a ``set_level()`` filter so only lines at or above the
    chosen severity are displayed.
    """

    LEVELS = {
        "CRITICAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "INFO": 20,
        "DEBUG": 10,
    }

    LEVEL_COLORS = {
        "CRITICAL": "bold red",
        "ERROR": "red",
        "WARNING": "yellow",
        "INFO": "green",
        "DEBUG": "dim",
    }

    def __init__(self, *, max_lines: int = 200, **kwargs) -> None:
        super().__init__(max_lines=max_lines, highlight=True, **kwargs)
        self._level_filter: Optional[str] = None

    def set_level(self, level: Optional[str]) -> None:
        """Set the minimum level to display.

        Args:
            level: One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
                ``CRITICAL``, or ``None`` to show all.
        """
        self._level_filter = level

    def update_logs(
        self,
        log_lines: list[str],
        level_filter: Optional[str] = None,
    ) -> None:
        """Replace displayed log entries with filtered + coloured lines.

        Args:
            log_lines: Raw log lines from ``LogBuffer.get_lines()``.
            level_filter: Optional filter override for this update.
        """
        if level_filter is not None:
            self._level_filter = level_filter

        self.clear()

        min_level = 0
        if self._level_filter and self._level_filter in self.LEVELS:
            min_level = self.LEVELS[self._level_filter]

        for line in log_lines:
            colour = self._pick_colour(line, min_level)
            if colour is False:
                continue  # filtered out
            self.write(f"[{colour}]{line}[/]")

    def _pick_colour(self, line: str, min_level: int) -> str | bool:
        """Determine the colour for a log line and whether to include it.

        Args:
            line: The log line text.
            min_level: Minimum numeric level to show (0 = all).

        Returns:
            A colour/style string, or ``False`` if the line should be hidden.
        """
        for level_name, level_num in sorted(
            self.LEVELS.items(), key=lambda x: -x[1]
        ):
            if f"| {level_name}" in line or level_name in line:
                if level_num < min_level:
                    return False
                return self.LEVEL_COLORS.get(level_name, "")
        return ""
