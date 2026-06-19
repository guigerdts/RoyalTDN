"""BuilderCanvas — helper widgets for the BuilderScreen.

Provides:
- ConditionRow: a single rule condition with indicator, operator, and value inputs.
"""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Input, Select

from royaltdn.frontend.console.builder_state import (
    INDICATOR_MAP,
    NEEDS_VALUE,
    OPERATOR_GROUPS,
)

# ── Flattened operator options for Select widgets ──────────────────

OPERATOR_OPTIONS: list[tuple[str, str]] = [
    (op["label"], op["key"])
    for group in OPERATOR_GROUPS
    for op in group["operators"]
]

ALL_INDICATOR_OPTIONS: list[tuple[str, str]] = [
    (d["label"], d["name"]) for d in INDICATOR_MAP.values()
]


class ConditionRow(Container):
    """A single condition row: indicator select + operator select + value input.

    The value ``Input`` is hidden by default and only shown when the selected
    operator requires a numeric value (see ``NEEDS_VALUE``).
    """

    _counter: int = 0

    def __init__(
        self,
        indicator_options: list[tuple[str, str]] | None = None,
        operator_options: list[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(classes="condition-row")
        ConditionRow._counter += 1
        self._row_id = f"cr_{ConditionRow._counter}"
        self._indicator_options = indicator_options or ALL_INDICATOR_OPTIONS
        self._operator_options = operator_options or OPERATOR_OPTIONS

    def compose(self) -> ComposeResult:
        yield Select(
            self._indicator_options,
            prompt="Indicador...",
            id=f"ind-{self._row_id}",
        )
        yield Select(
            self._operator_options,
            prompt="Operador...",
            id=f"op-{self._row_id}",
        )
        yield Input(
            placeholder="Valor",
            id=f"val-{self._row_id}",
        )

    def on_mount(self) -> None:
        """Hide value input initially."""
        val_input = self.query_one(f"#val-{self._row_id}", Input)
        val_input.display = False

    def on_select_changed(self, event: Select.Changed) -> None:
        """Show/hide value input when operator selection changes."""
        if event.select.id == f"op-{self._row_id}":
            val_input = self.query_one(f"#val-{self._row_id}", Input)
            val_input.display = event.value in NEEDS_VALUE

    # ── Public helpers ─────────────────────────────────────────────

    def get_condition(self) -> dict[str, Any]:
        """Return the condition dict from this row's current values.

        Returns:
            A dict with keys ``indicator``, ``operator``, and optionally ``value``.
            Empty-string values indicate nothing selected yet.
        """
        ind_select = self.query_one(f"#ind-{self._row_id}", Select)
        op_select = self.query_one(f"#op-{self._row_id}", Select)
        val_input = self.query_one(f"#val-{self._row_id}", Input)

        indicator = ind_select.value if ind_select.value is not Select.BLANK else ""
        operator = op_select.value if op_select.value is not Select.BLANK else ""

        result: dict[str, Any] = {
            "indicator": indicator,
            "operator": operator,
        }

        if val_input.display and val_input.value.strip():
            try:
                result["value"] = float(val_input.value.strip())
            except ValueError:
                pass  # keep non-numeric as string, will fail validation

        return result

    def set_condition(self, condition: dict[str, Any]) -> None:
        """Populate the row widgets from an existing condition dict.

        Args:
            condition: Dict with ``indicator``, ``operator``, and optional ``value``.
        """
        ind_select = self.query_one(f"#ind-{self._row_id}", Select)
        op_select = self.query_one(f"#op-{self._row_id}", Select)
        val_input = self.query_one(f"#val-{self._row_id}", Input)

        if "indicator" in condition:
            ind_select.value = condition["indicator"]
        if "operator" in condition:
            op_select.value = condition["operator"]
            if condition["operator"] in NEEDS_VALUE:
                val_input.display = True
                val_input.value = str(condition.get("value", ""))
