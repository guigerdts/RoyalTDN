"""Custom footer widget — shows key bindings and status message."""

from textual.widgets import Static


class RoyalTDNFooter(Static):
    """Footer bar showing available keys and a transient status message.

    Attributes:
        _status_message: Current bot status shown on the right.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__("", *args, **kwargs)
        self._status_message = "OFFLINE"

    def update_status(self, status_message: str) -> None:
        """Set the status text on the right side of the footer.

        Args:
            status_message: Short status label.
        """
        self._status_message = status_message or "OFFLINE"
        self.update(self._render_text())

    def _render_text(self) -> str:
        """Build the footer string with key hints and status."""
        color = "green" if self._status_message == "ONLINE" else "red"
        return (
            " 1:Dashboard  2:Scanner  3:Estrategias  "
            "4:Trades  5:Logs  "
            "[bold]P[/]:Pause  [bold]R[/]:Resume  "
            "[bold]S[/]:Scan  [bold]Q[/]:Salir  "
            f"|  Bot: [{color}]{self._status_message}[/]"
        )
