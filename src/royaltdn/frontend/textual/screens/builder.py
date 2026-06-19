"""BuilderScreen — strategy builder with 4 tabs: Indicators, Rules, Backtesting, Save/Load."""

from datetime import datetime, timezone
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    TabbedContent,
    TabPane,
)

from royaltdn.frontend.console.builder_state import (
    INDICATOR_MAP,
    NEEDS_VALUE,
    _build_tree,
    _next_id,
)
from royaltdn.frontend.textual.widgets.builder_canvas import (
    ALL_INDICATOR_OPTIONS,
    ConditionRow,
    OPERATOR_OPTIONS,
)


class BuilderScreen(Screen):
    """Builder screen: indicators, rules, backtesting, and save/load.

    State flows:
      1. Indicators tab → user selects + configures indicators
      2. Rules tab     → user builds entry/exit condition trees
      3. Backtesting   → runs the full backtest and shows metrics
      4. Save/Load     → persists / retrieves strategies
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.selected_indicators: list[dict[str, Any]] = []
        self.entry_rules: dict[str, Any] = {"operator": "AND", "conditions": []}
        self.exit_rules: dict[str, Any] = {"operator": "AND", "conditions": []}

    # ── Compose ────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Build the 4-tab layout."""
        with TabbedContent():
            with TabPane("Indicadores", id="tab-indicators"):
                yield Label("Seleccionar indicador:", classes="section-title")
                yield Select(
                    ALL_INDICATOR_OPTIONS,
                    prompt="Elegir indicador...",
                    id="indicator-select",
                )
                yield Container(id="param-inputs")
                yield Button("Agregar indicador", id="add-indicator", variant="primary")
                yield Label("Indicadores seleccionados:", classes="section-title")
                yield ListView(id="selected-indicators-list")
                yield Button("Quitar indicador", id="remove-indicator", variant="error")

            with TabPane("Reglas", id="tab-rules"):
                # ── Entry rules ──
                yield Label("Regla de Entrada", classes="section-title")
                yield Select(
                    [("AND", "AND"), ("OR", "OR")],
                    value="AND",
                    id="entry-logic",
                )
                yield Container(id="entry-conditions", classes="conditions-container")
                yield Button(
                    "Agregar condición (Entrada)",
                    id="add-entry-cond",
                    variant="primary",
                )
                yield Button(
                    "Eliminar condición (Entrada)",
                    id="remove-entry-cond",
                    variant="error",
                )
                yield ListView(id="entry-conditions-list")

                # ── Exit rules ──
                yield Label("Regla de Salida", classes="section-title")
                yield Select(
                    [("AND", "AND"), ("OR", "OR")],
                    value="AND",
                    id="exit-logic",
                )
                yield Container(id="exit-conditions", classes="conditions-container")
                yield Button(
                    "Agregar condición (Salida)",
                    id="add-exit-cond",
                    variant="primary",
                )
                yield Button(
                    "Eliminar condición (Salida)",
                    id="remove-exit-cond",
                    variant="error",
                )
                yield ListView(id="exit-conditions-list")

            with TabPane("Backtesting", id="tab-backtesting"):
                yield Label("Configuración de Backtesting", classes="section-title")
                yield Label("Símbolo:")
                yield Input(value="SPY", placeholder="SPY", id="bt-symbol")
                yield Label("Timeframe:")
                yield Select(
                    [
                        ("1 min", "1min"),
                        ("5 min", "5min"),
                        ("15 min", "15min"),
                        ("1 Hora", "1H"),
                        ("1 Día", "1D"),
                    ],
                    value="1D",
                    id="bt-timeframe",
                )
                yield Label("Período:")
                yield Select(
                    [
                        ("1 año", "1 year"),
                        ("2 años", "2 years"),
                        ("5 años", "5 years"),
                    ],
                    value="2 years",
                    id="bt-period",
                )
                yield Button("Ejecutar Backtesting", id="run-backtest", variant="primary")
                yield RichLog(id="backtest-results", highlight=True, markup=True)

            with TabPane("Guardar/Cargar", id="tab-save-load"):
                yield Label("Guardar Estrategia", classes="section-title")
                yield Input(placeholder="Nombre de la estrategia", id="strategy-name")
                yield Button("Guardar estrategia", id="save-strategy", variant="primary")

                yield Label("Cargar Estrategia", classes="section-title")
                yield Select(
                    [],
                    prompt="Seleccionar estrategia...",
                    id="saved-strategies",
                )
                yield Button("Cargar estrategia", id="load-strategy", variant="primary")
                yield Button("Refrescar lista", id="refresh-list")

    def on_mount(self) -> None:
        """Populate saved strategies list on mount."""
        self._refresh_saved_list()

    # ── update_data placeholder ────────────────────────────────────

    def update_data(self, state: dict[str, Any], log_buffer: list[str]) -> None:
        """Placeholder — BuilderScreen does not poll live data."""
        pass

    # ── Select changed handler ─────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        """Route select changes to appropriate handlers."""
        if event.select.id == "indicator-select":
            self._render_params(event.value)

    # ── Button press handler ───────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Route button presses to the correct handler."""
        btn_id = event.button.id or ""
        handlers: dict[str, Any] = {
            "add-indicator": self._add_indicator,
            "remove-indicator": self._remove_indicator,
            "add-entry-cond": lambda: self._add_condition("entry"),
            "remove-entry-cond": lambda: self._remove_condition("entry"),
            "add-exit-cond": lambda: self._add_condition("exit"),
            "remove-exit-cond": lambda: self._remove_condition("exit"),
            "run-backtest": self._run_backtest,
            "save-strategy": self._save_strategy,
            "load-strategy": self._load_strategy,
            "refresh-list": self._refresh_saved_list,
        }
        handler = handlers.get(btn_id)
        if handler:
            handler()

    # ════════════════════════════════════════════════════════════════
    # Tab: Indicadores
    # ════════════════════════════════════════════════════════════════

    def _render_params(self, indicator_name: Any) -> None:
        """Dynamically render param Input/Select widgets for the selected indicator.

        Args:
            indicator_name: The indicator name from the main select,
                or ``Select.BLANK`` if nothing selected.
        """
        container = self.query_one("#param-inputs", Container)
        container.remove_children()

        if not indicator_name or indicator_name is Select.BLANK:
            return

        ind_def = INDICATOR_MAP.get(indicator_name)
        if not ind_def:
            return

        for param in ind_def.get("params", []):
            pkey = param["key"]
            plabel = param.get("label", pkey)
            ptype = param.get("type", "int")
            default = param.get("default", "")

            if ptype == "select":
                opts = [(o, o) for o in param.get("options", [])]
                container.mount(Label(f"  {plabel}:"))
                container.mount(
                    Select(opts, value=default, id=f"param-{pkey}"),
                )
            else:
                container.mount(Label(f"  {plabel}:"))
                container.mount(
                    Input(placeholder=str(default), id=f"param-{pkey}"),
                )

    def _collect_params(self) -> dict[str, Any]:
        """Read param values from the dynamically rendered param inputs.

        Returns:
            A dict of param key → value (parsed to int/float where applicable).
        """
        selected = self.query_one("#indicator-select", Select)
        ind_name = selected.value
        if not ind_name or ind_name is Select.BLANK:
            return {}

        ind_def = INDICATOR_MAP.get(ind_name)
        if not ind_def:
            return {}

        params: dict[str, Any] = {}
        for param in ind_def.get("params", []):
            pkey = param["key"]
            widget = self.query_one(f"#param-{pkey}")
            ptype = param.get("type", "int")

            if isinstance(widget, Select):
                params[pkey] = widget.value
            elif isinstance(widget, Input):
                raw = widget.value.strip()
                if ptype == "int":
                    try:
                        params[pkey] = int(raw) if raw else param.get("default", 0)
                    except ValueError:
                        params[pkey] = param.get("default", 0)
                elif ptype == "float":
                    try:
                        params[pkey] = float(raw) if raw else param.get("default", 0.0)
                    except ValueError:
                        params[pkey] = param.get("default", 0.0)
                else:
                    params[pkey] = raw if raw else param.get("default", "")
        return params

    def _add_indicator(self) -> None:
        """Add the currently selected + configured indicator to the list."""
        sel = self.query_one("#indicator-select", Select)
        ind_name = sel.value
        if not ind_name or ind_name is Select.BLANK:
            self.notify("Seleccioná un indicador primero", severity="warning")
            return

        ind_def = INDICATOR_MAP.get(ind_name)
        if not ind_def:
            return

        params = self._collect_params()

        # Determine source from params or default
        source = params.pop("source", "close") if "source" in params else "close"

        entry: dict[str, Any] = {
            "id": _next_id(),
            "name": ind_name,
            "label": ind_def["label"],
            "params": params,
            "source": source,
        }
        self.selected_indicators.append(entry)
        self._refresh_indicator_list()
        self.notify(f"Indicador {ind_def['label']} agregado")

    def _remove_indicator(self) -> None:
        """Remove the selected indicator from the list."""
        lv = self.query_one("#selected-indicators-list", ListView)
        if not self.selected_indicators:
            self.notify("No hay indicadores para quitar", severity="warning")
            return
        self.selected_indicators.pop()
        self._refresh_indicator_list()
        self.notify("Último indicador quitado")

    def _refresh_indicator_list(self) -> None:
        """Rebuild the ListView showing selected indicators."""
        lv = self.query_one("#selected-indicators-list", ListView)
        lv.clear()
        if not self.selected_indicators:
            lv.append(ListItem(Label("[dim]Sin indicadores seleccionados[/]")))
        else:
            for ind in self.selected_indicators:
                label = ind.get("label", ind["name"])
                params_str = ", ".join(
                    f"{k}={v}" for k, v in ind.get("params", {}).items()
                )
                text = f"{label} [{params_str}]" if params_str else label
                lv.append(ListItem(Label(text)))

    # ════════════════════════════════════════════════════════════════
    # Tab: Reglas
    # ════════════════════════════════════════════════════════════════

    def _get_indicator_options(self) -> list[tuple[str, str]]:
        """Build indicator options from currently selected indicators.

        Returns:
            A list of (label, value) tuples for the ConditionRow Select,
            or ``ALL_INDICATOR_OPTIONS`` if no indicators are selected.
        """
        if not self.selected_indicators:
            return ALL_INDICATOR_OPTIONS
        return [
            (ind["name"], ind["name"])
            for ind in self.selected_indicators
        ]

    def _add_condition(self, entry_or_exit: str) -> None:
        """Mount a new ConditionRow into the Entry or Exit container.

        Args:
            entry_or_exit: ``"entry"`` or ``"exit"``.
        """
        container_id = f"{entry_or_exit}-conditions"
        cont = self.query_one(f"#{container_id}", Container)
        row = ConditionRow(indicator_options=self._get_indicator_options())
        cont.mount(row)
        self._refresh_conditions_list(entry_or_exit)

    def _remove_condition(self, entry_or_exit: str) -> None:
        """Remove the last ConditionRow from the Entry or Exit container.

        Args:
            entry_or_exit: ``"entry"`` or ``"exit"``.
        """
        container_id = f"{entry_or_exit}-conditions"
        cont = self.query_one(f"#{container_id}", Container)
        children = list(cont.children)
        if not children:
            self.notify("No hay condiciones para eliminar", severity="warning")
            return
        children[-1].remove()
        self._refresh_conditions_list(entry_or_exit)

    def _collect_condition_rows(self, entry_or_exit: str) -> list[dict[str, Any]]:
        """Read all ConditionRow values from the given container.

        Args:
            entry_or_exit: ``"entry"`` or ``"exit"``.

        Returns:
            List of condition dicts.
        """
        container_id = f"{entry_or_exit}-conditions"
        cont = self.query_one(f"#{container_id}", Container)
        conditions: list[dict[str, Any]] = []
        for child in cont.children:
            if isinstance(child, ConditionRow):
                cond = child.get_condition()
                if cond.get("indicator") and cond.get("operator"):
                    # Enrich with indicator params & source
                    ind_name = cond["indicator"]
                    matching = [
                        i for i in self.selected_indicators if i["name"] == ind_name
                    ]
                    if matching:
                        cond["params"] = matching[0]["params"]
                        cond["source"] = matching[0].get("source", "close")
                    conditions.append(cond)
        return conditions

    def _refresh_conditions_list(self, entry_or_exit: str) -> None:
        """Update the read-only ListView for the given rule section.

        Args:
            entry_or_exit: ``"entry"`` or ``"exit"``.
        """
        list_id = f"{entry_or_exit}-conditions-list"
        lv = self.query_one(f"#{list_id}", ListView)
        lv.clear()
        conditions = self._collect_condition_rows(entry_or_exit)

        logic_select = self.query_one(f"#{entry_or_exit}-logic", Select)
        logic = logic_select.value if logic_select.value is not Select.BLANK else "AND"

        if not conditions:
            lv.append(ListItem(Label("[dim]Sin condiciones[/]")))
        else:
            for c in conditions:
                ind = c.get("indicator", "?")
                op = c.get("operator", "?")
                val = c.get("value", "")
                label = f"{ind} {op} {val}" if val else f"{ind} {op}"
                lv.append(ListItem(Label(label)))
            # Show logic at the top
            lv.append(ListItem(Label(f"[bold]Lógica: {logic}[/]")))

    # ════════════════════════════════════════════════════════════════
    # Tab: Backtesting
    # ════════════════════════════════════════════════════════════════

    def _build_config(self) -> dict[str, Any]:
        """Assemble a full strategy config from the current screen state.

        Returns:
            Strategy config dict suitable for ``validate_config`` and ``run_backtest``.
        """
        # Collect conditions from entry / exit rows
        entry_conds = self._collect_condition_rows("entry")
        exit_conds = self._collect_condition_rows("exit")

        entry_logic = self.query_one("#entry-logic", Select)
        exit_logic = self.query_one("#exit-logic", Select)

        entry_tree = _build_tree(
            entry_logic.value if entry_logic.value is not Select.BLANK else "AND",
            entry_conds,
        )
        exit_tree = _build_tree(
            exit_logic.value if exit_logic.value is not Select.BLANK else "AND",
            exit_conds,
        )

        indicators = [
            {
                "name": ind["name"],
                "params": ind.get("params", {}),
                "source": ind.get("source", "close"),
            }
            for ind in self.selected_indicators
        ]

        return {
            "version": 1,
            "name": "Builder Test",
            "description": "",
            "symbols": ["SPY"],
            "timeframe": "1D",
            "indicators": indicators,
            "entry_rules": entry_tree,
            "exit_rules": exit_tree,
            "risk_management": {
                "stop_loss_pct": 2.0,
                "take_profit_pct": 5.0,
                "max_position_size": 25.0,
                "max_daily_loss": 10.0,
            },
        }

    def _run_backtest(self) -> None:
        """Execute backtest with current screen state and display results."""
        # Read form values
        symbol_input = self.query_one("#bt-symbol", Input)
        tf_select = self.query_one("#bt-timeframe", Select)
        period_select = self.query_one("#bt-period", Select)

        symbol = symbol_input.value.strip() or "SPY"
        timeframe = tf_select.value if tf_select.value is not Select.BLANK else "1D"
        period = period_select.value if period_select.value is not Select.BLANK else "2 years"

        # Build and validate config
        config = self._build_config()
        config["symbols"] = [symbol]
        config["timeframe"] = timeframe

        try:
            from royaltdn.strategy.backtesting import run_backtest
            from royaltdn.strategy.schema import validate_config
        except ImportError:
            self.notify("Backtesting no disponible (falta numpy/pandas)", severity="error")
            return

        ok, err = validate_config(config)
        if not ok:
            self.notify(f"Config inválida: {err}", severity="error")
            return

        # Show running state
        results_widget = self.query_one("#backtest-results", RichLog)
        results_widget.clear()
        results_widget.write("[yellow]Ejecutando backtesting...[/]")

        # Run backtest
        result = run_backtest(config, symbol=symbol, timeframe=timeframe, period=period)

        # Display results
        results_widget.clear()

        if "error" in result:
            err_msg = result["error"]
            metrics = result.get("metrics", {})
            if metrics.get("num_trades", 0) == 0:
                results_widget.write("[yellow]Estrategia no generó trades en el período seleccionado[/]")
            else:
                results_widget.write(f"[red]Error: {err_msg}[/]")
            return

        metrics = result.get("metrics", {})
        if not metrics or metrics.get("num_trades", 0) == 0:
            results_widget.write("[yellow]Estrategia no generó trades en el período seleccionado[/]")
            return

        # Format metrics
        lines = [
            "[bold]Resultados del Backtesting[/]",
            "",
            "[bold]Rendimiento:[/]",
            f"  Sharpe: {metrics.get('sharpe', 0):.2f}  |  "
            f"Sortino: {metrics.get('sortino', 0):.2f}  |  "
            f"Profit Factor: {metrics.get('profit_factor', 0):.2f}",
            f"  Win Rate: {metrics.get('win_rate', 0) * 100:.1f}%  |  "
            f"Max DD: {metrics.get('max_drawdown', 0) * 100:.1f}%  |  "
            f"Total Return: {metrics.get('total_return', 0) * 100:+.1f}%",
            f"  CAGR: {metrics.get('cagr', 0) * 100:.1f}%  |  "
            f"Trades: {metrics.get('num_trades', 0)}",
        ]
        results_widget.write("\n".join(lines))

    # ════════════════════════════════════════════════════════════════
    # Tab: Guardar / Cargar
    # ════════════════════════════════════════════════════════════════

    def _save_strategy(self) -> None:
        """Save the current strategy via ``StrategyStore``."""
        try:
            from royaltdn.strategy.schema import validate_config
            from royaltdn.strategy.strategy_store import StrategyStore
        except ImportError:
            self.notify("StrategyStore no disponible (falta numpy/pandas)", severity="error")
            return

        name_input = self.query_one("#strategy-name", Input)
        name = name_input.value.strip()
        if not name:
            self.notify("Ingresá un nombre para la estrategia", severity="warning")
            return

        # Build full config
        config = self._build_config()
        config["name"] = name
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        config["created_at"] = now_iso

        # Validate
        ok, err = validate_config(config)
        if not ok:
            self.notify(f"Config inválida: {err}", severity="error")
            return

        try:
            StrategyStore().save(config)
            self.notify(f"Estrategia '{name}' guardada")
            self._refresh_saved_list()
        except Exception as e:
            self.notify(f"Error al guardar: {e}", severity="error")

    def _load_strategy(self) -> None:
        """Load a saved strategy and populate all tabs."""
        try:
            from royaltdn.strategy.strategy_store import StrategyStore
        except ImportError:
            self.notify("StrategyStore no disponible (falta numpy/pandas)", severity="error")
            return

        sel = self.query_one("#saved-strategies", Select)
        name = sel.value
        if not name or name is Select.BLANK:
            self.notify("Seleccioná una estrategia de la lista", severity="warning")
            return

        config = StrategyStore().load(name)
        if config is None:
            self.notify(f"No se encontró la estrategia '{name}'", severity="error")
            return

        # Populate indicators
        self.selected_indicators = []
        for ind in config.get("indicators", []):
            self.selected_indicators.append({
                "id": _next_id(),
                "name": ind["name"],
                "label": INDICATOR_MAP.get(ind["name"], {}).get("label", ind["name"]),
                "params": ind.get("params", {}),
                "source": ind.get("source", "close"),
            })
        self._refresh_indicator_list()

        # Populate rules
        entry_rules = config.get("entry_rules", {})
        exit_rules = config.get("exit_rules", {})

        # Set logic selects
        self.query_one("#entry-logic", Select).value = entry_rules.get("operator", "AND")
        self.query_one("#exit-logic", Select).value = exit_rules.get("operator", "AND")

        # Clear and rebuild condition rows
        self._rebuild_conditions_from_tree("entry", entry_rules)
        self._rebuild_conditions_from_tree("exit", exit_rules)

        self.notify(f"Estrategia '{name}' cargada")

    def _rebuild_conditions_from_tree(self, entry_or_exit: str, tree: dict) -> None:
        """Clear condition container and rebuild rows from a rule tree.

        Args:
            entry_or_exit: ``"entry"`` or ``"exit"``.
            tree: Rule tree dict with ``operator`` and ``conditions``.
        """
        container_id = f"{entry_or_exit}-conditions"
        cont = self.query_one(f"#{container_id}", Container)
        cont.remove_children()

        conditions = tree.get("conditions", [])
        for cond in conditions:
            if "operator" in cond and "indicator" in cond:
                row = ConditionRow(indicator_options=self._get_indicator_options())
                row.set_condition(cond)
                cont.mount(row)

        self._refresh_conditions_list(entry_or_exit)

    def _refresh_saved_list(self) -> None:
        """Refresh the saved strategies Select from ``StrategyStore``."""
        sel = self.query_one("#saved-strategies", Select)
        try:
            from royaltdn.strategy.strategy_store import StrategyStore
            names = StrategyStore().list_names()
            sel.set_options([(n, n) for n in names])
        except ImportError:
            # numpy/pandas not available — skip strategy store
            self.notify("StrategyStore no disponible (falta numpy/pandas)", severity="warning")
            sel.set_options([])
        except Exception:
            sel.set_options([])
