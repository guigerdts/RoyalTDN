"""Rich interactive text menu for RoyalTDN — replaces Textual TUI on Termux.

All rendering uses ONLY 16-color ANSI names (no 24-bit hex colors).
All imports are lazy (function-level) to avoid import errors at module load.
"""

import time

_last_menu_visit: float = 0.0

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

    _log_activity("Menú iniciado", logs_dir)

    try:
        while True:
            _clear_screen()
            _print_header(console)
            badges = _check_notifications(state_loader)
            _print_menu(console, badges=badges)
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
                _show_estrategias(state_loader, console, logs_dir)
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

    _last_menu_visit = time.time()
    _log_activity("Menú finalizado", logs_dir)
    console.print("[bold yellow]Bot detenido.[/]")


# ── Core helpers ───────────────────────────────────────────────────────


def _clear_screen() -> None:
    """Clear terminal screen via ANSI escape codes."""
    print("\033[2J\033[H", end="")


def _print_header(console) -> None:
    """Render a Rich Panel header with bot title and PAUSADO status."""
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
    if _is_bot_paused():
        console.print(Text("PAUSADO", style="bold yellow"))


def _print_menu(console, badges: dict | None = None) -> None:
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

    # Apply badges
    if badges:
        if badges.get("signals", 0) > 0:
            n = badges["signals"]
            items[1] = ("2", f"Scanner — resultados de escaneo \U0001f514 ({n} nuevas)")
        if badges.get("trades", 0) > 0:
            n = badges["trades"]
            items[3] = ("4", f"Trades — historial y resumen \U0001f4b0 ({n} cerrados)")

    for key, desc in items:
        table.add_row(key, desc)

    console.print(table)

    if badges and badges.get("paused", False):
        console.print(Text("⚠ Bot paused — some actions may be limited", style="bold yellow"))


def _wait_enter() -> None:
    """Wait for Enter key press, handling Ctrl+C gracefully."""
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


# ── Cross-cutting helpers (Fase 11) ────────────────────────────────────


def _log_activity(mensaje: str, logs_dir: str = "logs") -> None:
    """Append a timestamped entry to ``logs/user_activity.log``.

    OSError is silently ignored — the menu must never crash from logging.
    """
    import os
    from datetime import datetime

    try:
        log_path = os.path.join(logs_dir, "user_activity.log")
        os.makedirs(logs_dir, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {mensaje}\n")
    except OSError:
        pass


def _is_bot_paused(logs_dir: str = "logs") -> bool:
    """Check whether the bot is currently paused by reading ``status.json``.

    Returns ``True`` if ``paused`` is true OR ``bot_status == "PAUSADO"``.
    FileNotFoundError / JSONDecodeError / OSError → ``False``.
    """
    import json
    import os

    path = os.path.join(logs_dir, "status.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("paused", False)) or data.get("bot_status") == "PAUSADO"
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def _check_notifications(state_loader) -> dict:
    """Detect new signals, new trades, and pending pause signal.

    Compares JSON timestamps against ``_last_menu_visit``.
    First visit (``_last_menu_visit == 0.0``) returns all zeros.
    """
    from datetime import datetime

    global _last_menu_visit

    signals_data = state_loader._load_file("signals.json", {})
    trades_data = state_loader._load_file("trades.json", {})

    new_signals = 0
    if _last_menu_visit > 0:
        last_signals = signals_data.get("last_signals", [])
        if isinstance(last_signals, list) and last_signals:
            ts = last_signals[0].get("timestamp", "")
            if ts:
                try:
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.timestamp() > _last_menu_visit:
                        new_signals = 1
                except (ValueError, TypeError):
                    pass

    new_trades = 0
    if _last_menu_visit > 0:
        trades_list = trades_data.get("trades", [])
        if isinstance(trades_list, list) and trades_list:
            ts = trades_list[-1].get("exit_at", "")
            if ts:
                try:
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.timestamp() > _last_menu_visit:
                        new_trades = 1
                except (ValueError, TypeError):
                    pass

    paused = False
    pause_data = state_loader._load_file("pause_signal.json", {})
    if pause_data and pause_data.get("action") == "pause":
        paused = True

    return {"signals": new_signals, "trades": new_trades, "paused": paused}


def _get_strategy_params_summary(config: dict) -> str:
    """Build a compact parameter summary string (≤50 chars) for a strategy config.

    For predefined strategies, params come from ``config["params"]``.
    For user strategies, params come from ``config["indicators"]`` list.
    Truncated at 50 characters with "…".
    """
    parts: list[str] = []
    if "indicators" in config:
        # User strategy
        for ind in config.get("indicators", []):
            name = ind.get("name", "?")
            p = ind.get("params", {})
            if p:
                inner = ", ".join(f"{k}={v}" for k, v in p.items())
                parts.append(f"{name}({inner})")
            else:
                parts.append(name)
    else:
        # Predefined strategy
        params = config.get("params", {})
        for k, v in params.items():
            parts.append(f"{k}={v}")
    result = ", ".join(parts)
    if len(result) > 50:
        result = result[:47] + "\u2026"
    return result


def _toggle_strategy(
    name: str, active: bool, is_user: bool, logs_dir: str = "logs",
) -> bool:
    """Toggle a strategy's ``active`` field.

    For predefined strategies: update ``logs/strategies.json`` in-place.
    For user strategies: load latest config from ``StrategyStore``, set
    ``active``, and save a new timestamped version (the watcher will
    pick it up).

    Returns ``True`` on success, ``False`` on error.
    """
    import json
    import os as _os

    if is_user:
        from royaltdn.strategy.strategy_store import StrategyStore as _SS

        store = _SS()
        cfg = store.load(name)
        if cfg is None:
            return False
        cfg["active"] = active
        try:
            store.save(cfg)
            return True
        except Exception:
            return False

    # Predefined: mutate logs/strategies.json
    path = _os.path.join(logs_dir, "strategies.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False

    updated = False
    for s in data.get("strategies", []):
        if s.get("name") == name:
            s["active"] = active
            updated = True
            break

    if not updated:
        return False

    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _os.replace(tmp, path)
        return True
    except OSError:
        return False


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

    bot_status = status.get("bot_status", "\u2014")
    is_paused = status.get("paused", False) or bot_status == "PAUSADO"
    status_style = "bold yellow" if is_paused else "bold white"
    status_label = "PAUSADO" if is_paused else bot_status

    rows = [
        ("Status", status_label, status_style),
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


# ── Estrategias ───────────────────────────────────────────────────────


def _show_estrategias(state_loader, console, logs_dir: str = "logs") -> None:
    """Screen 3: Unified strategies table with submenu for each strategy."""
    from rich.table import Table
    from rich.panel import Panel

    try:
        while True:
            _clear_screen()
            _print_header(console)

            # ── Load both sources ─────────────────────────────────────
            state_strategies = state_loader.load_strategies()
            try:
                from royaltdn.strategy.strategy_store import StrategyStore as _SS

                user_configs = _SS().load_all()
            except Exception:
                user_configs = []

            # ── Merge into unified sorted list ────────────────────────
            entries: list[dict] = []
            predefined = state_strategies.get("strategies", [])
            if isinstance(predefined, list):
                for s in predefined:
                    if isinstance(s, dict):
                        entries.append({
                            "name": str(s.get("name", "")),
                            "type": "Predefinida",
                            "active": bool(s.get("active", False)),
                            "config": s,
                            "is_user": False,
                        })
            if isinstance(user_configs, list):
                for cfg in user_configs:
                    if isinstance(cfg, dict):
                        entries.append({
                            "name": str(cfg.get("name", "")),
                            "type": "Usuario",
                            "active": bool(cfg.get("active", True)),
                            "config": cfg,
                            "is_user": True,
                        })
            entries.sort(key=lambda e: e["name"].lower())

            # ── Render unified table ──────────────────────────────────
            console.print(Panel("[bold]Estrategias[/]", border_style="white"))
            if entries:
                table = Table(
                    title=None,
                    border_style="white",
                    header_style="bold white",
                    show_edge=False,
                )
                table.add_column("#", style="bold cyan", width=3)
                table.add_column("Nombre", style="bold white")
                table.add_column("Tipo")
                table.add_column("Activa")
                table.add_column("Par\u00e1metros")
                for idx, e in enumerate(entries, start=1):
                    active_label = "S\u00ed" if e["active"] else "No"
                    params = _get_strategy_params_summary(e["config"])
                    table.add_row(str(idx), e["name"], e["type"], active_label, params)
                console.print(table)
            else:
                console.print("[dim]No hay estrategias cargadas.[/dim]")

            # ── Prompt ────────────────────────────────────────────────
            console.print()
            console.print(
                "[bold cyan]N[/] Seleccionar (n\u00famero)  "
                "[bold cyan]B[/] Crear nueva  "
                "[bold cyan]0[/] Volver"
            )
            try:
                sub = input(">> ").strip()
            except (KeyboardInterrupt, EOFError):
                return

            if sub == "0":
                return
            if sub.lower() == "b":
                _builder_flow(console, logs_dir=logs_dir)
                continue

            if sub.isdigit():
                idx = int(sub)
                if 1 <= idx <= len(entries):
                    _strategy_submenu(entries[idx - 1], console, logs_dir)
                    continue

            console.print("[bold red]Opci\u00f3n inv\u00e1lida.[/]")
            _wait_enter()

    except KeyboardInterrupt:
        return


def _strategy_submenu(entry: dict, console, logs_dir: str) -> None:
    """Submenu for a single strategy: toggle, edit (user), delete (user), backtest."""
    from rich.panel import Panel

    name = entry["name"]
    is_user = entry["is_user"]
    config = entry["config"]
    active = entry["active"]

    while True:
        _clear_screen()
        _print_header(console)

        console.print(Panel(f"[bold]{name}[/]", border_style="white"))
        console.print(f"  Tipo: {entry['type']}")
        console.print(f"  Activa: {'S\u00ed' if active else 'No'}")
        console.print(f"  Par\u00e1metros: {_get_strategy_params_summary(config)}")
        console.print()

        toggle_label = "Desactivar" if active else "Activar"
        parts = [f"[bold cyan]T[/] {toggle_label}"]
        if is_user:
            parts.append("[bold cyan]E[/] Editar")
            parts.append("[bold cyan]D[/] Eliminar")
        parts.append("[bold cyan]B[/] Backtest r\u00e1pido")
        parts.append("[bold cyan]0[/] Volver")
        console.print("  ".join(parts))

        try:
            sub = input(">> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return

        if sub == "0":
            return
        if sub == "t":
            new_active = not active
            ok = _toggle_strategy(name, new_active, is_user, logs_dir)
            if ok:
                action = "activ\u00f3" if new_active else "desactiv\u00f3"
                _log_activity(f"Usuario {action} '{name}'", logs_dir)
                console.print(
                    f"[green]Estrategia {'activada' if new_active else 'desactivada'}.[/]"
                )
            else:
                console.print("[red]Error al cambiar estado de la estrategia.[/]")
            _wait_enter()
            return  # back to parent to refresh the list
        if sub == "e" and is_user:
            _builder_flow(console, existing_config=config, logs_dir=logs_dir)
            _log_activity(f"Usuario edit\u00f3 '{name}'", logs_dir)
            _wait_enter()
            return
        if sub == "d" and is_user:
            confirm = _input_confirm(f"\u00bfEliminar '{name}'? (s/n): ")
            if confirm == "s":
                from royaltdn.strategy.strategy_store import StrategyStore as _SS

                try:
                    ok = _SS().delete(name)
                except Exception:
                    ok = False
                if ok:
                    _log_activity(f"Usuario elimin\u00f3 '{name}'", logs_dir)
                    console.print(f"[green]Estrategia '{name}' eliminada.[/]")
                else:
                    console.print(f"[red]Error al eliminar '{name}'.[/]")
                _wait_enter()
            return
        if sub == "b":
            _quick_backtest(config, console, logs_dir)
            _log_activity(
                f"Usuario ejecut\u00f3 backtest r\u00e1pido de '{name}'", logs_dir
            )
            _wait_enter()
            return

        console.print("[bold red]Opci\u00f3n inv\u00e1lida.[/]")
        _wait_enter()


def _input_confirm(prompt: str) -> str:
    """Read a single confirmation character, handling Ctrl+C cleanly."""
    try:
        return input(prompt).strip().lower()
    except (KeyboardInterrupt, EOFError):
        return "n"


def _quick_backtest(config: dict, console, logs_dir: str) -> None:
    """Run a quick backtest from the strategy submenu — no save option."""
    from rich.table import Table

    # Determine defaults from config
    default_symbol = ""
    if "symbol" in config:
        default_symbol = config["symbol"]
    elif "symbols" in config:
        syms = config["symbols"]
        if isinstance(syms, list) and syms:
            default_symbol = syms[0]
    if not default_symbol:
        default_symbol = "SPY"

    default_timeframe = config.get("timeframe", "1D")
    default_period = "2y"

    try:
        raw_sym = input(f"S\u00edmbolo (default: {default_symbol}): ").strip().upper()
        symbol = raw_sym if raw_sym else default_symbol
    except (KeyboardInterrupt, EOFError):
        return

    try:
        raw_per = input(f"Per\u00edodo (default: {default_period}): ").strip()
        period = raw_per if raw_per else default_period
    except (KeyboardInterrupt, EOFError):
        return

    from royaltdn.strategy.backtesting import run_backtest as _run_bt
    from royaltdn.strategy.schema import validate_config

    ok, err = validate_config(config)
    if not ok:
        console.print(f"[red]Configuraci\u00f3n inv\u00e1lida: {err}[/]")
        return

    console.print("[yellow]Ejecutando backtest...[/]")
    try:
        result = _run_bt(
            config, symbol=symbol, timeframe=default_timeframe, period=period,
        )
    except Exception as e:
        console.print(f"[red]Error en backtest: {e}[/]")
        return

    if "error" in result:
        console.print(f"[red]{result['error']}[/]")
        return

    metrics = result.get("metrics", {})
    table = Table(
        title="Resultados del Backtest R\u00e1pido",
        border_style="green",
        header_style="bold white",
    )
    table.add_column("M\u00e9trica", style="bold cyan")
    table.add_column("Valor", justify="right")
    table.add_row("Sharpe", f"{metrics.get('sharpe', 0):.2f}")
    table.add_row("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
    table.add_row("Win Rate", f"{metrics.get('win_rate', 0)*100:.1f}%")
    table.add_row("Max Drawdown", f"{metrics.get('max_drawdown', 0)*100:.2f}%")
    table.add_row("CAGR", f"{metrics.get('cagr', 0)*100:.2f}%")
    table.add_row("Total Return", f"{metrics.get('total_return', 0)*100:.2f}%")
    table.add_row("Num Trades", str(metrics.get('num_trades', 0)))
    console.print(table)


# ── Builder (12 stages) ──────────────────────────────────────────────


def _builder_flow(
    console,
    existing_config: dict | None = None,
    logs_dir: str = "logs",
) -> None:
    """Interactive strategy builder — 12 stages, Rich console, no Textual.

    When ``existing_config`` is provided the builder runs in **edit mode**:
    each stage pre-fills from the existing config and lets the user skip
    with Enter to keep the current value.

    Backward-compatible: when ``existing_config`` is ``None`` all stages
    behave as before (no defaults).
    """
    # ── Lazy imports (builder_state, schema, backtesting, store) ─────
    from royaltdn.frontend.console.builder_state import (
        INDICATOR_DEFS,
        OPERATOR_GROUPS,
        NEEDS_VALUE,
        _build_tree,
    )
    from royaltdn.strategy.schema import validate_config, VALID_TIMEFRAMES
    from royaltdn.strategy.backtesting import run_backtest
    from royaltdn.strategy.strategy_store import StrategyStore

    # ── Pre-fill from existing_config when editing ───────────────────
    is_edit = existing_config is not None
    if is_edit:
        strategy_name = existing_config.get("name", "")
        indicators_list = list(existing_config.get("indicators", []))
        entry_tree = existing_config.get(
            "entry_rules", {"operator": "AND", "conditions": []}
        )
        exit_tree = existing_config.get(
            "exit_rules", {"operator": "AND", "conditions": []}
        )
        pre_symbol = (
            existing_config.get("symbols", ["SPY"])[0]
            if existing_config.get("symbols")
            else "SPY"
        )
        pre_timeframe = existing_config.get("timeframe", "1D")
        pre_period = "2y"  # not persisted in config
        risk_mgmt = existing_config.get(
            "risk_management",
            {
                "stop_loss_pct": 2,
                "take_profit_pct": 5,
                "max_position_size": 1000,
                "max_daily_loss": 500,
            },
        )
    else:
        strategy_name = ""
        indicators_list = []
        entry_tree = {"operator": "AND", "conditions": []}
        exit_tree = {"operator": "AND", "conditions": []}
        pre_symbol = "SPY"
        pre_timeframe = "1D"
        pre_period = "2y"
        risk_mgmt = {
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_position_size": 1000,
            "max_daily_loss": 500,
        }

    import re as _re

    try:
        # ── Stage 1: Name ─────────────────────────────────────────────
        console.print("\n[bold]Stage 1/12 — Nombre de la estrategia[/]")
        while True:
            try:
                if is_edit and strategy_name:
                    prompt = (
                        f"Valor actual: {strategy_name}. Enter para mantener: "
                    )
                else:
                    prompt = "Nombre de la estrategia: "
                raw = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                return

            if is_edit and not raw:
                # Keep existing name
                break
            if not raw:
                console.print("[red]El nombre no puede estar vac\u00edo[/]")
                continue
            if not _re.match(r"^[a-zA-Z0-9 _]+$", raw):
                console.print(
                    "[red]Solo se permiten letras, n\u00fameros, espacios y guiones bajos.[/]"
                )
                continue
            strategy_name = raw
            break

        # ── Stages 2-4: Indicator loop ────────────────────────────────
        # Show existing indicators first (edit mode)
        if is_edit and indicators_list:
            console.print(
                f"\nIndicadores actuales ({len(indicators_list)}):"
            )
            for idx, ind in enumerate(indicators_list, start=1):
                params = ind.get("params", {})
                param_str = ", ".join(f"{k}={v}" for k, v in params.items())
                console.print(f"  {idx}. {ind['name']}  ({param_str})")

        # Add new indicators
        while True:
            console.print(
                f"\n[bold]Stage 2/12 — "
                f"{'Agregar' if is_edit else 'Seleccionar'} indicador "
                f"({len(indicators_list) + 1})[/]"
            )
            for idx, idef in enumerate(INDICATOR_DEFS, start=1):
                console.print(f"  [bold cyan]{idx}[/]  {idef['label']}")
            console.print("  [bold cyan]0[/]  Terminar selecci\u00f3n")

            try:
                pick = input(
                    "Seleccione indicador (n\u00famero) o 0 para terminar: "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                return

            if pick == "0":
                if not indicators_list:
                    console.print(
                        "[red]Debe agregar al menos un indicador.[/]"
                    )
                    continue
                break

            if not pick.isdigit() or int(pick) < 1 or int(pick) > len(INDICATOR_DEFS):
                console.print(
                    f"[red]Ingrese un n\u00famero entre 1 y {len(INDICATOR_DEFS)}.[/]"
                )
                continue

            selected = INDICATOR_DEFS[int(pick) - 1]
            indicator: dict = {"name": selected["name"], "params": {}}

            # Stage 3: Configure params
            console.print(
                f"\n[bold]Stage 3/12 — "
                f"Par\u00e1metros: {selected['label']}[/]"
            )
            for pdef in selected.get("params", []):
                key = pdef["key"]
                label = pdef["label"]
                default = pdef.get("default", "")
                ptype = pdef.get("type", "str")

                while True:
                    try:
                        pr = f"  {label} ({default}): "
                        val_raw = input(pr).strip()
                    except (KeyboardInterrupt, EOFError):
                        return

                    if not val_raw:
                        val_raw = str(default)

                    if ptype == "int":
                        if not val_raw.lstrip("-").isdigit():
                            console.print(
                                "[red]Debe ingresar un n\u00famero entero.[/]"
                            )
                            continue
                        val = int(val_raw)
                        pmin = pdef.get("min")
                        pmax = pdef.get("max")
                        if pmin is not None and val < pmin:
                            console.print(f"[red]M\u00ednimo: {pmin}[/]")
                            continue
                        if pmax is not None and val > pmax:
                            console.print(f"[red]M\u00e1ximo: {pmax}[/]")
                            continue
                        indicator["params"][key] = val
                        break
                    elif ptype == "float":
                        try:
                            val = float(val_raw)
                        except ValueError:
                            console.print(
                                "[red]Debe ingresar un n\u00famero decimal.[/]"
                            )
                            continue
                        pmin = pdef.get("min")
                        pmax = pdef.get("max")
                        if pmin is not None and val < pmin:
                            console.print(f"[red]M\u00ednimo: {pmin}[/]")
                            continue
                        if pmax is not None and val > pmax:
                            console.print(f"[red]M\u00e1ximo: {pmax}[/]")
                            continue
                        indicator["params"][key] = val
                        break
                    elif ptype == "select":
                        options = pdef.get("options", [])
                        console.print(
                            f"    Opciones: {', '.join(options)}"
                        )
                        if val_raw in options:
                            indicator["params"][key] = val_raw
                            break
                        else:
                            console.print(
                                f"[red]Seleccione una de: "
                                f"{', '.join(options)}[/]"
                            )
                            continue
                    else:
                        indicator["params"][key] = val_raw
                        break

            indicators_list.append(indicator)

            # Stage 4: Add more?
            console.print(
                f"\n[bold]Stage 4/12 — "
                f"Indicador '{selected['name']}' agregado.[/]"
            )
            while True:
                try:
                    more = input(
                        "\u00bfAgregar otro indicador? (s/n): "
                    ).strip().lower()
                except (KeyboardInterrupt, EOFError):
                    return
                if more in ("s", "n"):
                    break
                console.print("[red]Responda 's' o 'n'.[/]")
            if more == "n":
                break

        # ── Remove indicators (edit mode only) ────────────────────────
        if is_edit and len(indicators_list) > 1:
            while True:
                try:
                    rm = input(
                        "\u00bfEliminar alg\u00fan indicador? (s/n): "
                    ).strip().lower()
                except (KeyboardInterrupt, EOFError):
                    return
                if rm in ("s", "n"):
                    break
                console.print("[red]Responda 's' o 'n'.[/]")
            if rm == "s":
                while len(indicators_list) > 1:
                    console.print(
                        "\nIndicadores (seleccione n\u00famero a eliminar):"
                    )
                    for idx, ind in enumerate(indicators_list, start=1):
                        console.print(f"  [bold cyan]{idx}[/]  {ind['name']}")
                    console.print("  [bold cyan]0[/]  Terminar")
                    try:
                        rm_pick = input(">> ").strip()
                    except (KeyboardInterrupt, EOFError):
                        break
                    if rm_pick == "0":
                        break
                    if (
                        rm_pick.isdigit()
                        and 1 <= int(rm_pick) <= len(indicators_list)
                    ):
                        removed = indicators_list.pop(int(rm_pick) - 1)
                        console.print(
                            f"[green]Indicador '{removed['name']}' eliminado.[/]"
                        )
                    else:
                        console.print("[red]N\u00famero inv\u00e1lido.[/]")

        # ── Stage 5: Entry rule ───────────────────────────────────────
        if is_edit and entry_tree.get("conditions"):
            console.print(
                f"\n[bold]Stage 5/12 — "
                f"Regla de ENTRADA actual "
                f"({len(entry_tree['conditions'])} condicion(es))[/]"
            )
            try:
                mod = input(
                    "\u00bfModificar regla de entrada? (s/n): "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                return
            if mod == "s":
                entry_tree = _build_rule_conditions(
                    console, indicators_list, "ENTRADA"
                )
        else:
            console.print(f"\n[bold]Stage 5/12 — Regla de ENTRADA[/]")
            entry_tree = _build_rule_conditions(
                console, indicators_list, "ENTRADA"
            )
        if entry_tree is None:
            return  # Ctrl+C during entry rule

        # ── Stage 6: Exit rule ────────────────────────────────────────
        if is_edit and exit_tree.get("conditions"):
            console.print(
                f"\n[bold]Stage 6/12 — "
                f"Regla de SALIDA actual "
                f"({len(exit_tree['conditions'])} condicion(es))[/]"
            )
            try:
                mod = input(
                    "\u00bfModificar regla de salida? (s/n): "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                return
            if mod == "s":
                exit_tree = _build_rule_conditions(
                    console, indicators_list, "SALIDA"
                )
        else:
            console.print(f"\n[bold]Stage 6/12 — Regla de SALIDA[/]")
            exit_tree = _build_rule_conditions(
                console, indicators_list, "SALIDA"
            )
        if exit_tree is None:
            return  # Ctrl+C during exit rule

        # ── Stage 7: Symbol ───────────────────────────────────────────
        console.print(f"\n[bold]Stage 7/12 — S\u00edmbolo[/]")
        while True:
            try:
                if is_edit:
                    sym_prompt = (
                        f"Valor actual: {pre_symbol}. "
                        f"Enter para mantener: "
                    )
                else:
                    sym_prompt = (
                        "S\u00edmbolo para backtesting (default: SPY): "
                    )
                raw_sym = input(sym_prompt).strip().upper()
            except (KeyboardInterrupt, EOFError):
                return

            if is_edit and not raw_sym:
                symbol = pre_symbol
                break
            if not raw_sym:
                symbol = "SPY"
            elif _re.match(r"^[A-Z0-9]{1,10}$", raw_sym):
                symbol = raw_sym
            else:
                console.print(
                    "[red]S\u00edmbolo inv\u00e1lido. "
                    "Use 1-10 caracteres alfanum\u00e9ricos.[/]"
                )
                continue
            break

        # ── Stage 8: Timeframe ────────────────────────────────────────
        console.print(f"\n[bold]Stage 8/12 — Timeframe[/]")
        sorted_tfs = sorted(VALID_TIMEFRAMES)
        for idx, tf in enumerate(sorted_tfs, start=1):
            console.print(f"  [bold cyan]{idx}[/]  {tf}")
        while True:
            try:
                if is_edit:
                    tf_prompt = (
                        f"Valor actual: {pre_timeframe}. "
                        f"Enter para mantener: "
                    )
                else:
                    tf_prompt = "Timeframe (default: 1D): "
                tf_raw = input(tf_prompt).strip()
            except (KeyboardInterrupt, EOFError):
                return

            if is_edit and not tf_raw:
                timeframe = pre_timeframe
                break
            if not tf_raw:
                tf_raw = "1D"
            if tf_raw.isdigit():
                n = int(tf_raw)
                if 1 <= n <= len(sorted_tfs):
                    timeframe = sorted_tfs[n - 1]
                    break
            if tf_raw in VALID_TIMEFRAMES:
                timeframe = tf_raw
                break
            console.print(
                f"[red]Timeframe inv\u00e1lido. Use un n\u00famero "
                f"(1-{len(sorted_tfs)}) o un valor v\u00e1lido.[/]"
            )

        # ── Stage 9: Period ───────────────────────────────────────────
        console.print(f"\n[bold]Stage 9/12 — Per\u00edodo[/]")
        period_options = ["1m", "3m", "6m", "1y", "2y", "5y"]
        for idx, po in enumerate(period_options, start=1):
            console.print(f"  [bold cyan]{idx}[/]  {po}")
        while True:
            try:
                if is_edit:
                    per_prompt = (
                        f"Valor actual: {pre_period}. "
                        f"Enter para mantener: "
                    )
                else:
                    per_prompt = "Per\u00edodo (default: 2y): "
                period_raw = input(per_prompt).strip()
            except (KeyboardInterrupt, EOFError):
                return

            if is_edit and not period_raw:
                period = pre_period
                break
            if not period_raw:
                period = "2y"
                break
            if period_raw.isdigit():
                n = int(period_raw)
                if 1 <= n <= len(period_options):
                    period = period_options[n - 1]
                    break
            if period_raw in period_options:
                period = period_raw
                break
            console.print(
                f"[red]Per\u00edodo inv\u00e1lido. Use un n\u00famero "
                f"(1-{len(period_options)}) o un valor v\u00e1lido.[/]"
            )

        # ── Stage 10: Backtest ────────────────────────────────────────
        console.print(f"\n[bold]Stage 10/12 — Backtest[/]")
        config = {
            "version": 1,
            "name": strategy_name,
            "symbols": [symbol],
            "timeframe": timeframe,
            "indicators": indicators_list,
            "entry_rules": entry_tree,
            "exit_rules": exit_tree,
            "risk_management": risk_mgmt,
        }

        backtest_ok = False
        while not backtest_ok:
            ok, err = validate_config(config)
            if not ok:
                console.print(
                    f"[red]Configuraci\u00f3n inv\u00e1lida: {err}[/]"
                )
                console.print(
                    "[dim]Presiona Enter para volver "
                    "al men\u00fa de estrategias.[/]"
                )
                _wait_enter()
                return

            console.print("[yellow]Ejecutando backtest...[/]")
            try:
                result = run_backtest(
                    config,
                    symbol=symbol,
                    timeframe=timeframe,
                    period=period,
                )
            except Exception as e:
                console.print(f"[red]Error en backtest: {e}[/]")
                try:
                    retry = input(
                        "\u00bfReintentar? (s/n): "
                    ).strip().lower()
                except (KeyboardInterrupt, EOFError):
                    return
                if retry != "s":
                    return
                continue

            if "error" in result:
                err_msg = result["error"]
                console.print(f"[red]Backtest fall\u00f3: {err_msg}[/]")
                try:
                    retry = input(
                        "\u00bfReintentar? (s/n): "
                    ).strip().lower()
                except (KeyboardInterrupt, EOFError):
                    return
                if retry != "s":
                    return
                continue

            # Show results
            metrics = result.get("metrics", {})
            from rich.table import Table as RichTable

            bt_table = RichTable(
                title="Resultados del Backtest",
                border_style="green",
                header_style="bold white",
            )
            bt_table.add_column("M\u00e9trica", style="bold cyan")
            bt_table.add_column("Valor", justify="right")
            bt_table.add_row("Sharpe", f"{metrics.get('sharpe', 0):.2f}")
            bt_table.add_row(
                "Profit Factor", f"{metrics.get('profit_factor', 0):.2f}"
            )
            bt_table.add_row(
                "Win Rate", f"{metrics.get('win_rate', 0)*100:.1f}%"
            )
            bt_table.add_row(
                "Max Drawdown",
                f"{metrics.get('max_drawdown', 0)*100:.2f}%",
            )
            bt_table.add_row(
                "CAGR", f"{metrics.get('cagr', 0)*100:.2f}%"
            )
            bt_table.add_row(
                "Total Return",
                f"{metrics.get('total_return', 0)*100:.2f}%",
            )
            bt_table.add_row(
                "Num Trades", str(metrics.get('num_trades', 0))
            )
            console.print(bt_table)
            backtest_ok = True

        # ── Stage 11: Save ────────────────────────────────────────────
        console.print(f"\n[bold]Stage 11/12 — Guardar[/]")
        while True:
            try:
                save = input(
                    "\u00bfGuardar estrategia? (s/n): "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                return
            if save in ("s", "n"):
                break
            console.print("[red]Responda 's' o 'n'.[/]")

        if save == "s":
            try:
                path = StrategyStore().save(config)
            except Exception as e:
                console.print(f"[red]Error al guardar: {e}[/]")
            else:
                console.print(
                    f"[green]Estrategia guardada en: {path}[/]"
                )

        # ── Stage 12: Return ──────────────────────────────────────────
        console.print(f"\n[bold]Stage 12/12 — Listo[/]")
        console.print("[dim]Presiona Enter para continuar[/]")
        _wait_enter()

    except KeyboardInterrupt:
        return


def _build_rule_conditions(
    console,
    indicators_list: list[dict],
    rule_name: str,
) -> dict | None:
    """Build a rule conditions tree for entry or exit rules.
    
    Returns the condition tree dict, or None if user pressed Ctrl+C.
    """
    from royaltdn.frontend.console.builder_state import (
        OPERATOR_GROUPS,
        NEEDS_VALUE,
        _build_tree,
    )

    try:
        num_conds_raw = input(f"Número de condiciones para {rule_name}: ").strip()
    except (KeyboardInterrupt, EOFError):
        return None

    if not num_conds_raw.isdigit() or int(num_conds_raw) < 1:
        console.print("[red]Debe ingresar al menos 1 condición. Usando 1.[/]")
        num_conds = 1
    else:
        num_conds = int(num_conds_raw)

    conditions: list[dict] = []

    for i in range(1, num_conds + 1):
        console.print(f"\n[bold]Condición {i} de {num_conds}[/]")

        # Pick indicator from the already-selected list
        console.print("  Indicadores disponibles:")
        for idx, ind in enumerate(indicators_list, start=1):
            console.print(f"    [bold cyan]{idx}[/]  {ind['name']}")
        while True:
            try:
                ind_pick = input(f"  Indicador {i}: seleccione número: ").strip()
            except (KeyboardInterrupt, EOFError):
                return None
            if not ind_pick.isdigit() or int(ind_pick) < 1 or int(ind_pick) > len(indicators_list):
                console.print(f"[red]Ingrese un número entre 1 y {len(indicators_list)}.[/]")
                continue
            break

        selected_indicator = indicators_list[int(ind_pick) - 1]
        indicator_name = selected_indicator["name"]
        indicator_params = selected_indicator["params"]

        # Pick operator group
        console.print("  Grupos de operadores:")
        for gidx, grp in enumerate(OPERATOR_GROUPS, start=1):
            ops_list = ", ".join(o["label"] for o in grp["operators"])
            console.print(f"    [bold cyan]{gidx}[/]  {grp['group']}: {ops_list}")
        while True:
            try:
                g_pick = input("  Grupo de operador: ").strip()
            except (KeyboardInterrupt, EOFError):
                return None
            if not g_pick.isdigit() or int(g_pick) < 1 or int(g_pick) > len(OPERATOR_GROUPS):
                console.print(f"[red]Ingrese un número entre 1 y {len(OPERATOR_GROUPS)}.[/]")
                continue
            break

        selected_group = OPERATOR_GROUPS[int(g_pick) - 1]

        # Pick specific operator within group
        console.print(f"  Operadores en '{selected_group['group']}':")
        for oidx, op in enumerate(selected_group["operators"], start=1):
            console.print(f"    [bold cyan]{oidx}[/]  {op['label']}")
        while True:
            try:
                op_pick = input("  Operador: ").strip()
            except (KeyboardInterrupt, EOFError):
                return None
            if not op_pick.isdigit() or int(op_pick) < 1 or int(op_pick) > len(selected_group["operators"]):
                console.print(f"[red]Ingrese un número entre 1 y {len(selected_group['operators'])}.[/]")
                continue
            break

        selected_op = selected_group["operators"][int(op_pick) - 1]
        operator_key = selected_op["key"]

        cond: dict = {
            "indicator": indicator_name,
            "params": indicator_params,
            "operator": operator_key,
        }

        if operator_key in NEEDS_VALUE:
            while True:
                try:
                    val_raw = input("  Valor: ").strip()
                except (KeyboardInterrupt, EOFError):
                    return None
                try:
                    cond["value"] = float(val_raw)
                    break
                except ValueError:
                    console.print("[red]Debe ingresar un valor numérico.[/]")
                    continue

        conditions.append(cond)

    # Logic (AND/OR) if more than 1 condition
    logic = "AND"
    if num_conds > 1:
        while True:
            try:
                logic_raw = input("Lógica entre condiciones (AND/OR): ").strip().upper()
            except (KeyboardInterrupt, EOFError):
                return None
            if logic_raw in ("AND", "OR"):
                logic = logic_raw
                break
            console.print("[red]Ingrese AND o OR.[/]")

    return _build_tree(logic, conditions)


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
                paused = status.get("paused", False)
                bot_style = "bold yellow" if (paused or bot_state == "PAUSADO") else "bold green"
                bot_display = "PAUSADO" if (paused or bot_state == "PAUSADO") else bot_state
                uptime = status.get("uptime", "\u2014")
                status_text = (
                    f"Bot: [{bot_style}]{bot_display}[/]\n"
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
                _log_activity("Usuario pausó el bot", logs_dir)
                console.print("[bold green]✅ Bot pausado[/]")
                _wait_enter()
            elif sub == "2":
                from royaltdn.frontend.console.commands import resume_bot

                resume_bot(logs_dir)
                _log_activity("Usuario reanudó el bot", logs_dir)
                console.print("[bold green]✅ Bot reanudado[/]")
                _wait_enter()
            elif sub == "3":
                from royaltdn.frontend.console.commands import trigger_scanner

                trigger_scanner(logs_dir)
                _log_activity("Usuario forzó escaneo", logs_dir)
                console.print("[bold green]✅ Scanner disparado[/]")
                _wait_enter()
            else:
                console.print("[bold red]Opción inválida.[/]")
                _wait_enter()

    except KeyboardInterrupt:
        return
