"""Screen renderers — each exports a ``render_*`` function returning ``Layout``."""

from royaltdn.frontend.console.screens.dashboard import render_dashboard
from royaltdn.frontend.console.screens.estrategias import render_estrategias
from royaltdn.frontend.console.screens.logs import render_logs
from royaltdn.frontend.console.screens.scanner import render_scanner
from royaltdn.frontend.console.screens.trades import render_trades

__all__ = [
    "render_dashboard",
    "render_scanner",
    "render_estrategias",
    "render_trades",
    "render_logs",
]
