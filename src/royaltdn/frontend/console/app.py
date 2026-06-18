"""Console application — Rich Live loop, command-based navigation via text input.

Entry point: ``run_console()``

Uses ``Console.input()`` with Enter for broad Termux/proot/Android compatibility.
"""

from typing import Any, Optional

from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.layout import Layout

from royaltdn.frontend.console.commands import pause_bot, resume_bot, trigger_scanner
from royaltdn.frontend.console.components.state import StateLoader
from royaltdn.frontend.console.log_handler import LogBuffer, setup_console_log_handler
from royaltdn.frontend.console.screens import (
    render_dashboard,
    render_estrategias,
    render_logs,
    render_scanner,
    render_trades,
)
from royaltdn.frontend.console.components.widgets import create_footer

# ── Console instance ──────────────────────────────────────────────────────

_console = Console()

# ── Command handler ──────────────────────────────────────────────────────


def handle_command(
    cmd: str,
    current_screen: int,
    level_filter: Optional[str],
    module_filter: Optional[str],
    text_filter: Optional[str],
) -> tuple[bool, int, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Process a text command and return updated state.

    Returns:
        Tuple of ``(running, current_screen, level_filter, module_filter,
                     text_filter, status_message)``.
    """
    status_message: Optional[str] = None
    new_screen = current_screen

    if cmd in ("1", "d", "dashboard"):
        new_screen = 0
    elif cmd in ("2", "s", "scanner"):
        new_screen = 1
    elif cmd in ("3", "e", "estrategias", "strategies"):
        new_screen = 2
    elif cmd in ("4", "t", "trades"):
        new_screen = 3
    elif cmd in ("5", "l", "logs"):
        new_screen = 4

    elif cmd in ("p", "pause"):
        pause_bot()
        status_message = "✅ Señal de pausa enviada"
        logger.info("Pause command executed")
    elif cmd in ("r", "resume"):
        resume_bot()
        status_message = "✅ Señal de reanudación enviada"
        logger.info("Resume command executed")
    elif cmd in ("scan",):
        trigger_scanner()
        status_message = "✅ Scanner disparado"
        logger.info("Scan command executed")

    elif cmd == "i":
        level_filter = None if level_filter == "INFO" else "INFO"
        status_message = f"Filtro: {level_filter or 'TODOS'}"
    elif cmd == "w":
        level_filter = None if level_filter == "WARNING" else "WARNING"
        status_message = f"Filtro: {level_filter or 'TODOS'}"
    elif cmd == "e":
        level_filter = None if level_filter == "ERROR" else "ERROR"
        status_message = f"Filtro: {level_filter or 'TODOS'}"
    elif cmd == "a":
        level_filter = None
        status_message = "Filtro: TODOS"

    elif cmd in ("h", "help"):
        status_message = (
            "Comandos: [1]Dashboard [2]Scanner [3]Estrategias [4]Trades [5]Logs | "
            "[p]Pausar [r]Reanudar [scan]Scan [i]INFO [w]WARN [e]ERROR [a]ALL [q]Salir"
        )

    elif cmd in ("q", "exit", "quit"):
        logger.info("Quit command — stopping console")
        return (False, new_screen, level_filter, module_filter, text_filter, None)

    return (True, new_screen, level_filter, module_filter, text_filter, status_message)


# ── Screen dispatch ───────────────────────────────────────────────────────


def render_screen(
    screen_id: int,
    state: dict,
    log_buffer: LogBuffer,
    level_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
    text_filter: Optional[str] = None,
    status_message: Optional[str] = None,
) -> Layout:
    """Dispatch rendering to the correct screen function.

    Args:
        screen_id: 0–4 for Dashboard / Scanner / Estrategias / Trades / Logs.
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance.
        level_filter: Optional log level filter.
        module_filter: Optional module name filter.
        text_filter: Optional free-text filter.
        status_message: Optional message shown in footer (confirmation, help).

    Returns:
        A ``Layout`` ready for ``Live.update()``.
    """
    if screen_id == 0:
        layout = render_dashboard(state, log_buffer)
    elif screen_id == 1:
        layout = render_scanner(state, log_buffer)
    elif screen_id == 2:
        layout = render_estrategias(state, log_buffer)
    elif screen_id == 3:
        layout = render_trades(state, log_buffer)
    elif screen_id == 4:
        layout = render_logs(
            state,
            log_buffer,
            level_filter=level_filter,
            module_filter=module_filter,
            text_filter=text_filter,
        )
    else:
        layout = render_dashboard(state, log_buffer)

    # Overlay status message on footer if present
    if status_message:
        try:
            current_footer = layout["footer"]
            layout["footer"].update(
                create_footer(
                    active_screen=screen_id + 1,
                    status_message=status_message,
                )
            )
        except (KeyError, AttributeError):
            pass

    return layout


# ── Main entry ────────────────────────────────────────────────────────────


def run_console(logs_dir: str = "logs") -> None:
    """Launch the interactive Rich console with command-based navigation.

    Initialises ``StateLoader``, ``LogBuffer``, hooks it as a Loguru sink,
    and starts a ``Live`` render loop at 2 FPS.  Instead of single-key
    capture (incompatible with Termux/proot/Android), the user types short
    commands and presses Enter.

    Commands:
        1/d/dashboard → Dashboard screen
        2/s/scanner   → Scanner screen
        3/e/estrategias → Estrategias screen
        4/t/trades    → Trades screen
        5/l/logs      → Logs screen
        p/pause       → Pause bot
        r/resume      → Resume bot
        scan          → Trigger scanner
        i             → Filter logs: INFO
        w             → Filter logs: WARNING
        e             → Filter logs: ERROR
        a             → Clear log level filter
        h/help        → Show help
        q/exit/quit   → Quit console
    """
    loader = StateLoader(logs_dir=logs_dir)
    log_buffer = LogBuffer(max_lines=200)
    setup_console_log_handler(log_buffer)

    current_screen = 0  # 0=Dashboard, 1=Scanner, 2=Estrategias, 3=Trades, 4=Logs
    level_filter: Optional[str] = None
    module_filter: Optional[str] = None
    text_filter: Optional[str] = None
    running = True
    status_message: Optional[str] = None

    try:
        state = loader.load_all()
        layout = render_screen(
            current_screen, state, log_buffer,
            level_filter, module_filter, text_filter, status_message,
        )

        with Live(layout, refresh_per_second=2, screen=True) as live:
            while running:
                # ── Re-read state and re-render ──
                state = loader.load_all()
                layout = render_screen(
                    current_screen, state, log_buffer,
                    level_filter, module_filter, text_filter, status_message,
                )
                live.update(layout)

                # ── Text command input ──
                try:
                    cmd = _console.input("[bold cyan]>> [/bold cyan]", timeout=1.0)
                    cmd = cmd.strip().lower()
                    if cmd:
                        running, current_screen, level_filter, module_filter, \
                            text_filter, status_message = handle_command(
                                cmd, current_screen,
                                level_filter, module_filter, text_filter,
                            )
                    else:
                        # Empty input (timeout) → clear transient status message
                        status_message = None
                except Exception:
                    pass

    except KeyboardInterrupt:
        logger.info("Ctrl+C received — stopping console")
    finally:
        print("\n🛑 Consola detenida.")
