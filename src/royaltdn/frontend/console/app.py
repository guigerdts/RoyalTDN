"""Console application — Rich Live loop, keyboard input, screen dispatch.

Entry point: ``run_console()``
"""

import select
import sys
from typing import Any, Optional

import colorama
from loguru import logger
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

# ── Constants ─────────────────────────────────────────────────────────────

REFRESH_RATE = 4  # FPS — matches 0.25 s key-poll timeout
KEY_TIMEOUT = 1.0 / REFRESH_RATE

# ── Key helpers ───────────────────────────────────────────────────────────


def get_key(timeout: float = KEY_TIMEOUT) -> Optional[str]:
    """Non-blocking single-character read from stdin.

    Uses ``select.select`` with *timeout* seconds.  Returns the character
    read, or ``None`` if no key was pressed.
    """
    try:
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            return sys.stdin.read(1)
    except (ValueError, KeyboardInterrupt):
        pass
    return None


# ── Key handler ───────────────────────────────────────────────────────────


def handle_key(key: str, state: dict) -> dict:
    """Process a single key press and return updated state dict.

    Args:
        key: The key that was pressed (lowercase string).
        state: Current state dict with keys ``current_screen``, ``running``,
            ``filters``.

    Returns:
        Updated state dict (never mutated in place).
    """
    new_state = {
        "current_screen": state["current_screen"],
        "running": state["running"],
        "filters": dict(state["filters"]),
    }

    if key in ("1", "2", "3", "4", "5"):
        new_state["current_screen"] = int(key) - 1  # 0-indexed

    elif key == "p":
        pause_bot()
        logger.info("Pause signal sent")

    elif key == "r":
        resume_bot()
        logger.info("Resume signal sent")

    elif key == "s":
        trigger_scanner()
        logger.info("Scanner trigger sent")

    elif key == "i":
        new_state["filters"]["level_filter"] = (
            None if new_state["filters"]["level_filter"] == "INFO" else "INFO"
        )
        logger.info("Log level filter toggled: {}", new_state["filters"]["level_filter"])

    elif key == "w":
        new_state["filters"]["level_filter"] = (
            None if new_state["filters"]["level_filter"] == "WARNING" else "WARNING"
        )
        logger.info("Log level filter toggled: {}", new_state["filters"]["level_filter"])

    elif key == "e":
        new_state["filters"]["level_filter"] = (
            None if new_state["filters"]["level_filter"] == "ERROR" else "ERROR"
        )
        logger.info("Log level filter toggled: {}", new_state["filters"]["level_filter"])

    elif key == "a":
        new_state["filters"]["level_filter"] = None
        logger.info("Log level filter cleared")

    elif key == "q":
        logger.info("Quit key pressed — stopping console")
        new_state["running"] = False

    return new_state


# ── Screen dispatch ───────────────────────────────────────────────────────


def render_screen(
    screen_id: int,
    state: dict,
    log_buffer: LogBuffer,
    filters: dict[str, Optional[str]],
) -> Layout:
    """Dispatch rendering to the correct screen function.

    Args:
        screen_id: 0–4 for Dashboard / Scanner / Estrategias / Trades / Logs.
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance.
        filters: Dict with optional keys ``level_filter``, ``module_filter``,
            ``text_filter``.

    Returns:
        A ``Layout`` ready for ``Live.update()``.
    """
    if screen_id == 0:
        return render_dashboard(state, log_buffer)
    elif screen_id == 1:
        return render_scanner(state, log_buffer)
    elif screen_id == 2:
        return render_estrategias(state, log_buffer)
    elif screen_id == 3:
        return render_trades(state, log_buffer)
    elif screen_id == 4:
        return render_logs(
            state,
            log_buffer,
            level_filter=filters.get("level_filter"),
            module_filter=filters.get("module_filter"),
            text_filter=filters.get("text_filter"),
        )
    return render_dashboard(state, log_buffer)


# ── Main entry ────────────────────────────────────────────────────────────


def run_console(logs_dir: str = "logs") -> None:
    """Launch the interactive Rich console.

    Initialises ``StateLoader``, ``LogBuffer``, hooks it as a Loguru sink,
    and starts a ``Live`` render loop at 4 FPS with keyboard navigation.

    Key bindings:
        1-5 → switch screen
        p   → pause bot
        r   → resume bot
        s   → trigger scanner
        i   → filter logs: INFO
        w   → filter logs: WARNING
        e   → filter logs: ERROR
        a   → filter logs: ALL (clear level filter)
        q   → quit console
        Ctrl+C → quit console
    """
    colorama.init()

    loader = StateLoader(logs_dir=logs_dir)
    log_buffer = LogBuffer(max_lines=200)
    setup_console_log_handler(log_buffer)

    state = {
        "current_screen": 0,
        "running": True,
        "filters": {
            "level_filter": None,
            "module_filter": None,
            "text_filter": None,
        },
    }

    # Initial renderable
    try:
        data = loader.load_all()
        renderable = render_screen(
            state["current_screen"], data, log_buffer, state["filters"]
        )

        with Live(renderable, refresh_per_second=REFRESH_RATE, screen=True) as live:
            while state["running"]:
                # ── Key capture ──
                key = get_key(timeout=KEY_TIMEOUT)

                if key is not None:
                    key = key.lower()
                    state = handle_key(key, state)

                # ── Re-read state and re-render ──
                data = loader.load_all()
                live.update(
                    render_screen(
                        state["current_screen"], data, log_buffer, state["filters"]
                    )
                )

    except KeyboardInterrupt:
        logger.info("Ctrl+C received — stopping console")
    finally:
        colorama.deinit()
        print("\n🛑 Consola detenida.")
