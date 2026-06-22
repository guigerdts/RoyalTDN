"""Live dashboard for the CellMesh crypto trading bot.

Uses Rich for terminal UI display, showing real-time events,
prices, and portfolio status. Falls back to structured logging
when Rich is not available.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class Dashboard:
    """Terminal dashboard that displays live trading activity.

    Subscribes to the EventBus and renders a Rich Layout with:

    - Header panel showing bot status (conectado / desconectado).
    - Table of recent events (ticks, signals, trades).
    - Footer panel with portfolio stats.
    """

    def __init__(self, bus: Any) -> None:
        """Initialise the dashboard.

        Args:
            bus: EventBus instance to subscribe to.
        """
        self.bus = bus
        self._running = False
        self._events: list[dict[str, Any]] = []
        self._last_render: float = 0.0
        self._queue: asyncio.Queue | None = None
        self._prices: dict[str, float] = {}
        self._stats: dict[str, Any] = {
            "capital": 0.0,
            "positions": 0,
            "drawdown": 0.0,
            "last_trade": None,
        }

    async def run(self) -> None:
        """Run the dashboard loop.

        Attempts to use Rich for live terminal display. If Rich is
        not available, falls back to printing events via ``logger.info``.
        """
        self._running = True

        # Subscribe for our own dedicated event stream
        self._queue = self.bus.subscribe()

        try:
            import rich  # noqa: F401
            await self._run_rich()
        except ImportError:
            logger.warning("Rich no disponible — usando fallback por logger")
            await self._run_logger()

    async def _run_rich(self) -> None:
        """Run the dashboard with Rich Live display."""
        from rich.console import Console
        from rich.layout import Layout
        from rich.live import Live
        from rich.panel import Panel
        from rich.table import Table

        console = Console(color_system="standard")
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        with Live(layout, console=console, refresh_per_second=1) as live:
            while self._running:
                self._drain_events()

                layout["header"].update(self._build_header())
                layout["body"].update(self._build_table())
                layout["footer"].update(self._build_footer())

                await asyncio.sleep(1)

    async def _run_logger(self) -> None:
        """Fallback: log events via loguru when Rich is unavailable."""
        while self._running:
            self._drain_events()
            await asyncio.sleep(0.5)

    def _drain_events(self) -> None:
        """Pull all pending events from the subscribed queue."""
        if self._queue is None:
            return
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                self._events.append(event)
                if len(self._events) > 100:
                    self._events.pop(0)
                self._process_event(event)
            except asyncio.QueueEmpty:
                break

    def _process_event(self, event: dict[str, Any]) -> None:
        """Update internal state from an event.

        Args:
            event: The event dict to process.
        """
        etype = event.get("type", "")

        if etype == "tick":
            symbol = event.get("symbol", "")
            price = event.get("price", 0.0)
            self._prices[symbol] = price

        elif etype == "signal":
            logger.info(
                "Senal: {} {} @ ${:.2f}",
                event.get("symbol", ""),
                event.get("action", ""),
                event.get("price", 0.0),
            )

        elif etype == "trade":
            self._stats["last_trade"] = event
            logger.info(
                "Trade: {} {} {} @ ${:.2f}",
                event.get("symbol", ""),
                event.get("action", ""),
                event.get("qty", 0),
                event.get("price", 0.0),
            )

    def _build_header(self) -> Any:
        """Build the header panel with connection status."""
        from rich.panel import Panel

        status = "conectado" if self._running else "desconectado"
        return Panel(
            f"CellMesh — Crypto Trading Bot  |  Estado: {status}",
            style="bold",
        )

    def _build_table(self) -> Any:
        """Build the events table panel."""
        from rich.panel import Panel
        from rich.table import Table

        table = Table(title="Eventos recientes")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Symbol", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Price", justify="right")
        table.add_column("Action", style="magenta")
        table.add_column("Status", style="blue")

        for event in self._events[-20:]:
            ts = str(event.get("timestamp", ""))
            if len(ts) > 19:
                ts = ts[:19]
            symbol = event.get("symbol", "")
            etype = event.get("type", "")
            price = event.get("price", 0.0)
            action = event.get("action", "")
            status = event.get("status", "OK")
            table.add_row(
                ts,
                symbol,
                etype,
                f"${price:.2f}" if price else "-",
                action or "-",
                status,
            )

        return Panel(table)

    def _build_footer(self) -> Any:
        """Build the stats footer panel."""
        from rich.panel import Panel

        cap = self._stats.get("capital", 0.0)
        pos = self._stats.get("positions", 0)
        dd = self._stats.get("drawdown", 0.0)
        trade = self._stats.get("last_trade")

        parts = [
            f"Capital: ${cap:,.2f}",
            f"Posiciones: {pos}",
            f"Drawdown: {dd:.2%}",
        ]

        if trade:
            parts.append(
                f"Ultimo trade: {trade.get('symbol', '')} "
                f"{trade.get('action', '')} "
                f"{trade.get('qty', 0)} @ ${trade.get('price', 0):.2f}"
            )

        return Panel("  |  ".join(parts))

    async def stop(self) -> None:
        """Gracefully stop the dashboard loop."""
        self._running = False
        logger.info("Dashboard detenido")
