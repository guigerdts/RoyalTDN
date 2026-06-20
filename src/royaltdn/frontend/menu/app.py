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
                _last_menu_visit = time.time()
                _show_dashboard(state_loader, log_buffer, console)
            elif cmd == "2":
                _last_menu_visit = time.time()
                _show_scanner(state_loader, console, logs_dir)
            elif cmd == "3":
                _last_menu_visit = time.time()
                _show_estrategias(state_loader, console, logs_dir)
            elif cmd == "4":
                _last_menu_visit = time.time()
                _show_trades(state_loader, console, logs_dir)
            elif cmd == "5":
                _last_menu_visit = time.time()
                _show_logs(log_buffer, console)
            elif cmd == "6":
                _last_menu_visit = time.time()
                _show_control(console, logs_dir)
            elif cmd == "7":
                _last_menu_visit = time.time()
                _show_simulation(state_loader, console, logs_dir)
            elif cmd == "8":
                _last_menu_visit = time.time()
                _show_activity(console, logs_dir)
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
        ("7", "Simulación — escenarios what-if"),
        ("8", "Actividad — registro de acciones"),
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
    """Screen 1: Dashboard with KPIs, positions, signals, summary, logs.

    Supports auto-refresh countdown: prompts for interval, then re-renders
    every N seconds with a 1-second countdown and optional early exit (0).
    """
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.console import Group
    import select
    import sys as _sys

    def _render() -> None:
        """Re-render full dashboard — clear, header, all sections."""
        _clear_screen()
        _print_header(console)

        state = state_loader.load_all()
        signals = state_loader._load_file("signals.json", {})
        state["signals"] = signals
        log_lines = log_buffer.get_lines()

        sections: list = []
        _build_kpis(state, sections, Panel, Table, Text)
        _build_positions(state, sections, Panel, Table, Text)
        _build_signals(state, sections, Panel, Table, Text)
        _build_summary(state, sections, Panel, Table, Text)
        _build_log_section(log_lines, sections, Panel, Text)
        console.print(Group(*sections))

    try:
        while True:
            _render()

            try:
                prompt = input(
                    "\u00bfAuto-refresh? (Enter=5s, n\u00famero=segundos, N=manual): "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                return

            if prompt == "":
                interval = 5
            elif prompt.upper() == "N":
                # Manual mode — return to main menu immediately
                return
            elif prompt.isdigit() and int(prompt) > 0:
                interval = int(prompt)
            else:
                interval = 5

            # ── Auto-refresh countdown loop ──────────────────────────
            try:
                for remaining in range(interval, 0, -1):
                    _render()
                    console.print(
                        f"Pr\u00f3xima actualizaci\u00f3n en "
                        f"{remaining}s... (0=volver)"
                    )

                    # Non-blocking check for "0" to cancel auto-refresh
                    if select.select([_sys.stdin], [], [], 0)[0]:
                        try:
                            check = _sys.stdin.readline().strip()
                        except (KeyboardInterrupt, EOFError):
                            return
                        if check == "0":
                            break  # back to manual → re-prompt

                    time.sleep(1)
            except KeyboardInterrupt:
                return

    except KeyboardInterrupt:
        return


# ── Control: Alert Config ────────────────────────────────────────────


def _show_alert_config(console, logs_dir: str = "logs") -> None:
    """Screen 6 submenu: Configure alert thresholds.

    Reads ``logs/alert_thresholds.json`` with defaults:
      - max_daily_drawdown_pct: 3.0
      - max_consecutive_losses: 5
      - daily_pnl_limit: 0 (0 = no limit)

    User selects a param by number, enters a new value, validates, and
    writes back to the JSON file.  Calls ``_log_activity()`` on change.
    """
    import json
    import os

    THRESHOLD_DEFS: list[tuple[str, str, float | int, float | int | None, float | int | None, type]] = [
        ("max_daily_drawdown_pct", "Drawdown máximo diario", 3.0, 0.5, 20.0, float),
        ("max_consecutive_losses", "Pérdidas consecutivas máximas", 5, 2, 10, int),
        ("daily_pnl_limit", "P&L diario mínimo", 0, 0, None, float),
    ]

    config_path = os.path.join(logs_dir, "alert_thresholds.json")

    def _load() -> dict:
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {key: dflt for key, _, dflt, _, _, _ in THRESHOLD_DEFS}

    def _display(key: str, val: float | int) -> str:
        if key == "max_daily_drawdown_pct":
            return f"{val:.1f}%"
        if key == "max_consecutive_losses":
            return str(val)
        if key == "daily_pnl_limit":
            return "sin límite" if val == 0 else f"${val:.2f}"
        return str(val)

    try:
        while True:
            _clear_screen()
            _print_header(console)

            thresholds = _load()

            console.print()
            console.print("[bold]Umbrales de alerta[/]")
            for idx, (key, name, dflt, *_) in enumerate(THRESHOLD_DEFS, start=1):
                val = thresholds.get(key, dflt)
                console.print(f"  [bold cyan]{idx}[/] {name}: {_display(key, val)}")
            console.print("  [bold cyan]0[/] Volver")

            try:
                cmd = input(">> ").strip()
            except (KeyboardInterrupt, EOFError):
                return

            if cmd == "0":
                return
            if not cmd.isdigit() or not (1 <= int(cmd) <= len(THRESHOLD_DEFS)):
                console.print("[bold red]Opción inválida.[/]")
                _wait_enter()
                continue

            idx = int(cmd) - 1
            key, name, default, vmin, vmax, vtype = THRESHOLD_DEFS[idx]
            current = thresholds.get(key, default)

            console.print(f"\n[bold]{name}[/]")
            console.print(f"  Valor actual: {_display(key, current)}")

            while True:
                try:
                    raw = input("  Nuevo valor: ").strip()
                except (KeyboardInterrupt, EOFError):
                    break

                if not raw:
                    continue

                try:
                    val = vtype(raw)
                except ValueError:
                    hint = "decimal" if vtype is float else "entero"
                    console.print(f"[red]Ingrese un número {hint}.[/]")
                    continue

                if vmin is not None and val < vmin:
                    console.print(
                        f"[red]El valor mínimo es {vmin}.[/]"
                    )
                    continue
                if vmax is not None and val > vmax:
                    console.print(
                        f"[red]El valor máximo es {vmax}.[/]"
                    )
                    continue

                thresholds[key] = val
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(thresholds, f, indent=2, ensure_ascii=False)
                    _log_activity(
                        f"Usuario cambió umbral de {key} a {val}", logs_dir
                    )
                    console.print("[green]Umbral actualizado.[/]")
                except OSError as e:
                    console.print(f"[red]Error al guardar: {e}[/]")
                break

            _wait_enter()

    except KeyboardInterrupt:
        return


# ── Simulation ───────────────────────────────────────────────────────


def _show_simulation(
    state_loader, console, logs_dir: str = "logs",
) -> None:
    """Screen 7: What-if simulation — modify a risk param and compare.

    Lists strategies that have at least 1 historical trade, prompts for
    a risk parameter and new value, runs ``_simulate_trades()``, and
    displays an original vs simulated comparison table.
    """
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    import os

    try:
        # ── Load trades ──────────────────────────────────────────
        trades_data = state_loader.load_trades()
        all_trades = trades_data.get("trades", [])
        if not isinstance(all_trades, list) or not all_trades:
            console.print("[dim]No hay trades históricos para simular.[/]")
            _wait_enter()
            return

        # ── Build strategy list from trades + state ──────────────
        strategy_names_in_trades: set[str] = set()
        for t in all_trades:
            name = t.get("strategy") or t.get("strategy_name") or ""
            if name:
                strategy_names_in_trades.add(str(name))

        if not strategy_names_in_trades:
            console.print(
                "[dim]No hay trades con estrategia asignada para simular.[/]"
            )
            _wait_enter()
            return

        # Sort for consistent display
        sorted_names = sorted(strategy_names_in_trades)

        _clear_screen()
        _print_header(console)
        console.print()
        console.print("[bold]Seleccionar estrategia para simular[/]")
        for idx, name in enumerate(sorted_names, start=1):
            console.print(f"  [bold cyan]{idx}[/] {name}")
        console.print("  [bold cyan]0[/] Volver")

        try:
            pick = input(">> ").strip()
        except (KeyboardInterrupt, EOFError):
            return

        if pick == "0" or not pick.isdigit():
            return

        sel_idx = int(pick) - 1
        if sel_idx < 0 or sel_idx >= len(sorted_names):
            console.print("[bold red]Selección inválida.[/]")
            _wait_enter()
            return

        strategy_name = sorted_names[sel_idx]
        # Filter trades for this strategy
        sim_trades = [
            t for t in all_trades
            if (t.get("strategy") or t.get("strategy_name") or "") == strategy_name
        ]

        if not sim_trades:
            console.print(
                "[dim]Esta estrategia no tiene trades para simular.[/]"
            )
            _wait_enter()
            return

        # ── Build a minimal config from state ────────────────────
        # Try to find the strategy config from state / store
        sim_config: dict = {"risk_management": {}}
        state_strategies = state_loader.load_strategies()
        for s in state_strategies.get("strategies", []):
            if isinstance(s, dict) and s.get("name") == strategy_name:
                sim_config = dict(s)
                break
        if sim_config == {"risk_management": {}}:
            # Try user strategies
            try:
                from royaltdn.strategy.strategy_store import StrategyStore as _SS
                usr = _SS().load(strategy_name)
                if usr is not None:
                    sim_config = usr
            except Exception:
                pass

        # ── Param selection ──────────────────────────────────────
        console.print()
        console.print("[bold]Modificar parámetro de riesgo[/]")
        console.print("  [bold cyan]1[/] Stop loss (multiplicador ATR)")
        console.print("  [bold cyan]2[/] Take profit (ratio)")
        console.print("  [bold cyan]3[/] Tamaño de posición (% del capital)")
        console.print("  [bold cyan]0[/] Volver")

        try:
            param_pick = input(">> ").strip()
        except (KeyboardInterrupt, EOFError):
            return

        param_map = {
            "1": ("stop_loss", "stop_loss_pct"),
            "2": ("take_profit", "take_profit_pct"),
            "3": ("position_size", "max_position_size"),
        }
        if param_pick not in param_map:
            return

        param_key, _ = param_map[param_pick]

        # ── Value prompt ─────────────────────────────────────────
        console.print()
        while True:
            try:
                raw = input("Nuevo valor: ").strip()
            except (KeyboardInterrupt, EOFError):
                return

            if not raw:
                continue

            try:
                new_val = float(raw)
            except ValueError:
                console.print("[red]Ingrese un número decimal.[/]")
                continue

            if param_key == "position_size":
                if new_val < 1 or new_val > 100:
                    console.print(
                        "[red]El tamaño de posición debe estar entre 1% y 100%.[/]"
                    )
                    continue
            elif new_val <= 0:
                console.print("[red]El valor debe ser positivo.[/]")
                continue
            break

        # ── Run simulation ───────────────────────────────────────
        result = _simulate_trades(sim_trades, sim_config, param_key, new_val)

        # Log activity
        _log_activity(
            f"Usuario ejecutó simulación de '{strategy_name}' "
            f"cambiando '{param_key}' a {new_val}",
            logs_dir,
        )

        # ── Comparison table ─────────────────────────────────────
        _clear_screen()
        _print_header(console)

        table = Table(
            title=f"Simulación: {strategy_name} — {param_key} = {new_val}",
            border_style="white",
            header_style="bold white",
        )
        table.add_column("Métrica", style="bold cyan")
        table.add_column("Original", justify="right")
        table.add_column("Simulado", justify="right")

        pnl_o = result["original_pnl"]
        pnl_s = result["simulated_pnl"]
        pnl_o_style = "green" if pnl_o >= 0 else "red"
        pnl_s_style = "green" if pnl_s >= 0 else "red"
        table.add_row(
            "P&L Total",
            f"[{pnl_o_style}]\u200b${pnl_o:+,.2f}[/]",
            f"[{pnl_s_style}]\u200b${pnl_s:+,.2f}[/]",
        )
        table.add_row(
            "Drawdown Máx",
            f"{result['original_dd']:.1f}%",
            f"{result['simulated_dd']:.1f}%",
        )
        table.add_row(
            "Win Rate",
            f"{result['original_wr']:.1f}%",
            f"{result['simulated_wr']:.1f}%",
        )

        console.print(Panel(table, border_style="white"))
        console.print("\n[dim]Presiona Enter para volver[/]")
        _wait_enter()

    except KeyboardInterrupt:
        return


def _simulate_trades(
    trades: list[dict],
    config: dict,
    param: str,
    new_value: float,
) -> dict:
    """Recalculate P&L for historical trades adjusting a single risk param.

    Clones the strategy config, applies the new param value, and
    computes original vs simulated metrics:

    - P&L Total
    - Max Drawdown (simplified peak-to-trough)
    - Win Rate

    Args:
        trades: List of trade dicts with ``pnl``, ``entry_price``,
                ``exit_price``, ``qty``.
        config: Strategy config dict (deep-copied internally).
        param: ``"stop_loss"`` | ``"take_profit"`` | ``"position_size"``.
        new_value: New value for the selected param.

    Returns:
        dict with ``original_pnl``, ``simulated_pnl``, ``original_dd``,
        ``simulated_dd``, ``original_wr``, ``simulated_wr``.
    """
    import copy

    # Clone config
    sim_config = copy.deepcopy(config)

    # Apply new risk param
    if param == "stop_loss":
        sim_config.setdefault("risk_management", {})["stop_loss_pct"] = new_value
    elif param == "take_profit":
        sim_config.setdefault("risk_management", {})["take_profit_pct"] = new_value
    elif param == "position_size":
        sim_config.setdefault("risk_management", {})["max_position_size"] = new_value

    # Calculate original metrics
    original_pnl = sum(t.get("pnl", 0) for t in trades)
    original_wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    original_wr = (original_wins / len(trades) * 100) if trades else 0

    # Simulate with new param
    simulated_pnls: list[float] = []
    for t in trades:
        entry = t.get("entry_price", 0)
        exit_price = t.get("exit_price", 0)
        qty = t.get("qty", 1)
        direction = 1  # long

        # Adjust based on param
        if param == "stop_loss":
            stop_distance = entry * (new_value / 100.0)  # new_value = stop_loss_pct
            new_exit = entry - stop_distance
            if direction == 1:  # long
                exit_price = min(exit_price, new_exit)
        elif param == "take_profit":
            tp_distance = entry * (new_value / 100.0)  # new_value = take_profit_pct
            new_exit = entry + tp_distance
            if direction == 1:  # long
                exit_price = min(exit_price, new_exit)
        elif param == "position_size":
            qty = int(10000 * new_value / 100 / entry) if entry > 0 else qty
            qty = max(1, qty)

        simulated_pnl = (exit_price - entry) * qty * direction
        simulated_pnls.append(simulated_pnl)

    simulated_total = sum(simulated_pnls)
    simulated_wins = sum(1 for p in simulated_pnls if p > 0)
    simulated_wr = (simulated_wins / len(simulated_pnls) * 100) if simulated_pnls else 0

    # Simple drawdown calc (peak-to-trough using cumulative)
    def calc_drawdown(pnl_list: list[float]) -> float:
        cum = 0.0
        peak = 0.0
        dd = 0.0
        for p in pnl_list:
            cum += p
            if cum > peak:
                peak = cum
            dd = min(dd, cum - peak)
        return dd / 10000.0 * 100 if peak > 0 else 0.0

    original_dd = calc_drawdown([t.get("pnl", 0) for t in trades])
    simulated_dd = calc_drawdown(simulated_pnls)

    return {
        "original_pnl": original_pnl,
        "simulated_pnl": simulated_total,
        "original_dd": original_dd,
        "simulated_dd": simulated_dd,
        "original_wr": original_wr,
        "simulated_wr": simulated_wr,
    }


# ── Activity Log Viewer ──────────────────────────────────────────────


def _show_activity(console, logs_dir: str = "logs") -> None:
    """Screen 8: Activity log viewer — last 20 lines from user_activity.log.

    Shows timestamped entries with:
      - timestamp in dim white
      - message in white
    Supports optional text search filter.

    If the file doesn't exist or is empty, shows a dim placeholder.
    """
    import os

    try:
        path = os.path.join(logs_dir, "user_activity.log")

        try:
            with open(path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
        except (FileNotFoundError, OSError):
            all_lines = []

        _clear_screen()
        _print_header(console)
        console.print()

        if not all_lines:
            console.print("[dim]No hay actividad registrada aún.[/]")
            console.print("\n[dim]Presiona Enter para volver[/]")
            _wait_enter()
            return

        # Optional text search
        console.print("[dim]Enter para ver todo, o texto para buscar: [/]", end="")
        try:
            search = input().strip()
        except (KeyboardInterrupt, EOFError):
            return

        # Filter lines
        if search:
            filtered = [l for l in all_lines if search.lower() in l.lower()]
        else:
            filtered = all_lines

        if not filtered:
            console.print("[dim]No hay entradas que coincidan con la búsqueda.[/]")
            console.print("\n[dim]Presiona Enter para volver[/]")
            _wait_enter()
            return

        # Show last 20 of filtered
        from rich.text import Text

        display = filtered[-20:]
        for line in display:
            line = line.strip()
            if not line:
                continue
            # Split timestamp from message
            if line.startswith("[") and "]" in line:
                ts_end = line.index("]") + 1
                ts = line[:ts_end]
                msg = line[ts_end:].strip()
                console.print(Text.assemble(
                    (ts, "dim white"),
                    (" ", ""),
                    (msg, "white"),
                ))
            else:
                console.print(line)

        if len(filtered) > 20:
            console.print(
                f"\n[dim]Mostrando últimas 20 de {len(filtered)} entradas[/]"
            )

        console.print("\n[dim]Presiona Enter para volver[/]")
        _wait_enter()

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

        # T-10: Post-scan metrics panel
        scan_history = data.get("scan_history", [])
        if scan_history:
            latest = scan_history[-1]
            total_sym = latest.get("total_symbols", 0)
            passed_sym = latest.get("passed_symbols", 0)
            sig_count = latest.get("signals_count", 0)
            elapsed = latest.get("elapsed_seconds", 0.0)
            pct = (passed_sym / total_sym * 100) if total_sym > 0 else 0.0
            metrics_panel = (
                f"[bold white]Total s\u00edmbolos[/]: {total_sym}\n"
                f"[bold white]Pasaron filtro[/]: {passed_sym}/{total_sym} ({pct:.0f}%)\n"
                f"[bold white]Se\u00f1ales[/]: {sig_count}\n"
                f"[bold white]Tiempo[/]: {elapsed:.1f}s"
            )
            console.print(Panel(
                metrics_panel,
                title="\U0001f4ca  Resultados del Escaneo",
                border_style="white",
            ))

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
    table.add_row("Sortino Ratio", f"{metrics.get('sortino_ratio', metrics.get('sortino', 0)):.2f}")
    table.add_row("Calmar Ratio", f"{metrics.get('calmar_ratio', 0):.2f}")
    table.add_row("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
    table.add_row("Win Rate", f"{metrics.get('win_rate', 0)*100:.1f}%")
    table.add_row("Max Drawdown", f"{metrics.get('max_drawdown', 0)*100:.2f}%")
    table.add_row("CAGR", f"{metrics.get('cagr', 0)*100:.2f}%")
    table.add_row("Total Return", f"{metrics.get('total_return', 0)*100:.2f}%")
    table.add_row("Expectancy", f"${metrics.get('expectancy', 0):+.2f}")
    table.add_row("Avg Trade Duration", f"{metrics.get('avg_trade_duration', 0):.1f} h")
    table.add_row("Num Trades", str(metrics.get('num_trades', 0)))
    console.print(table)

    # T-04: < 30 trades warning
    num_trades = metrics.get('num_trades', 0)
    if 0 < num_trades < 30:
        console.print(
            f"[bold yellow]\u26a0\ufe0f \u26a0\ufe0f  ADVERTENCIA: Solo {num_trades} trades generados. "
            f"M\u00ednimo recomendado: 30. Resultados no estad\u00edsticamente significativos.[/]"
        )

    # T-06: B&H comparison, trade table
    if not result.get("trades"):
        console.print("[bold yellow]\u26a0\ufe0f No se generaron trades en este per\u00edodo.[/]")
    else:
        from royaltdn.strategy.backtesting import _display_buy_hold_comparison, _display_backtest_trades
        _display_buy_hold_comparison(result.get("buy_hold_equity"), metrics, console)
        _display_backtest_trades(result.get("trades", []), console)


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
            bt_table.add_row("Sortino Ratio", f"{metrics.get('sortino_ratio', metrics.get('sortino', 0)):.2f}")
            bt_table.add_row("Calmar Ratio", f"{metrics.get('calmar_ratio', 0):.2f}")
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
            bt_table.add_row("Expectancy", f"${metrics.get('expectancy', 0):+.2f}")
            bt_table.add_row("Avg Trade Duration", f"{metrics.get('avg_trade_duration', 0):.1f} h")
            bt_table.add_row(
                "Num Trades", str(metrics.get('num_trades', 0))
            )
            console.print(bt_table)

            # T-04 / T-06: warning, B&H, trade table
            num_trades = metrics.get('num_trades', 0)
            if 0 < num_trades < 30:
                console.print(
                    f"[bold yellow]\u26a0\ufe0f \u26a0\ufe0f  ADVERTENCIA: Solo {num_trades} trades generados. "
                    f"M\u00ednimo recomendado: 30. Resultados no estad\u00edsticamente significativos.[/]"
                )
            if not result.get("trades"):
                console.print("[bold yellow]\u26a0\ufe0f No se generaron trades en este per\u00edodo.[/]")
            else:
                from royaltdn.strategy.backtesting import _display_buy_hold_comparison, _display_backtest_trades
                _display_buy_hold_comparison(result.get("buy_hold_equity"), metrics, console)
                _display_backtest_trades(result.get("trades", []), console)

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
                _log_activity(
                    f"Estrategia '{strategy_name}' guardada", logs_dir
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


def _show_trades(state_loader, console, logs_dir: str = "logs") -> None:
    """Screen 4: Trade summary — enriched table, cumulative AND filters, single-key submenu."""
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from datetime import datetime, timedelta

    try:
        active_filters: dict = {}

        while True:
            _clear_screen()
            _print_header(console)

            data = state_loader.load_trades()
            all_trades = data.get("trades", [])
            if not isinstance(all_trades, list):
                all_trades = []

            # ── Summary (always shows unfiltered totals) ─────────────
            total = data.get("total_trades", len(all_trades))
            win_rate = data.get("win_rate", 0)
            profit_factor = data.get("profit_factor", 0)
            total_pnl = data.get("total_pnl", 0)

            # T-11: New summary metrics on unfiltered data
            pnl_list = [float(t.get("pnl", t.get("profit_loss", 0))) for t in all_trades if isinstance(t, dict)]
            num_total_trades = len(pnl_list)

            # Sharpe
            if num_total_trades >= 2:
                mean_pnl = sum(pnl_list) / len(pnl_list)
                variance = sum((x - mean_pnl) ** 2 for x in pnl_list) / (len(pnl_list) - 1)
                std_pnl = variance ** 0.5
                sharpe_val = (mean_pnl / std_pnl * (252 ** 0.5)) if std_pnl > 0 else 0.0
                sharpe_str = f"{sharpe_val:.2f}"
            else:
                sharpe_str = "N/A"
                mean_pnl = 0.0

            # Avg Trade
            avg_trade_val = mean_pnl = (sum(pnl_list) / len(pnl_list)) if pnl_list else 0.0
            avg_trade_style = "bold green" if avg_trade_val >= 0 else "bold red"

            # Max Drawdown (peak-to-trough of cumulative P&L)
            cum = 0.0
            peak = 0.0
            max_dd_val = 0.0
            for p in pnl_list:
                cum += p
                if cum > peak:
                    peak = cum
                dd = (cum - peak) / peak if peak > 0 else 0.0
                max_dd_val = min(max_dd_val, dd)
            max_dd_pct = max_dd_val * 100

            # Expectancy
            if num_total_trades > 0:
                wins_list = [p for p in pnl_list if p > 0]
                losses_list = [p for p in pnl_list if p < 0]
                wr = len(wins_list) / num_total_trades
                avg_win = sum(wins_list) / len(wins_list) if wins_list else 0.0
                avg_loss = sum(losses_list) / len(losses_list) if losses_list else 0.0
                expectancy = (wr * avg_win) - ((1 - wr) * abs(avg_loss))
                expectancy_str = f"${expectancy:+.2f}"
            else:
                expectancy_str = "$0.00"

            # T-14: WR > 60% in green
            wr_style = "green" if float(win_rate) > 60 else "white"
            pnl_style = "bold green" if float(total_pnl) >= 0 else "bold red"

            summary = Table.grid(padding=(0, 3))
            summary.add_column(justify="center", ratio=1)
            summary.add_row(
                Text.assemble(("Total\n", "bold white"), (str(total), "bold white")),
                Text.assemble(
                    ("Win Rate\n", "bold white"),
                    (f"{float(win_rate):.1f}%", wr_style),
                ),
                Text.assemble(
                    ("Profit Factor\n", "bold white"),
                    (f"{float(profit_factor):.2f}", "bold cyan"),
                ),
                Text.assemble(
                    ("Total P&L\n", "bold white"),
                    (f"${float(total_pnl):+,.2f}", pnl_style),
                ),
                Text.assemble(
                    ("Sharpe\n", "bold white"),
                    (sharpe_str, "bold cyan"),
                ),
                Text.assemble(
                    ("Avg Trade\n", "bold white"),
                    (f"${avg_trade_val:+,.2f}", avg_trade_style),
                ),
                Text.assemble(
                    ("Max DD\n", "bold white"),
                    (f"{max_dd_pct:.2f}%", "bold yellow"),
                ),
                Text.assemble(
                    ("Expectancy\n", "bold white"),
                    (expectancy_str, "bold cyan"),
                ),
            )
            console.print(Panel(summary, title="Trade Summary", border_style="white"))

            # T-13: Apply cumulative AND filters
            filtered = list(all_trades)

            if "symbol" in active_filters:
                sym_val = active_filters["symbol"]
                filtered = [t for t in filtered if str(t.get("symbol", "")).upper() == sym_val.upper()]

            if "strategy" in active_filters:
                strat_val = active_filters["strategy"]
                filtered = [
                    t for t in filtered
                    if (t.get("strategy") or t.get("strategy_name") or "") == strat_val
                ]

            if "date_range" in active_filters:
                dr = active_filters["date_range"]
                if dr == "today":
                    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    filtered = _filter_trades_by_date(filtered, today.isoformat(), datetime.now().isoformat())
                elif dr == "week":
                    start = (datetime.now() - timedelta(days=7)).isoformat()
                    filtered = _filter_trades_by_date(filtered, start, datetime.now().isoformat())
                elif dr == "month":
                    start = (datetime.now() - timedelta(days=30)).isoformat()
                    filtered = _filter_trades_by_date(filtered, start, datetime.now().isoformat())
                elif dr == "custom":
                    try:
                        s = input("Fecha inicio (YYYY-MM-DD): ").strip()
                        e = input("Fecha fin (YYYY-MM-DD): ").strip()
                    except (KeyboardInterrupt, EOFError):
                        s = e = ""
                    if s and e:
                        filtered = _filter_trades_by_date(filtered, s, e)

            # T-14: Active filters header in italic blue
            if active_filters:
                parts = []
                if "symbol" in active_filters:
                    parts.append(f"S\u00edmbolo={active_filters['symbol']}")
                if "strategy" in active_filters:
                    parts.append(f"Estrategia={active_filters['strategy']}")
                if "date_range" in active_filters:
                    parts.append(f"Fecha={active_filters['date_range']}")
                console.print(f"[italic blue]Filtros activos: {', '.join(parts)}[/]")

            # ── Filtered summary + trade table ──────────────────────
            if filtered:
                f_total = len(filtered)
                f_pnls = [float(t.get("pnl", t.get("profit_loss", 0))) for t in filtered if isinstance(t, dict)]
                wins = sum(1 for p in f_pnls if p > 0)
                f_win_rate = (wins / f_total * 100) if f_total else 0.0
                f_total_pnl = sum(f_pnls)
                winning_pnl = sum(p for p in f_pnls if p > 0)
                losing_pnl = sum(p for p in f_pnls if p < 0)
                f_profit_factor = (winning_pnl / abs(losing_pnl)) if losing_pnl else float("inf")
                f_wr_style = "green" if f_win_rate > 60 else "white"

                pnl_s = "bold green" if f_total_pnl >= 0 else "bold red"
                f_summary = Table.grid(padding=(0, 3))
                f_summary.add_column(justify="center", ratio=1)
                f_summary.add_row(
                    Text.assemble(("Filtrados\n", "bold white"), (str(f_total), "bold white")),
                    Text.assemble(
                        ("Win Rate\n", "bold white"),
                        (f"{f_win_rate:.1f}%", f_wr_style),
                    ),
                    Text.assemble(
                        ("Profit Factor\n", "bold white"),
                        (f"{f_profit_factor:.2f}" if f_profit_factor != float("inf") else "\u221e", "bold cyan"),
                    ),
                    Text.assemble(
                        ("Total P&L\n", "bold white"),
                        (f"${f_total_pnl:+,.2f}", pnl_s),
                    ),
                )
                console.print(Panel(f_summary, title="Filtro", border_style="white"))

                # T-12: Enriched trade table — 12 columns
                table = Table(
                    title=None, border_style="white", header_style="bold white"
                )
                table.add_column("#", style="bold cyan")
                table.add_column("Fecha")
                table.add_column("S\u00edmbolo", style="bold white")
                table.add_column("Lado")
                table.add_column("Qty", justify="right")
                table.add_column("Entry", justify="right")
                table.add_column("Exit", justify="right")
                table.add_column("P&L", justify="right")
                table.add_column("Retorno%", justify="right")
                table.add_column("Duraci\u00f3n", justify="right")
                table.add_column("Slippage", justify="right")
                table.add_column("Estrategia")

                for idx, t in enumerate(filtered, start=1):
                    if not isinstance(t, dict):
                        continue
                    # Fecha: entry_at formatted YYYY-MM-DD HH:MM
                    entry_at = t.get("entry_at", "") or t.get("entry_time", "") or ""
                    fecha = "\u2014"
                    if entry_at:
                        try:
                            dt = datetime.fromisoformat(str(entry_at).replace("Z", "+00:00"))
                            fecha = dt.strftime("%Y-%m-%d %H:%M")
                        except (ValueError, TypeError):
                            fecha = str(entry_at)[:16]

                    symbol = str(t.get("symbol", "\u2014"))
                    side = str(t.get("side", "\u2014"))
                    qty_raw = t.get("qty", t.get("quantity", "\u2014"))
                    qty = (
                        f"{qty_raw:.4f}"
                        if isinstance(qty_raw, (int, float))
                        else str(qty_raw)
                    )
                    entry_raw = t.get("entry_price", t.get("price", 0))
                    entry = f"${float(entry_raw):,.2f}" if entry_raw else "\u2014"
                    exit_raw = t.get("exit_price", "")
                    exit_val = f"${float(exit_raw):,.2f}" if exit_raw else "\u2014"
                    pnl_raw = t.get("pnl", t.get("profit_loss", 0))
                    pnl = (
                        f"${float(pnl_raw):+,.2f}"
                        if isinstance(pnl_raw, (int, float))
                        else "\u2014"
                    )
                    # T-14: P&L >= 0 bold green, < 0 bold red, == 0 default
                    pnl_style = "bold green" if (isinstance(pnl_raw, (int, float)) and pnl_raw > 0) else ("bold red" if (isinstance(pnl_raw, (int, float)) and pnl_raw < 0) else "white")

                    # Retorno%
                    ret_pct = t.get("return_pct", "")
                    ret_str = f"{float(ret_pct):.2f}%" if ret_pct else "\u2014"

                    # Duración: (exit_at - entry_at)
                    dur_str = "\u2014"
                    exit_at = t.get("exit_at", "") or t.get("exit_time", "")
                    if entry_at and exit_at:
                        try:
                            ed = datetime.fromisoformat(str(entry_at).replace("Z", "+00:00"))
                            xd = datetime.fromisoformat(str(exit_at).replace("Z", "+00:00"))
                            delta = xd - ed
                            if delta.total_seconds() < 3600:
                                dur_str = "< 1h"
                            elif delta.days > 0:
                                hours = delta.seconds // 3600
                                dur_str = f"{delta.days}d {hours}h"
                            else:
                                dur_str = f"{delta.seconds // 3600}h"
                        except (ValueError, TypeError):
                            pass

                    # Slippage
                    slippage_bps = t.get("slippage_bps", 0)
                    slippage_str = f"{slippage_bps} bps"

                    # Estrategia
                    estrategia = str(t.get("strategy") or t.get("strategy_name") or "\u2014")

                    table.add_row(
                        str(idx), fecha, symbol, side, qty, entry, exit_val,
                        f"[{pnl_style}]{pnl}[/]",
                        ret_str, dur_str, slippage_str, estrategia,
                    )
                console.print(table)
            else:
                # T-12, T-14: Empty state in dim italic gray
                console.print("[dim italic]No hay trades para mostrar con los filtros actuales.[/]")

            # T-13: Single-key submenu
            console.print()
            console.print(
                "[bold cyan]S[/] S\u00edmbolo   "
                "[bold cyan]E[/] Estrategia   "
                "[bold cyan]F[/] Fecha   "
                "[bold cyan]T[/] Reset   "
                "[bold cyan]X[/] Exportar   "
                "[bold cyan]V[/] Stats   "
                "[bold cyan]P[/] Estrategia   "
                "[bold cyan]0[/] Volver"
            )
            try:
                sub = input(">> ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return

            if sub == "0":
                return
            elif sub == "s":
                # T-13: Prompt for symbol
                try:
                    val = input("Ingrese s\u00edmbolo (ENTER para cancelar): ").strip().upper()
                except (KeyboardInterrupt, EOFError):
                    continue
                if val:
                    active_filters["symbol"] = val
                elif "symbol" in active_filters:
                    del active_filters["symbol"]
                continue
            elif sub == "e":
                # T-13: Prompt for strategy
                try:
                    val = input("Ingrese estrategia (ENTER para cancelar): ").strip()
                except (KeyboardInterrupt, EOFError):
                    continue
                if val:
                    active_filters["strategy"] = val
                elif "strategy" in active_filters:
                    del active_filters["strategy"]
                continue
            elif sub == "f":
                # T-13: Date submenu
                console.print()
                console.print(
                    "[bold cyan]1[/] Hoy   "
                    "[bold cyan]2[/] Semana   "
                    "[bold cyan]3[/] Mes   "
                    "[bold cyan]4[/] Todo   "
                    "[bold cyan]5[/] Personalizado"
                )
                try:
                    dc = input("Filtrar por per\u00edodo: ").strip()
                except (KeyboardInterrupt, EOFError):
                    continue
                dr_map = {"1": "today", "2": "week", "3": "month", "4": None, "5": "custom"}
                val = dr_map.get(dc)
                if val:
                    active_filters["date_range"] = val
                elif "date_range" in active_filters:
                    del active_filters["date_range"]
                continue
            elif sub == "t":
                # T-13: Reset all filters
                active_filters = {}
                continue
            elif sub == "x":
                _export_trades(filtered, console, logs_dir)
                _wait_enter()
                continue
            elif sub == "v":
                _show_advanced_stats(filtered, console)
                _wait_enter()
                continue
            elif sub == "p":
                _show_performance_by_strategy(filtered, console)
                _wait_enter()
                continue
            # Anything else → loop (re-prompt with fresh data)

    except KeyboardInterrupt:
        return


def _filter_trades_by_date(
    trades: list[dict], start_date: str, end_date: str
) -> list[dict]:
    """Filter trades by comparing ``entry_at`` or ``exit_at`` ISO timestamps.

    Returns trades whose entry or exit falls within [start_date, end_date]
    (inclusive). If the end_date is a date-only string (no time component),
    it is extended to the end of that day (23:59:59). Trades without
    timestamp data are excluded.
    """
    from datetime import datetime

    def _parse(ts: str) -> datetime | None:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    start = _parse(start_date)
    end = _parse(end_date)
    if start is None or end is None:
        return trades  # no filter on parse failure

    # If end_date is date-only (no time component), extend to end of day
    if "T" not in end_date and " " not in end_date:
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

    result: list[dict] = []
    for t in trades:
        entry_ts = t.get("entry_at") or t.get("entry_time") or t.get("timestamp", "")
        exit_ts = t.get("exit_at") or t.get("exit_time", "")
        ts = entry_ts or exit_ts
        if not ts:
            continue
        parsed = _parse(str(ts))
        if parsed and start <= parsed <= end:
            result.append(t)
    return result


def _show_performance_by_strategy(trades: list[dict], console) -> None:
    """Group trades by ``strategy`` field and display performance metrics.

    Shows a Rich table with columns: Estrategia, Trades, Win Rate, P&L, Profit Factor.
    Sorted by P&L descending. Trades without ``strategy`` field are grouped
    as "Sin estrategia".
    """
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    groups: dict[str, list[dict]] = {}
    for t in trades:
        strategy = t.get("strategy") or t.get("strategy_name") or "Sin estrategia"
        strategy = str(strategy)
        groups.setdefault(strategy, []).append(t)

    if not groups:
        console.print("[dim]No hay trades para agrupar por estrategia.[/]")
        return

    rows: list[dict] = []
    for strategy, group in groups.items():
        n = len(group)
        wins = sum(1 for t in group if float(t.get("pnl", t.get("profit_loss", 0))) > 0)
        losses = n - wins
        win_rate = (wins / n * 100) if n else 0.0
        total_pnl = sum(float(t.get("pnl", t.get("profit_loss", 0))) for t in group)
        winning_pnl = sum(
            float(t.get("pnl", t.get("profit_loss", 0)))
            for t in group if float(t.get("pnl", t.get("profit_loss", 0))) > 0
        )
        losing_pnl = sum(
            float(t.get("pnl", t.get("profit_loss", 0)))
            for t in group if float(t.get("pnl", t.get("profit_loss", 0))) < 0
        )
        profit_factor = (winning_pnl / abs(losing_pnl)) if losing_pnl else float("inf")

        rows.append({
            "strategy": strategy,
            "trades": n,
            "win_rate": win_rate,
            "pnl": total_pnl,
            "profit_factor": profit_factor,
        })

    rows.sort(key=lambda r: r["pnl"], reverse=True)

    table = Table(
        title=None,
        border_style="white",
        header_style="bold white",
    )
    table.add_column("Estrategia", style="bold white")
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("Profit Factor", justify="right")

    for r in rows:
        pnl_style = "green" if r["pnl"] >= 0 else "red"
        pf_str = (
            f"{r['profit_factor']:.2f}"
            if r["profit_factor"] != float("inf")
            else "\u221e"
        )
        table.add_row(
            r["strategy"],
            str(r["trades"]),
            f"{r['win_rate']:.1f}%",
            f"[{pnl_style}]${r['pnl']:+,.2f}[/]",
            pf_str,
        )

    console.print(Panel(table, title="Rendimiento por Estrategia", border_style="white"))


def _export_trades(
    trades: list[dict], console, logs_dir: str = "logs"
) -> None:
    """Export filtered trades to CSV or JSON in an ``exports/`` directory.

    Prompts for format (1 CSV, 2 JSON) and filename. Creates ``exports/``
    if missing. Calls ``_log_activity()`` on success.
    """
    import csv
    import json
    import os

    try:
        fmt = input("Formato: 1 CSV, 2 JSON: ").strip()
    except (KeyboardInterrupt, EOFError):
        return

    from datetime import datetime

    date_str = datetime.now().strftime("%Y%m%d")

    try:
        name = input(
            f"Nombre del archivo (default: trades_export_{date_str}): "
        ).strip()
        if not name:
            name = f"trades_export_{date_str}"
    except (KeyboardInterrupt, EOFError):
        return

    exports_dir = os.path.join(logs_dir, "..", "exports") if logs_dir else "exports"
    exports_dir = os.path.abspath(exports_dir)
    os.makedirs(exports_dir, exist_ok=True)

    try:
        if fmt == "1":
            # CSV
            filename = f"{name}.csv"
            path = os.path.join(exports_dir, filename)
            fieldnames = [
                "symbol", "side", "qty", "entry_price", "exit_price",
                "pnl", "entry_at", "exit_at", "strategy",
            ]
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(trades)
            _log_activity(f"Usuario export\u00f3 trades a CSV ({filename})", logs_dir)
            console.print(f"[green]Exportado a exports/{filename}[/]")
        elif fmt == "2":
            # JSON
            filename = f"{name}.json"
            path = os.path.join(exports_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(trades, f, indent=2, ensure_ascii=False)
            _log_activity(f"Usuario export\u00f3 trades a JSON ({filename})", logs_dir)
            console.print(f"[green]Exportado a exports/{filename}[/]")
        else:
            console.print("[red]Formato inv\u00e1lido. Use 1 para CSV o 2 para JSON.[/]")
    except OSError as e:
        console.print(f"[red]Error al exportar: {e}[/]")


def _show_advanced_stats(trades: list[dict], console) -> None:
    """Compute and display advanced trade statistics.

    Includes: longest win/loss streaks, average duration (hours), best/worst
    weekday by P&L, average P&L per trade, and monthly profit ratio (last 3
    months if data available).
    """
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from datetime import datetime, timedelta

    if not trades:
        console.print("[dim]No hay trades para calcular estad\u00edsticas.[/]")
        return

    # ── Consecutive streaks ───────────────────────────────────────────
    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0

    for t in trades:
        pnl = float(t.get("pnl", t.get("profit_loss", 0)))
        if pnl > 0:
            current_win_streak += 1
            current_loss_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
        elif pnl < 0:
            current_loss_streak += 1
            current_win_streak = 0
            max_loss_streak = max(max_loss_streak, current_loss_streak)
        else:
            current_win_streak = 0
            current_loss_streak = 0

    # ── Average duration ──────────────────────────────────────────────
    durations: list[float] = []
    for t in trades:
        entry_ts = t.get("entry_at") or t.get("entry_time") or t.get("timestamp", "")
        exit_ts = t.get("exit_at") or t.get("exit_time", "")
        if entry_ts and exit_ts:
            try:
                entry_dt = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
                exit_dt = datetime.fromisoformat(str(exit_ts).replace("Z", "+00:00"))
                if exit_dt > entry_dt:
                    durations.append((exit_dt - entry_dt).total_seconds() / 3600)
            except (ValueError, TypeError):
                pass

    avg_duration = (
        sum(durations) / len(durations) if durations else 0.0
    )

    # ── Best/worst weekday ────────────────────────────────────────────
    weekday_pnl: dict[int, float] = {}
    for t in trades:
        ts_str = t.get("exit_at") or t.get("exit_time") or t.get("entry_at") or t.get("entry_time") or t.get("timestamp", "")
        if ts_str:
            try:
                dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                pnl = float(t.get("pnl", t.get("profit_loss", 0)))
                weekday_pnl[dt.weekday()] = weekday_pnl.get(dt.weekday(), 0.0) + pnl
            except (ValueError, TypeError):
                pass

    weekday_names = ["Lunes", "Martes", "Mi\u00e9rcoles", "Jueves", "Viernes", "S\u00e1bado", "Domingo"]
    best_day = ""
    worst_day = ""
    if weekday_pnl:
        best_wd = max(weekday_pnl, key=weekday_pnl.get)
        worst_wd = min(weekday_pnl, key=weekday_pnl.get)
        best_day = f"{weekday_names[best_wd]} (${weekday_pnl[best_wd]:+,.2f})"
        worst_day = f"{weekday_names[worst_wd]} (${weekday_pnl[worst_wd]:+,.2f})"

    # ── Average P&L per trade ─────────────────────────────────────────
    total_pnl = sum(float(t.get("pnl", t.get("profit_loss", 0))) for t in trades)
    avg_pnl = total_pnl / len(trades) if trades else 0.0

    # ── Monthly profit ratio (last 3 months) ──────────────────────────
    now = datetime.now()
    monthly_pnl: dict[str, float] = {}
    for t in trades:
        ts_str = t.get("exit_at") or t.get("exit_time") or t.get("entry_at") or t.get("entry_time") or t.get("timestamp", "")
        if ts_str:
            try:
                dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                month_key = dt.strftime("%Y-%m")
                if dt >= (now - timedelta(days=90)):
                    pnl = float(t.get("pnl", t.get("profit_loss", 0)))
                    monthly_pnl[month_key] = monthly_pnl.get(month_key, 0.0) + pnl
            except (ValueError, TypeError):
                pass

    monthly_lines = ""
    if monthly_pnl:
        parts = []
        for month in sorted(monthly_pnl.keys(), reverse=True):
            m_pnl = monthly_pnl[month]
            m_style = "green" if m_pnl >= 0 else "red"
            parts.append(f"{month}: [{m_style}]${m_pnl:+,.2f}[/]")
        monthly_lines = " | ".join(parts)

    # ── Render ────────────────────────────────────────────────────────
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="left")

    rows_data = [
        ("Racha m\u00e1s larga de ganancias", f"{max_win_streak} trades"),
        ("Racha m\u00e1s larga de p\u00e9rdidas", f"{max_loss_streak} trades"),
        ("Duraci\u00f3n media", f"{avg_duration:.1f} h"),
        ("Mejor d\u00eda de la semana", best_day or "\u2014"),
        ("Peor d\u00eda de la semana", worst_day or "\u2014"),
        ("P&L medio por trade", f"${avg_pnl:+,.2f}"),
    ]
    for label, value in rows_data:
        table.add_row(label, value)

    console.print(Panel(table, title="Estad\u00edsticas Avanzadas", border_style="white"))

    if monthly_lines:
        console.print(
            Panel(
                Text.from_markup(
                    f"Profit ratio mensual (\u00faltimos 3 meses):\n{monthly_lines}"
                ),
                title="Rendimiento Mensual",
                border_style="white",
            )
        )


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
                "[bold cyan]4[/] Alertas   "
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
            elif sub == "4":
                _show_alert_config(console, logs_dir)
            else:
                console.print("[bold red]Opción inválida.[/]")
                _wait_enter()

    except KeyboardInterrupt:
        return
