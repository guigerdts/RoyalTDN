"""Rich interactive text menu for RoyalTDN — replaces Textual TUI on Termux.

All rendering uses ONLY 16-color ANSI names (no 24-bit hex colors).
All imports are lazy (function-level) to avoid import errors at module load.
"""

import time


# ── Entry point ────────────────────────────────────────────────────────


def run_menu(logs_dir: str = "logs") -> None:
    """Rich interactive menu — replaces Textual TUI on Termux."""
    from rich.console import Console

    from royaltdn.frontend.console.components.state import StateLoader
    from royaltdn.frontend.console.log_handler import LogBuffer, setup_console_log_handler

    state_loader = StateLoader(logs_dir)
    log_buffer = LogBuffer(max_lines=200)
    setup_console_log_handler(log_buffer)
    console = Console(color_system="standard")

    try:
        while True:
            _clear_screen()
            _print_header(console)
            _print_menu(console)
            try:
                cmd = input(">> ").strip()
            except KeyboardInterrupt:
                print()
                cmd = "_ctrl_c"

            if cmd == "1":
                _show_dashboard(state_loader, log_buffer, console)
            elif cmd == "2":
                _show_scanner(state_loader, console, logs_dir)
            elif cmd == "3":
                _show_estrategias(state_loader, console)
            elif cmd == "4":
                _show_trades(state_loader, console)
            elif cmd == "5":
                _show_logs(log_buffer, console)
            elif cmd == "6":
                _show_control(console, logs_dir)
            elif cmd == "0":
                break
            elif cmd == "_ctrl_c":
                # Ctrl+C at main prompt — ask to quit
                print("\n[bold yellow]¿Salir? (s/n): [/]", end="", flush=True)
                try:
                    resp = input().strip().lower()
                except (KeyboardInterrupt, EOFError):
                    resp = "s"
                if resp == "s":
                    break
                # otherwise continue loop
            else:
                console.print("[bold red]Opción inválida. Presiona Enter para continuar.[/]")
                _wait_enter()

    except KeyboardInterrupt:
        pass  # fall through to stop message

    console.print("[bold yellow]Bot detenido.[/]")


# ── Core helpers ───────────────────────────────────────────────────────


def _clear_screen() -> None:
    """Clear terminal screen via ANSI escape codes."""
    print("\033[2J\033[H", end="")


def _print_header(console) -> None:
    """Render a Rich Panel header with bot title."""
    from rich.panel import Panel
    from rich.text import Text

    title = Text("RoyalTDN Trading Bot", style="bold white")
    subtitle = Text("Menú Interactivo", style="dim white")
    console.print(
        Panel(
            subtitle,
            title=title,
            border_style="white",
            padding=(0, 1),
        )
    )


def _print_menu(console) -> None:
    """Render the main menu as a Rich Table."""
    from rich.table import Table
    from rich.text import Text

    table = Table(show_header=False, border_style="white", box=None, padding=(0, 2))
    table.add_column("key", style="bold cyan", width=4)
    table.add_column("desc")

    items = [
        ("1", "Dashboard — vista general del bot"),
        ("2", "Scanner — resultados de escaneo"),
        ("3", "Estrategias — ver estrategias cargadas"),
        ("4", "Trades — historial y resumen"),
        ("5", "Logs — registros del sistema"),
        ("6", "Control — pausar/reanudar bot"),
        ("0", "Salir"),
    ]
    for key, desc in items:
        table.add_row(key, desc)

    console.print(table)


def _wait_enter() -> None:
    """Wait for Enter key press, handling Ctrl+C gracefully."""
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


# ── Dashboard ──────────────────────────────────────────────────────────


def _show_dashboard(state_loader, log_buffer, console) -> None:
    """Screen 1: Dashboard with KPIs, positions, signals, summary, logs."""
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.console import Group

    try:
        while True:
            _clear_screen()
            _print_header(console)

            state = state_loader.load_all()
            # load_all() does NOT include signals; load separately
            signals = state_loader._load_file("signals.json", {})
            state["signals"] = signals
            log_lines = log_buffer.get_lines()

            sections: list = []

            # ── KPIs ─────────────────────────────────────────────────
            _build_kpis(state, sections, Panel, Table, Text)

            # ── Open Positions ───────────────────────────────────────
            _build_positions(state, sections, Panel, Table, Text)

            # ── Last Signals ─────────────────────────────────────────
            _build_signals(state, sections, Panel, Table, Text)

            # ── Trade Summary ────────────────────────────────────────
            _build_summary(state, sections, Panel, Table, Text)

            # ── Logs (last 20) ──────────────────────────────────────
            _build_log_section(log_lines, sections, Panel, Text)

            console.print(Group(*sections))

            # Prompt
            try:
                cmd = input(
                    "¿Actualizar? (Enter=sí, 0=volver, N=auto cada Ns): "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                return

            if cmd == "0":
                return

            if cmd.isdigit() and int(cmd) > 0:
                interval = int(cmd)
                while True:
                    try:
                        time.sleep(interval)
                    except KeyboardInterrupt:
                        return  # Ctrl+C exits dashboard
                    _clear_screen()
                    _print_header(console)
                    state = state_loader.load_all()
                    signals = state_loader._load_file("signals.json", {})
                    state["signals"] = signals
                    log_lines = log_buffer.get_lines()
                    sections = []
                    _build_kpis(state, sections, Panel, Table, Text)
                    _build_positions(state, sections, Panel, Table, Text)
                    _build_signals(state, sections, Panel, Table, Text)
                    _build_summary(state, sections, Panel, Table, Text)
                    _build_log_section(log_lines, sections, Panel, Text)
                    console.print(Group(*sections))
            # Enter or anything else → loop and refresh

    except KeyboardInterrupt:
        return


# ── Dashboard sub-builders (match dashboard.py patterns) ──────────────


def _build_kpis(
    state: dict,
    sections: list,
    Panel: type,
    Table: type,
    Text: type,
) -> None:
    """Build KPI grid: Status, Equity, P&L Día, DD%, Win Rate, Posiciones, Scan."""
    status = state.get("status", {})
    equity = state.get("equity", {})
    trades = state.get("trades", {})
    positions = state.get("positions", {})

    pos_list = (
        positions.get("open_positions", [])
        if isinstance(positions, dict)
        else []
    )
    if not isinstance(pos_list, list):
        pos_list = []

    scanner_info = "\u2014"
    scanner = state.get("scanner", {})
    if isinstance(scanner, dict):
        last = scanner.get("last_scan", {})
        if isinstance(last, dict) and last.get("timestamp"):
            scanner_info = str(last["timestamp"])[-8:]

    rows = [
        ("Status", status.get("bot_status", "\u2014"), "bold white"),
        ("Equity", f"${float(equity.get('current_equity', 0)):,.2f}", "bold cyan"),
        (
            "P&L D\u00eda",
            f"${float(equity.get('pnl_day', 0)):+,.2f}",
            (
                "bold green"
                if float(equity.get("pnl_day", 0)) >= 0
                else "bold red"
            ),
        ),
        ("DD", f"{float(equity.get('drawdown_pct', 0)):+.2f}%", "bold yellow"),
        ("WR", f"{float(trades.get('win_rate', 0)):.1f}%", "bold cyan"),
        ("Pos", str(len(pos_list)), "bold white"),
        ("Scan", scanner_info, "bold white"),
    ]

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="center", ratio=1)
    cells = []
    for label, value, style in rows:
        cells.append(
            Text.assemble((f"{label}\n", "bold white"), (str(value), style))
        )
    table.add_row(*cells)

    sections.append(Panel(table, title="KPIs", border_style="white"))


def _build_positions(
    state: dict,
    sections: list,
    Panel: type,
    Table: type,
    Text: type,
) -> None:
    """Build open positions table (or placeholder)."""
    positions_data = state.get("positions", {})
    if not isinstance(positions_data, dict):
        sections.append(
            Panel(
                Text("No position data", style="dim white"),
                title="Open Positions",
                border_style="white",
            )
        )
        return

    positions = positions_data.get("open_positions", [])
    if not isinstance(positions, list) or not positions:
        sections.append(
            Panel(
                Text("No open positions", style="dim white"),
                title="Open Positions",
                border_style="white",
            )
        )
        return

    table = Table(title=None, border_style="white", header_style="bold white")
    table.add_column("Symbol", style="bold white")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("P&L", justify="right")

    for pos in positions:
        symbol = str(pos.get("symbol", "\u2014"))
        side = str(pos.get("side", pos.get("direction", "\u2014")))
        qty_raw = pos.get("qty", pos.get("quantity", "\u2014"))
        qty = (
            f"{qty_raw:.2f}"
            if isinstance(qty_raw, (int, float))
            else str(qty_raw)
        )
        entry_raw = pos.get("entry_price", pos.get("avg_entry_price", 0))
        entry = f"${float(entry_raw):,.2f}" if entry_raw else "\u2014"
        pnl_raw = pos.get("unrealized_pl", pos.get("pnl", 0))
        pnl = (
            f"${float(pnl_raw):+,.2f}"
            if isinstance(pnl_raw, (int, float))
            else "\u2014"
        )
        pnl_style = (
            "green"
            if (isinstance(pnl_raw, (int, float)) and pnl_raw >= 0)
            else "red"
        )
        table.add_row(symbol, side, qty, entry, f"[{pnl_style}]{pnl}[/]")

    sections.append(Panel(table, title="Open Positions", border_style="white"))


def _build_signals(
    state: dict,
    sections: list,
    Panel: type,
    Table: type,
    Text: type,
) -> None:
    """Build last signals table (or placeholder)."""
    signals_data = state.get("signals", {})
    if not isinstance(signals_data, dict):
        sections.append(
            Panel(
                Text("No signal data", style="dim white"),
                title="Last Signals",
                border_style="white",
            )
        )
        return

    last_signals = signals_data.get("last_signals", [])
    if not isinstance(last_signals, list) or not last_signals:
        count = signals_data.get("today_count", 0)
        text = (
            f"No signals today ({count} total)"
            if count
            else "Waiting for bot signals..."
        )
        sections.append(
            Panel(
                Text(text, style="dim white"),
                title="Last Signals",
                border_style="white",
            )
        )
        return

    table = Table(title=None, border_style="white", header_style="bold white")
    table.add_column("Action")
    table.add_column("Symbol", style="bold white")
    table.add_column("Price", justify="right")
    table.add_column("Strategy")
    table.add_column("Time")

    for s in last_signals[:10]:
        action = s.get("action", "?")
        action_style = (
            "green"
            if action == "BUY"
            else ("red" if action == "SELL" else "white")
        )
        symbol = str(s.get("symbol", "?"))
        price_raw = s.get("price", "")
        price = f"${float(price_raw):,.2f}" if price_raw else "\u2014"
        strategy = str(s.get("strategy", ""))
        ts = str(s.get("timestamp", ""))[-8:] if s.get("timestamp") else ""
        table.add_row(f"[{action_style}]{action}[/]", symbol, price, strategy, ts)

    sections.append(Panel(table, title="Last Signals", border_style="white"))


def _build_summary(
    state: dict,
    sections: list,
    Panel: type,
    Table: type,
    Text: type,
) -> None:
    """Build trade summary grid (or placeholder)."""
    trades = state.get("trades", {})
    if not isinstance(trades, dict) or not trades.get("total_trades"):
        sections.append(
            Panel(
                Text("No trades executed yet", style="dim white"),
                title="Trade Summary",
                border_style="white",
            )
        )
        return

    total = trades.get("total_trades", 0)
    win_rate = trades.get("win_rate", 0)
    profit_factor = trades.get("profit_factor", 0)
    total_pnl = trades.get("total_pnl", 0)

    table = Table.grid(padding=(0, 3))
    table.add_column(justify="center", ratio=1)
    pnl_style = "green" if float(total_pnl) >= 0 else "red"
    cells = [
        Text.assemble(("Total\n", "bold white"), (str(total), "bold white")),
        Text.assemble(
            ("Win Rate\n", "bold white"),
            (f"{float(win_rate):.1f}%", "bold cyan"),
        ),
        Text.assemble(
            ("Profit Factor\n", "bold white"),
            (f"{float(profit_factor):.2f}", "bold cyan"),
        ),
        Text.assemble(
            ("Total P&L\n", "bold white"),
            (f"${float(total_pnl):+,.2f}", pnl_style),
        ),
    ]
    table.add_row(*cells)

    sections.append(Panel(table, title="Trade Summary", border_style="white"))


def _build_log_section(
    log_lines: list[str],
    sections: list,
    Panel: type,
    Text: type,
) -> None:
    """Build logs section with colorized levels."""
    if not log_lines:
        sections.append(
            Panel(
                Text("No log entries", style="dim white"),
                title="Logs",
                border_style="white",
            )
        )
        return

    lines = []
    for line in log_lines[-20:]:
        style = "white"
        if "CRITICAL" in line or "ERROR" in line:
            style = "bold red"
        elif "WARNING" in line or "WARN" in line:
            style = "yellow"
        elif "INFO" in line:
            style = "green"
        elif "DEBUG" in line:
            style = "dim white"
        lines.append(Text(line.strip(), style=style))

    from rich.console import Group as RichGroup

    sections.append(
        Panel(RichGroup(*lines), title="Logs", border_style="white")
    )


# ── Scanner ────────────────────────────────────────────────────────────


def _show_scanner(state_loader, console, logs_dir: str) -> None:
    """Screen 2: Show last scan results, optionally trigger a new scan."""
    from rich.table import Table
    from rich.panel import Panel

    try:
        data = state_loader.load_scanner_results()
        last_scan = data.get("last_scan", {})

        console.print(
            Panel(
                "[bold]Último escaneo[/]",
                border_style="white",
            )
        )

        if last_scan and isinstance(last_scan, dict) and last_scan.get("symbols"):
            table = Table(title=None, border_style="white", header_style="bold white")
            table.add_column("Symbol", style="bold white")
            table.add_column("Price", justify="right")
            table.add_column("Signal")
            table.add_column("Score", justify="right")

            for sym in last_scan["symbols"]:
                if isinstance(sym, dict):
                    table.add_row(
                        str(sym.get("symbol", "?")),
                        f"${float(sym.get('price', 0)):.4f}"
                        if sym.get("price")
                        else "\u2014",
                        str(sym.get("signal", "\u2014")),
                        f"{float(sym.get('score', 0)):.2f}"
                        if sym.get("score")
                        else "\u2014",
                    )
            console.print(table)
        else:
            console.print("[dim]No hay resultados de escaneo aún.[/]")

        if last_scan.get("timestamp"):
            console.print(f"\nTimestamp: [cyan]{last_scan['timestamp']}[/]")

        console.print()
        try:
            force = input("¿Forzar escaneo ahora? (s/n): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return

        if force == "s":
            from royaltdn.frontend.console.commands import trigger_scanner

            trigger_scanner(logs_dir)
            console.print("[yellow]Escaneo disparado. Esperando...[/]")
            time.sleep(5)
            # Reload and show updated results
            data = state_loader.load_scanner_results()
            last_scan = data.get("last_scan", {})
            console.print(
                Panel(
                    "[bold]Resultados actualizados[/]",
                    border_style="white",
                )
            )
            if last_scan and isinstance(last_scan, dict) and last_scan.get("symbols"):
                table = Table(
                    title=None, border_style="white", header_style="bold white"
                )
                table.add_column("Symbol", style="bold white")
                table.add_column("Price", justify="right")
                table.add_column("Signal")
                table.add_column("Score", justify="right")
                for sym in last_scan["symbols"]:
                    if isinstance(sym, dict):
                        table.add_row(
                            str(sym.get("symbol", "?")),
                            f"${float(sym.get('price', 0)):.4f}"
                            if sym.get("price")
                            else "\u2014",
                            str(sym.get("signal", "\u2014")),
                            f"{float(sym.get('score', 0)):.2f}"
                            if sym.get("score")
                            else "\u2014",
                        )
                console.print(table)
            else:
                console.print("[dim]No hay resultados de escaneo aún.[/]")

        console.print("\n[dim]Presiona Enter para volver[/]")
        _wait_enter()

    except KeyboardInterrupt:
        return


# ── Estrategias (NO BUILDER) ──────────────────────────────────────────


def _show_estrategias(state_loader, console) -> None:
    """Screen 3: List strategies from state + StrategyStore (no Builder)."""
    from rich.table import Table
    from rich.panel import Panel

    try:
        while True:
            _clear_screen()
            _print_header(console)

            state_strategies = state_loader.load_strategies()

            try:
                from royaltdn.strategy.strategy_store import StrategyStore

                user_strategies = StrategyStore().load_all()
            except Exception:
                user_strategies = []

            console.print(
                Panel(
                    "[bold]Estrategias Cargadas[/]",
                    border_style="white",
                )
            )

            # Show predefined strategies from state
            predefined = state_strategies.get("strategies", [])
            if isinstance(predefined, list) and predefined:
                table = Table(
                    title="Predefinidas",
                    border_style="white",
                    header_style="bold white",
                )
                table.add_column("Nombre", style="bold white")
                table.add_column("Tipo")
                table.add_column("Activa")
                for strat in predefined:
                    if isinstance(strat, dict):
                        table.add_row(
                            str(strat.get("name", "\u2014")),
                            str(strat.get("type", "\u2014")),
                            "Sí" if strat.get("active") else "No",
                        )
                console.print(table)
            else:
                console.print("[dim]No hay estrategias predefinidas cargadas.[/]")

            # Show user-defined strategies from StrategyStore
            if user_strategies:
                table2 = Table(
                    title="Usuario",
                    border_style="white",
                    header_style="bold white",
                )
                table2.add_column("Nombre", style="bold white")
                table2.add_column("Símbolo")
                table2.add_column("Timeframe")
                for cfg in user_strategies:
                    if isinstance(cfg, dict):
                        table2.add_row(
                            str(cfg.get("name", "\u2014")),
                            str(cfg.get("symbol", "\u2014")),
                            str(cfg.get("timeframe", "\u2014")),
                        )
                console.print(table2)

            console.print()
            console.print(
                "[bold cyan]1[/] Ver estrategias cargadas  "
                "[bold cyan]2[/] Crear nueva estrategia  "
                "[bold cyan]0[/] Volver"
            )
            try:
                sub = input(">> ").strip()
            except (KeyboardInterrupt, EOFError):
                return

            if sub == "0":
                return
            elif sub == "1":
                # Already shown above, just wait
                _wait_enter()
            elif sub == "2":
                console.print(
                    "[dim]Builder disponible en próxima versión[/]"
                )
                _wait_enter()
            else:
                console.print("[bold red]Opción inválida.[/]")
                _wait_enter()

    except KeyboardInterrupt:
        return


# ── Trades ─────────────────────────────────────────────────────────────


def _show_trades(state_loader, console) -> None:
    """Screen 4: Trade summary + trade list with optional symbol filter."""
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    try:
        _clear_screen()
        _print_header(console)

        data = state_loader.load_trades()

        # Summary
        total = data.get("total_trades", 0)
        win_rate = data.get("win_rate", 0)
        profit_factor = data.get("profit_factor", 0)
        total_pnl = data.get("total_pnl", 0)

        pnl_style = "green" if float(total_pnl) >= 0 else "red"
        summary = Table.grid(padding=(0, 3))
        summary.add_column(justify="center", ratio=1)
        summary.add_row(
            Text.assemble(("Total\n", "bold white"), (str(total), "bold white")),
            Text.assemble(
                ("Win Rate\n", "bold white"),
                (f"{float(win_rate):.1f}%", "bold cyan"),
            ),
            Text.assemble(
                ("Profit Factor\n", "bold white"),
                (f"{float(profit_factor):.2f}", "bold cyan"),
            ),
            Text.assemble(
                ("Total P&L\n", "bold white"),
                (f"${float(total_pnl):+,.2f}", pnl_style),
            ),
        )
        console.print(Panel(summary, title="Trade Summary", border_style="white"))

        # Filter prompt
        try:
            symbol_filter = (
                input("Filtrar por símbolo (Enter=todos): ").strip().upper()
            )
        except (KeyboardInterrupt, EOFError):
            return

        trades_list = data.get("trades", [])
        if not isinstance(trades_list, list):
            trades_list = []

        if symbol_filter:
            trades_list = [
                t
                for t in trades_list
                if str(t.get("symbol", "")).upper() == symbol_filter
            ]

        if trades_list:
            table = Table(
                title=None, border_style="white", header_style="bold white"
            )
            table.add_column("Symbol", style="bold white")
            table.add_column("Side")
            table.add_column("Qty", justify="right")
            table.add_column("Entry", justify="right")
            table.add_column("Exit", justify="right")
            table.add_column("P&L", justify="right")

            for t in trades_list:
                if not isinstance(t, dict):
                    continue
                symbol = str(t.get("symbol", "\u2014"))
                side = str(t.get("side", "\u2014"))
                qty_raw = t.get("qty", t.get("quantity", "\u2014"))
                qty = (
                    f"{qty_raw:.4f}"
                    if isinstance(qty_raw, (int, float))
                    else str(qty_raw)
                )
                entry_raw = t.get("entry_price", t.get("price", 0))
                entry = (
                    f"${float(entry_raw):,.2f}" if entry_raw else "\u2014"
                )
                exit_raw = t.get("exit_price", "")
                exit_val = (
                    f"${float(exit_raw):,.2f}" if exit_raw else "\u2014"
                )
                pnl_raw = t.get("pnl", t.get("profit_loss", 0))
                pnl = (
                    f"${float(pnl_raw):+,.2f}"
                    if isinstance(pnl_raw, (int, float))
                    else "\u2014"
                )
                pnl_style = (
                    "green"
                    if (isinstance(pnl_raw, (int, float)) and pnl_raw >= 0)
                    else "red"
                )
                table.add_row(
                    symbol, side, qty, entry, exit_val, f"[{pnl_style}]{pnl}[/]"
                )

            console.print(table)
        else:
            msg = (
                f"No trades for symbol '{symbol_filter}'"
                if symbol_filter
                else "No trades yet"
            )
            console.print(f"[dim]{msg}[/]")

        console.print("\n[dim]Presiona Enter para volver[/]")
        _wait_enter()

    except KeyboardInterrupt:
        return


# ── Logs ───────────────────────────────────────────────────────────────


def _show_logs(log_buffer, console) -> None:
    """Screen 5: Log viewer with level filter and text search."""
    from rich.text import Text
    from rich.panel import Panel
    from rich.console import Group as RichGroup

    try:
        current_level = None
        current_text = None

        while True:
            _clear_screen()
            _print_header(console)

            lines = log_buffer.get_lines(
                level_filter=current_level, text_filter=current_text, last_n=20
            )

            if lines:
                rendered = []
                for line in lines:
                    style = "white"
                    if "CRITICAL" in line or "ERROR" in line:
                        style = "bold red"
                    elif "WARNING" in line or "WARN" in line:
                        style = "yellow"
                    elif "INFO" in line:
                        style = "green"
                    elif "DEBUG" in line:
                        style = "dim white"
                    rendered.append(Text(line.strip(), style=style))
                console.print(
                    Panel(
                        RichGroup(*rendered),
                        title="Logs",
                        border_style="white",
                    )
                )
            else:
                console.print(
                    Panel(
                        Text("No matching log entries", style="dim white"),
                        title="Logs",
                        border_style="white",
                    )
                )

            filter_info = f"Filtro: {current_level or 'Todos'}"
            if current_text:
                filter_info += f" | Texto: '{current_text}'"
            console.print(f"\n[dim]{filter_info}[/]")

            console.print()
            console.print(
                "[bold cyan]1[/] INFO   "
                "[bold cyan]2[/] WARNING   "
                "[bold cyan]3[/] ERROR   "
                "[bold cyan]4[/] Todos   "
                "[bold cyan]5[/] Buscar   "
                "[bold cyan]0[/] Volver"
            )
            try:
                sub = input(">> ").strip()
            except (KeyboardInterrupt, EOFError):
                return

            if sub == "0":
                return
            elif sub == "1":
                current_level = "INFO"
            elif sub == "2":
                current_level = "WARNING"
            elif sub == "3":
                current_level = "ERROR"
            elif sub == "4":
                current_level = None
                current_text = None
            elif sub == "5":
                try:
                    text = input("Buscar texto: ").strip()
                except (KeyboardInterrupt, EOFError):
                    continue
                if text:
                    current_text = text
            else:
                console.print("[bold red]Opción inválida.[/]")
                _wait_enter()

    except KeyboardInterrupt:
        return


# ── Control ────────────────────────────────────────────────────────────


def _show_control(console, logs_dir: str) -> None:
    """Screen 6: Bot control — pause, resume, trigger scanner."""
    from rich.panel import Panel
    from rich.text import Text

    try:
        while True:
            _clear_screen()
            _print_header(console)

            # Load status
            from royaltdn.frontend.console.commands import get_bot_status

            status = get_bot_status(logs_dir)
            if status:
                bot_state = status.get("bot_status", "unknown")
                uptime = status.get("uptime", "\u2014")
                status_text = (
                    f"Bot: [bold green]{bot_state}[/]\n"
                    f"Uptime: [cyan]{uptime}[/]\n"
                    f"Última actualización: "
                    f"[dim]{status.get('last_update', '\u2014')}[/]"
                )
            else:
                status_text = "[dim]No hay datos de estado disponibles.[/]"

            console.print(
                Panel(
                    Text.from_markup(status_text),
                    title="Estado del Bot",
                    border_style="white",
                )
            )

            console.print()
            console.print(
                "[bold cyan]1[/] Pausar bot   "
                "[bold cyan]2[/] Reanudar bot   "
                "[bold cyan]3[/] Forzar scanner   "
                "[bold cyan]0[/] Volver"
            )
            try:
                sub = input(">> ").strip()
            except (KeyboardInterrupt, EOFError):
                return

            if sub == "0":
                return
            elif sub == "1":
                from royaltdn.frontend.console.commands import pause_bot

                pause_bot(logs_dir)
                console.print("[bold green]✅ Bot pausado[/]")
                _wait_enter()
            elif sub == "2":
                from royaltdn.frontend.console.commands import resume_bot

                resume_bot(logs_dir)
                console.print("[bold green]✅ Bot reanudado[/]")
                _wait_enter()
            elif sub == "3":
                from royaltdn.frontend.console.commands import trigger_scanner

                trigger_scanner(logs_dir)
                console.print("[bold green]✅ Scanner disparado[/]")
                _wait_enter()
            else:
                console.print("[bold red]Opción inválida.[/]")
                _wait_enter()

    except KeyboardInterrupt:
        return
