"""Estrategias screen — predefined and user-defined strategies."""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Label


class EstrategiasScreen(Screen):
    """Shows predefined (built-in) and user-defined strategies."""

    def compose(self) -> ComposeResult:
        """Build the estrategias layout."""
        yield Label("[bold]Predefined Strategies[/]", id="predefined-label")
        yield DataTable(id="predefined-table")
        yield Label("[bold]User Strategies[/]", id="user-label")
        yield DataTable(id="user-table")

    def on_mount(self) -> None:
        """Configure table columns."""
        pre = self.query_one("#predefined-table", DataTable)
        pre.add_columns("Name", "Indicators", "Rules", "Status")

        user = self.query_one("#user-table", DataTable)
        user.add_columns("Name", "Symbol", "Timeframe", "Created")

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Refresh strategy tables from state.

        Args:
            state: ``StateLoader.load_all()`` dict.
            log_buffer: Unfiltered log lines (unused here).
        """
        strategies = state.get("strategies", {})
        self._update_predefined(strategies)
        self._update_user(strategies)

    # ── Internal updaters ─────────────────────────────────────────────

    def _update_predefined(self, strategies: dict[str, Any]) -> None:
        table = self.query_one("#predefined-table", DataTable)
        table.clear()

        predefined = strategies.get("predefined", strategies.get("builtin", []))
        if not isinstance(predefined, list):
            predefined = []

        for strat in predefined:
            name = strat.get("name", "\u2014")
            indicators = ", ".join(strat.get("indicators", [])) if isinstance(strat.get("indicators"), list) else "\u2014"
            rules = str(strat.get("rules_count", strat.get("rules", "\u2014")))
            status = strat.get("status", "\u2014")
            table.add_row(name, indicators, rules, status)

    def _update_user(self, strategies: dict[str, Any]) -> None:
        table = self.query_one("#user-table", DataTable)
        table.clear()

        user = strategies.get("user", strategies.get("user_defined", []))
        if not isinstance(user, list):
            user = []

        for strat in user:
            name = strat.get("name", "\u2014")
            symbol = strat.get("symbol", "\u2014")
            tf = strat.get("timeframe", "\u2014")
            created = strat.get("created_at", strat.get("created", "\u2014"))
            table.add_row(name, symbol, tf, created)
