"""Console application — Rich Live display + standard ``input()`` for commands.

Compatible with every terminal (Termux, proot, Android, Windows, Linux, macOS)
because command input uses Python's built-in ``input()``, not Rich console or
select-based key capture.
"""

from typing import Optional

import colorama
from loguru import logger
from rich.live import Live

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

# ── Command handler ──────────────────────────────────────────────────────


def handle_command(
    cmd: str,
    current_screen: str,
    level_filter: Optional[str],
    module_filter: Optional[str],
    text_filter: Optional[str],
) -> tuple[bool, str, Optional[str], Optional[str], Optional[str]]:
    """Process a text command and return updated state.

    Returns:
        Tuple of ``(running, current_screen, level_filter, module_filter, text_filter)``.
    """
    new_screen = current_screen

    if cmd in ("1", "d", "dashboard"):
        new_screen = "dashboard"
    elif cmd in ("2", "s", "scanner"):
        new_screen = "scanner"
    elif cmd in ("3", "e", "estrategias", "strategies"):
        new_screen = "estrategias"
    elif cmd in ("4", "t", "trades"):
        new_screen = "trades"
    elif cmd in ("5", "l", "logs"):
        new_screen = "logs"

    elif cmd in ("p", "pause"):
        pause_bot()
        print("✅ Señal de pausa enviada")
        logger.info("Pause command executed")
    elif cmd in ("r", "resume"):
        resume_bot()
        print("✅ Señal de reanudación enviada")
        logger.info("Resume command executed")
    elif cmd in ("scan",):
        trigger_scanner()
        print("✅ Scanner disparado")
        logger.info("Scan command executed")

    elif cmd == "i":
        level_filter = None if level_filter == "INFO" else "INFO"
        print(f"Filtro: {level_filter or 'TODOS'}")
    elif cmd == "w":
        level_filter = None if level_filter == "WARNING" else "WARNING"
        print(f"Filtro: {level_filter or 'TODOS'}")
    elif cmd == "e":
        level_filter = None if level_filter == "ERROR" else "ERROR"
        print(f"Filtro: {level_filter or 'TODOS'}")
    elif cmd == "a":
        level_filter = None
        print("Filtro: TODOS")

    elif cmd in ("h", "help"):
        print(
            "Comandos: [1]Dashboard [2]Scanner [3]Estrategias [4]Trades [5]Logs | "
            "[p]Pausar [r]Reanudar [scan]Scan [i]INFO [w]WARN [e]ERROR [a]ALL [q]Salir"
        )

    elif cmd in ("q", "exit", "quit"):
        logger.info("Quit command — stopping console")
        return (False, new_screen, level_filter, module_filter, text_filter)

    return (True, new_screen, level_filter, module_filter, text_filter)


# ── Screen dispatch ───────────────────────────────────────────────────────


def render_screen(
    screen_id: str,
    state: dict,
    log_buffer: LogBuffer,
    level_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
    text_filter: Optional[str] = None,
):
    """Dispatch rendering to the correct screen function.

    Args:
        screen_id: ``"dashboard"``, ``"scanner"``, ``"estrategias"``,
            ``"trades"``, or ``"logs"``.
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance.
        level_filter: Optional log level filter.
        module_filter: Optional module name filter.
        text_filter: Optional free-text filter.
    """
    if screen_id == "dashboard":
        return render_dashboard(state, log_buffer)
    elif screen_id == "scanner":
        return render_scanner(state, log_buffer)
    elif screen_id == "estrategias":
        return render_estrategias(state, log_buffer)
    elif screen_id == "trades":
        return render_trades(state, log_buffer)
    elif screen_id == "logs":
        return render_logs(
            state,
            log_buffer,
            level_filter=level_filter,
            module_filter=module_filter,
            text_filter=text_filter,
        )
    return render_dashboard(state, log_buffer)


# ── Main entry ────────────────────────────────────────────────────────────


def run_console(logs_dir: str = "logs") -> None:
    """Launch the Rich console display with terminal-based command input.

    The dashboard renders with Rich Live in a loop.  At each iteration it
    blocks on ``input()`` to read a command from the user.  Once a command
    is processed the display updates and waits for the next command.

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
    colorama.init()

    loader = StateLoader(logs_dir=logs_dir)
    log_buffer = LogBuffer(max_lines=200)
    setup_console_log_handler(log_buffer)

    current_screen: str = "dashboard"
    level_filter: Optional[str] = None
    module_filter: Optional[str] = None
    text_filter: Optional[str] = None
    running = True

    try:
        initial = render_screen(
            current_screen, loader.load_all(), log_buffer,
            level_filter, module_filter, text_filter,
        )

        with Live(initial, refresh_per_second=2, screen=True) as live:
            while running:
                # ── Re-read state and re-render ──
                state = loader.load_all()
                layout = render_screen(
                    current_screen, state, log_buffer,
                    level_filter, module_filter, text_filter,
                )
                live.update(layout)

                # ── Wait for command with standard input() ──
                try:
                    cmd = input(">> ").strip().lower()
                    if cmd:
                        running, current_screen, level_filter, module_filter, \
                            text_filter = handle_command(
                                cmd, current_screen,
                                level_filter, module_filter, text_filter,
                            )
                except (EOFError, KeyboardInterrupt):
                    running = False

    except KeyboardInterrupt:
        logger.info("Ctrl+C received — stopping console")
    finally:
        colorama.deinit()
        print("\n🛑 Consola detenida.")
