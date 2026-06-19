"""RoyalTDNApp — main Textual application with screen registry, bindings, and live polling."""

from typing import Optional

from loguru import logger
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.timer import Timer

from royaltdn.frontend.console.commands import pause_bot, resume_bot, trigger_scanner
from royaltdn.frontend.console.components.state import StateLoader
from royaltdn.frontend.console.log_handler import LogBuffer, setup_console_log_handler

from royaltdn.frontend.textual.screens import (
    BuilderScreen,
    DashboardScreen,
    EstrategiasScreen,
    HelpScreen,
    LogsScreen,
    ScannerScreen,
    TradesScreen,
)
from royaltdn.frontend.textual.widgets import RoyalTDNFooter, RoyalTDNHeader


class RoyalTDNApp(App):
    """Main Textual application for RoyalTDN.

    Manages 6 content panels (registered as ``SCREENS`` for documentation),
    a status header, a command footer, and a ``set_interval`` timer that
    polls ``StateLoader`` every 500 ms to keep all widgets up to date.

    Screen switching is done via visibility toggling inside a shared
    ``Container``, keeping ``RoyalTDNHeader`` and ``RoyalTDNFooter``
    persistent across switches.
    """

    CSS_PATH = ["css/app.tcss", "css/builder.tcss"]

    BINDINGS = [
        Binding("1", "switch_screen('dashboard')", "Dashboard"),
        Binding("2", "switch_screen('scanner')", "Scanner"),
        Binding("3", "switch_screen('estrategias')", "Estrategias"),
        Binding("4", "switch_screen('trades')", "Trades"),
        Binding("5", "switch_screen('logs')", "Logs"),
        Binding("6", "switch_screen('builder')", "Builder"),
        Binding("p", "pause_bot", "Pausar"),
        Binding("r", "resume_bot", "Reanudar"),
        Binding("s", "trigger_scanner", "Scan now"),
        Binding("h", "switch_screen('help')", "Ayuda", priority=True),
        Binding("q", "quit", "Salir", priority=True),
    ]

    # Screen registry — used by action_switch_screen for lookup.
    SCREENS: dict[str, type] = {
        "dashboard": DashboardScreen,
        "scanner": ScannerScreen,
        "estrategias": EstrategiasScreen,
        "trades": TradesScreen,
        "logs": LogsScreen,
        "builder": BuilderScreen,
        "help": HelpScreen,
    }

    def __init__(self, logs_dir: str = "logs") -> None:
        super().__init__()
        self._logs_dir = logs_dir
        self._state_loader: Optional[StateLoader] = None
        self._log_buffer: Optional[LogBuffer] = None
        self._timer: Optional[Timer] = None
        self._screen_map: dict[str, Container] = {}

    # ── Application lifecycle ─────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Build the root UI: persistent header, content container, footer."""
        yield RoyalTDNHeader(id="header")
        with Container(id="screen-content"):
            yield DashboardScreen(id="dashboard")
            yield ScannerScreen(id="scanner")
            yield EstrategiasScreen(id="estrategias")
            yield TradesScreen(id="trades")
            yield LogsScreen(id="logs")
            yield BuilderScreen(id="builder")
            yield HelpScreen(id="help")
        yield RoyalTDNFooter(id="footer")

    def on_mount(self) -> None:
        """Initialise shared services, build screen map, set up timer."""
        self._state_loader = StateLoader(logs_dir=self._logs_dir)
        self._log_buffer = LogBuffer(max_lines=200)
        setup_console_log_handler(self._log_buffer)

        # Build screen-id → widget lookup, show only dashboard
        content = self.query_one("#screen-content", Container)
        for child in content.children:
            self._screen_map[child.id or ""] = child
            child.display = child.id == "dashboard"  # type: ignore[attr-defined]

        # Start live polling at 0.5 s intervals
        self._timer = self.set_interval(0.5, self.refresh_data)
        self.refresh_data()

    # ── Periodic refresh ──────────────────────────────────────────────

    def refresh_data(self) -> None:
        """Load fresh state and route updates to the active screen."""
        if not self._state_loader or not self._log_buffer:
            return

        state = self._state_loader.load_all()
        log_lines = self._log_buffer.get_lines()

        self._update_header(state)
        self._update_footer(state)
        self._update_active_screen(state, log_lines)

    def _update_header(self, state: dict) -> None:
        status = state.get("status", {})
        try:
            header = self.query_one("#header", RoyalTDNHeader)
            header.update_data(
                status=status.get("bot_status", "OFFLINE"),
                mode=status.get("mode", "paper"),
                uptime=status.get("uptime", "0:00:00"),
                scanner_info=status.get("last_scan", "\u2014"),
            )
        except Exception:
            pass  # header may not be mounted yet

    def _update_footer(self, state: dict) -> None:
        status = state.get("status", {})
        try:
            footer = self.query_one("#footer", RoyalTDNFooter)
            footer.update_status(status.get("bot_status", "OFFLINE"))
        except Exception:
            pass

    def _update_active_screen(self, state: dict, log_lines: list[str]) -> None:
        for screen_id, screen_widget in self._screen_map.items():
            if screen_widget.display is True:
                if hasattr(screen_widget, "update_data"):
                    try:
                        screen_widget.update_data(state, log_lines)  # type: ignore[misc]
                    except Exception:
                        logger.error("DashboardScreen.update_data() failed")
                break

    # ── Actions ───────────────────────────────────────────────────────

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch the visible content panel by name.

        Args:
            screen_name: One of ``dashboard``, ``scanner``, ``estrategias``,
                ``trades``, ``logs``, ``builder``, ``help``.
        """
        if screen_name not in self._screen_map:
            self.notify(f"Screen '{screen_name}' not available", severity="warning")
            return

        for sid, child in self._screen_map.items():
            child.display = sid == screen_name  # type: ignore[attr-defined]

    def action_pause_bot(self) -> None:
        """Write pause signal and notify."""
        pause_bot(logs_dir=self._logs_dir)
        self.notify("Bot PAUSED", severity="information")

    def action_resume_bot(self) -> None:
        """Write resume signal and notify."""
        resume_bot(logs_dir=self._logs_dir)
        self.notify("Bot RESUMED", severity="information")

    def action_trigger_scanner(self) -> None:
        """Write scan-now signal and notify."""
        trigger_scanner(logs_dir=self._logs_dir)
        self.notify("Scanner triggered", severity="information")

    def action_quit(self) -> None:
        """Clean up timer and exit."""
        if self._timer is not None:
            self._timer.stop()
        self.exit()
