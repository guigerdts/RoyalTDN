"""Console application — Rich Live display with threaded input.

Compatible with every terminal (Termux, proot, Android, Windows, Linux, macOS).

``input()`` runs in a **dedicated daemon thread** so it never blocks the Rich
``Live`` render loop.  Commands are pushed through a ``queue.Queue`` and
consumed non-blockingly on each render tick.
"""

import queue
import threading
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
    render_help,
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
) -> tuple[bool, str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Process a text command and return updated state.

    Returns:
        Tuple of ``(running, current_screen, level_filter, module_filter,
        text_filter, status_message)``.
    """
    new_screen = current_screen
    status_message: Optional[str] = None

    if cmd in ("1", "d", "dashboard"):
        new_screen = "dashboard"
        status_message = "📊 Dashboard"
    elif cmd in ("2", "s", "scanner"):
        new_screen = "scanner"
        status_message = "🔍 Scanner"
    elif cmd in ("3", "e", "estrategias", "strategies"):
        new_screen = "estrategias"
        status_message = "⚙️ Estrategias"
    elif cmd in ("4", "t", "trades"):
        new_screen = "trades"
        status_message = "📈 Trades"
    elif cmd in ("5", "l", "logs"):
        new_screen = "logs"
        status_message = "📋 Logs"

    elif cmd in ("p", "pause"):
        pause_bot()
        logger.info("Pause command executed")
        status_message = "✅ Bot PAUSADO"
    elif cmd in ("r", "resume"):
        resume_bot()
        logger.info("Resume command executed")
        status_message = "▶️ Bot REANUDADO"
    elif cmd in ("scan",):
        trigger_scanner()
        logger.info("Scan command executed")
        status_message = "🔍 Scanner disparado"

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
        new_screen = "help"
        status_message = "📖 Ayuda"

    elif cmd in ("q", "exit", "quit"):
        logger.info("Quit command — stopping console")
        return (False, new_screen, level_filter, module_filter, text_filter, None)

    return (True, new_screen, level_filter, module_filter, text_filter, status_message)


# ── Screen dispatch ───────────────────────────────────────────────────────


def render_screen(
    screen_id: str,
    state: dict,
    log_buffer: LogBuffer,
    level_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
    text_filter: Optional[str] = None,
    status_message: Optional[str] = None,
):
    """Dispatch rendering to the correct screen function.

    Args:
        screen_id: ``"dashboard"``, ``"scanner"``, ``"estrategias"``,
            ``"trades"``, ``"logs"``, or ``"help"``.
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance.
        level_filter: Optional log level filter.
        module_filter: Optional module name filter.
        text_filter: Optional free-text filter.
        status_message: Optional message shown in the footer bar.
    """
    kwargs = {"state": state, "log_buffer": log_buffer, "status_message": status_message}
    if screen_id == "dashboard":
        return render_dashboard(**kwargs)
    elif screen_id == "scanner":
        return render_scanner(**kwargs)
    elif screen_id == "estrategias":
        return render_estrategias(**kwargs)
    elif screen_id == "trades":
        return render_trades(**kwargs)
    elif screen_id == "logs":
        return render_logs(
            state=state,
            log_buffer=log_buffer,
            level_filter=level_filter,
            module_filter=module_filter,
            text_filter=text_filter,
            status_message=status_message,
        )
    elif screen_id == "help":
        return render_help(**kwargs)
    # Fallback to dashboard
    return render_dashboard(**kwargs)


# ── Main entry ────────────────────────────────────────────────────────────


# ── Input thread ────────────────────────────────────────────────────────


def _input_worker(cmd_queue: "queue.Queue[str]", stop_event: threading.Event) -> None:
    """Daemon thread: reads ``input()`` and pushes commands to a queue.

    Runs until ``stop_event`` is set.  Exceptions (``EOFError``,
    ``KeyboardInterrupt``) set the event and exit cleanly.
    """
    while not stop_event.is_set():
        try:
            raw = input(">> ")
            cmd = raw.strip().lower()
            if cmd:
                cmd_queue.put_nowait(cmd)
        except (EOFError, KeyboardInterrupt):
            stop_event.set()
            break


# ── Main entry ──────────────────────────────────────────────────────────


def run_console(logs_dir: str = "logs") -> None:
    """Launch the Rich console with threaded input.

    ``input()`` runs in a **separate daemon thread** so it never blocks the
    ``Live`` render loop.  Commands are consumed non-blockingly on each tick.
    This design is compatible with every terminal including Termux/proot.

    Screens:
        1/d/dashboard    → Dashboard
        2/s/scanner      → Scanner
        3/e/estrategias  → Estrategias
        4/t/trades       → Trades
        5/l/logs         → Logs (filters: i=INFO w=WARN e=ERROR a=ALL)
        h/help           → Help screen with full command list

    Controls:
        p/pause          → Pause bot
        r/resume         → Resume bot
        scan             → Trigger scanner
        q/exit/quit      → Quit console
    """
    colorama.init()

    loader = StateLoader(logs_dir=logs_dir)
    log_buffer = LogBuffer(max_lines=200)
    setup_console_log_handler(log_buffer)

    current_screen: str = "dashboard"
    level_filter: Optional[str] = None
    module_filter: Optional[str] = None
    text_filter: Optional[str] = None
    status_message: Optional[str] = None
    running = True

    # Thread synchronisation
    cmd_queue: "queue.Queue[str]" = queue.Queue()
    stop_event = threading.Event()

    input_t = threading.Thread(
        target=_input_worker,
        args=(cmd_queue, stop_event),
        daemon=True,
    )
    input_t.start()

    try:
        initial = render_screen(
            current_screen, loader.load_all(), log_buffer,
            level_filter, module_filter, text_filter, status_message,
        )

        with Live(initial, refresh_per_second=2, screen=True) as live:
            while running:
                # ── Process queued commands (non-blocking) ──
                try:
                    while True:
                        cmd = cmd_queue.get_nowait()
                        running, current_screen, level_filter, module_filter, \
                            text_filter, status_message = handle_command(
                                cmd, current_screen,
                                level_filter, module_filter, text_filter,
                            )
                except queue.Empty:
                    pass

                # ── Re-read state and re-render ──
                state = loader.load_all()
                layout = render_screen(
                    current_screen, state, log_buffer,
                    level_filter, module_filter, text_filter, status_message,
                )
                live.update(layout)

                # Auto-clear transient feedback after one render cycle
                status_message = None

    except KeyboardInterrupt:
        logger.info("Ctrl+C received — stopping console")
    finally:
        stop_event.set()
        colorama.deinit()
        print("\n🛑 Consola detenida.")
