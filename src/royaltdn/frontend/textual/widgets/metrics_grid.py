"""KPI card grid widget — renders metrics as Rich columns."""

from typing import Any

from rich.console import Console, RenderableType
from rich.table import Column
from rich.text import Text
from textual.strip import Strip
from textual.widgets import Static


class MetricsGrid(Static):
    """Renders a set of KPI cards in a horizontal grid.

    Each card is a (label, value) pair rendered as Rich markup inside
    a ``Static`` widget.  The layout is a single-row table with one
    column per metric.
    """

    def __init__(self, title: str = "", **kwargs: object) -> None:
        super().__init__("", **kwargs)
        self._title = title
        self._metrics: list[tuple[str, str]] = []

    def update_metrics(self, metrics: list[tuple[str, str]]) -> None:
        """Replace the displayed metrics.

        Args:
            metrics: List of ``(label, value)`` pairs.  Use ``"—"`` for
                missing values.
        """
        self._metrics = metrics
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a single line — we override render for Rich support."""
        return Strip(text="", cell_length=self.size.width)

    def render(self) -> RenderableType:
        """Render the metric grid as a Rich table."""
        if not self._metrics:
            return Text("No metrics available", style="dim italic")

        from rich.table import Column as RichColumn
        from rich.table import Table

        table = Table(
            show_header=False,
            show_edge=False,
            show_lines=False,
            padding=(0, 1),
            collapse_padding=True,
            expand=True,
        )

        # Add one column per metric, equally sized based on count
        col_count = len(self._metrics)
        for _ in self._metrics:
            table.add_column(ratio=1)

        row_cells: list[RenderableType] = []
        for label, value in self._metrics:
            display_value = value if value else "\u2014"
            cell = Text.assemble(
                (f"{label}\n", "bold"),
                (str(display_value), "bold cyan"),
            )
            row_cells.append(cell)

        table.add_row(*row_cells)
        return table
