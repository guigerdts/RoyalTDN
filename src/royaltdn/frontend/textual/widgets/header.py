"""Custom header widget — shows bot name, mode, status, uptime, scanner info."""

from textual.widgets import Static


class RoyalTDNHeader(Static):
    """Header bar showing the bot operational status.

    Attributes:
        _status: Bot status string (e.g. ONLINE / OFFLINE / PAUSED).
        _mode: Trading mode (e.g. paper / live).
        _uptime: Elapsed uptime string.
        _scanner_info: Last scan info or indicator.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__("", *args, **kwargs)
        self._status = "OFFLINE"
        self._mode = "paper"
        self._uptime = "0:00:00"
        self._scanner_info = "\u2014"

    def update_data(
        self,
        status: str,
        mode: str,
        uptime: str,
        scanner_info: str,
    ) -> None:
        """Refresh the header content.

        Args:
            status: Bot status string.
            mode: Trading mode.
            uptime: Uptime string.
            scanner_info: Scanner status or last scan label.
        """
        self._status = status or "OFFLINE"
        self._mode = mode or "paper"
        self._uptime = uptime or "0:00:00"
        self._scanner_info = scanner_info or "\u2014"
        self.update(self._render_text())

    def _render_text(self) -> str:
        """Build the header string with Rich markup."""
        color = "green" if self._status == "ONLINE" else "red"

        # Use Rich markup to color the status badge
        return (
            f" ROYALTDN BOT  |  {self._mode}  |  "
            f"[bold {color}]{self._status}[/]  |  "
            f"Uptime: {self._uptime}  |  "
            f"Scanner: {self._scanner_info} "
        )
