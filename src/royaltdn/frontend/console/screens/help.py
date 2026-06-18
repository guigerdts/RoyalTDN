"""Help screen — full command reference table."""

from typing import Any, Optional

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from royaltdn.frontend.console.components.widgets import create_footer, create_header


def render_help(state: dict, log_buffer: Any, status_message: str | None = None) -> Layout:
    """Render the help/reference screen.

    Args:
        state: The full ``StateLoader.load_all()`` dict.
        log_buffer: ``LogBuffer`` instance (passed but not used here).
        status_message: Optional message shown in the footer bar.

    Returns:
        A ``Layout`` with header, commands table, and footer.
    """
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )

    layout["header"].update(create_header(state))

    # ── Build commands table ────────────────────────────────────────────
    table = Table(
        title="[bold white]COMANDOS DE LA CONSOLA[/]",
        title_style="bold white",
        border_style="cyan",
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Comando", justify="center", width=18)
    table.add_column("Alternativas", justify="center", width=18)
    table.add_column("Acción", justify="left")

    table.add_row("1", "d / dashboard", "Dashboard — KPIs, posiciones, señales")
    table.add_row("2", "s / scanner", "Scanner — resultados del escaneo")
    table.add_row("3", "e / estrategias", "Estrategias — activas y de usuario")
    table.add_row("4", "t / trades", "Trades — historial y métricas")
    table.add_row("5", "l / logs", "Logs — registro en vivo con filtros")
    table.add_row("", "", "")
    table.add_row("p", "pause", "Pausar el bot (señal IPC)")
    table.add_row("r", "resume", "Reanudar el bot")
    table.add_row("scan", "", "Disparar scanner manual")
    table.add_row("", "", "")
    table.add_row("i", "", "Filtrar logs: solo INFO")
    table.add_row("w", "", "Filtrar logs: solo WARNING")
    table.add_row("e", "", "Filtrar logs: solo ERROR")
    table.add_row("a", "", "Quitar filtro de nivel")
    table.add_row("", "", "")
    table.add_row("h", "help", "Mostrar esta pantalla de ayuda")
    table.add_row("q", "quit / exit", "Salir de la consola")

    help_panel = Panel(
        table,
        border_style="bright_blue",
        title="[bold white]📖 Ayuda[/]",
        subtitle="[dim]Escribí cualquier comando para navegar[/]",
    )

    layout["body"].update(help_panel)
    layout["footer"].update(create_footer(active_screen=0, status_message=status_message))

    return layout
