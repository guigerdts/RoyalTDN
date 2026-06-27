"""Telegram alerts — consolidados por trade + métricas del bot.

Acumula eventos de trading (signal → approved → executed → position)
agrupados por ``trade_id`` y envía un único mensaje por operación
con el detalle completo y el estado actual del portfolio.

Los eventos ``rejected`` y ``position.closed`` se agrupan en un buffer
interno y se envían cada 60s como mensajes resumidos para evitar
límites de tasa (429) de la API de Telegram.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger


class TelegramAlerts:
    """Telegram notifier con mensajes consolidados por trade.

    Suscribe al EventBus, agrupa eventos por ``trade_id``, y al
    completarse el ciclo (posición abierta) envía un solo HTML con:

    - Señal, aprobación, ejecución, posición
    - Capital, posiciones abiertas, drawdown, última operación
    """

    def __init__(
        self,
        bus: Any,
        bot_token: str,
        chat_id: str,
        portfolio: Any = None,
        batch_interval: int = 60,
    ) -> None:
        """Initialise the Telegram alert system.

        Args:
            bus: EventBus instance to subscribe to.
            bot_token: Telegram Bot API token.
            chat_id: Numeric chat or channel ID.
            portfolio: Optional Portfolio instance for live metrics.
            batch_interval: Seconds between batched message flushes (default 60).
        """
        self._token = bot_token
        self._chat_id = chat_id
        self._portfolio = portfolio
        self._queue = bus.subscribe()
        self._running = False

        # Acumulador: trade_id → dict con partes del mensaje
        self._pending: dict[str, dict[str, Any]] = {}
        self._last_trade_ts: float = 0.0

        # Batch buffer
        self._pending_events: list[dict] = []
        self._batch_interval = batch_interval
        self._flush_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Run the alert loop — consume events from the bus queue."""
        import httpx

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(
            "TelegramAlerts iniciado — chat_id={}",
            self._chat_id,
        )

        try:
            async with httpx.AsyncClient() as client:
                while self._running:
                    try:
                        event = await asyncio.wait_for(
                            self._queue.get(), timeout=1.0,
                        )
                    except asyncio.TimeoutError:
                        continue

                    await self._handle_event(client, event)
        finally:
            if self._flush_task and not self._flush_task.done():
                self._flush_task.cancel()

    async def stop(self) -> None:
        """Gracefully stop the alert loop — flush remaining events first."""
        self._running = False
        import httpx

        async with httpx.AsyncClient() as client:
            await self._flush(client)
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        logger.info("TelegramAlerts detenido")

    # ------------------------------------------------------------------
    # Event router
    # ------------------------------------------------------------------

    async def _handle_event(self, client: Any, event: dict[str, Any]) -> None:
        """Route a single event — qualifying types append to batch buffer."""
        etype = event.get("type", "")
        trade_id: str = event.get("trade_id", "") or ""

        if etype not in ("signal", "approved", "rejected", "executed", "position"):
            return

        # ── Signal — store context, no message ───────────────────────
        if etype == "signal":
            if trade_id:
                self._pending[trade_id] = {
                    "symbol": event.get("symbol", "?"),
                    "action": event.get("action", ""),
                    "price": event.get("price", 0.0),
                    "strategy": event.get("strategy", "?"),
                }
            # No trade_id: silently ignored (legacy, not batch-qualifying)
            return

        # ── Approved — update context, no message ────────────────────
        if etype == "approved":
            if trade_id and trade_id in self._pending:
                self._pending[trade_id].update({
                    "approved": True,
                    "reason": event.get("reason", "risk_check_passed"),
                })
            return

        # ── Rejected — cleanup pending, buffer for batch ─────────────
        if etype == "rejected":
            if trade_id:
                self._pending.pop(trade_id, None)
            self._pending_events.append(event)
            return

        # ── Executed — update context, buffer for batch ──────────────
        if etype == "executed":
            if trade_id and trade_id in self._pending:
                self._pending[trade_id].update({
                    "executed": True,
                    "qty": event.get("qty", 0),
                    "exec_price": event.get("price", 0.0),
                })
            self._pending_events.append(event)
            return

        # ── Position — buffer closed, silently cleanup opened ────────
        if etype == "position":
            status = event.get("status", "")

            if status == "opened":
                # Cleanup pending context, no message sent
                if trade_id:
                    self._pending.pop(trade_id, None)
                return

            if status == "closed":
                self._last_trade_ts = time.time()
                self._pending_events.append(event)
                return

    # ------------------------------------------------------------------
    # Batch flush
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        """Background task: drain _pending_events every batch_interval."""
        import httpx

        while self._running:
            await asyncio.sleep(self._batch_interval)
            if not self._pending_events:
                continue
            async with httpx.AsyncClient() as client:
                await self._flush(client)

    async def _flush(self, client: Any) -> None:
        """Drain the buffer, build grouped message, and send."""
        if not self._pending_events:
            return
        message = self._build_batch_message()
        self._pending_events.clear()
        chunks = self._split_message(message)
        for chunk in chunks:
            await self._send(client, chunk)

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    def _fmt_trade(self, pending: dict[str, Any]) -> str:
        """Mensaje consolidado de una operación completa (abierta)."""
        lines = ["<b>\U0001f514 NUEVA OPERACIÓN</b>"]

        # Señal
        lines.append(
            f'<b>Señal:</b> {pending["action"]} '
            f'{pending["symbol"]} @ <b>${pending["price"]:,.2f}</b>'
            f' — {pending["strategy"]}'
        )

        # Aprobación
        if pending.get("approved"):
            lines.append(
                f'<b>Aprobación:</b> \u2705 '
                f'{pending.get("reason", "risk_check_passed")}'
            )

        # Ejecución
        if pending.get("executed"):
            qty = float(pending["qty"])
            qty_s = f"{qty:,.4f}" if qty < 1 else f"{qty:,.2f}"
            lines.append(
                f'<b>Ejecución:</b> {pending["action"]} '
                f'{qty_s} {pending["symbol"]} '
                f'@ <b>${pending["exec_price"]:,.2f}</b>'
            )

        # Posición
        lines.append(
            f'<b>Posición:</b> ABIERTA'
            f' — Capital: <b>${pending.get("capital", 0):,.2f}</b>'
        )

        # ── Estado del Bot ──────────────────────────────────────────
        lines.extend(self._bot_stats_lines())

        return "\n".join(lines)

    def _fmt_rejected(
        self,
        event: dict[str, Any],
        pending: dict[str, Any],
    ) -> str:
        """Mensaje para una señal rechazada."""
        symbol = pending.get("symbol", event.get("symbol", "?"))
        action = pending.get("action", event.get("action", "?"))
        reason = event.get("reason", "risk_rejected")

        lines = ["<b>\u274c SEÑAL RECHAZADA</b>"]
        lines.append(
            f'<b>{action}</b> <code>{symbol}</code> — {reason}'
        )
        if pending.get("strategy"):
            lines.append(f'Estrategia: {pending["strategy"]}')
        return "\n".join(lines)

    def _fmt_close(self, event: dict[str, Any]) -> str:
        """Mensaje para el cierre de una posición."""
        symbol = event.get("symbol", "?")
        pnl = event.get("pnl", 0.0)
        capital = event.get("capital", 0.0)
        sign = "+" if pnl >= 0 else ""

        lines = ["<b>\U0001f4ca POSICIÓN CERRADA</b>"]
        lines.append(
            f'<code>{symbol}</code>'
            f' — PnL: <b>{sign}${pnl:,.2f}</b>'
            f' — Capital: <b>${capital:,.2f}</b>'
        )

        if self._portfolio:
            lines.append(
                f'<b>Posiciones restantes:</b> '
                f'{len(self._portfolio.positions)}'
            )

        lines.extend(self._bot_stats_lines())
        return "\n".join(lines)

    def _fmt_single(self, event: dict[str, Any]) -> str | None:
        """Fallback para eventos sin trade_id (legacy / reinicio)."""
        etype = event.get("type", "")
        symbol = event.get("symbol", "")
        action = event.get("action", "")

        if etype == "signal":
            price = event.get("price", 0.0)
            strategy = event.get("strategy", "?")
            return (
                f"\U0001f514 SEÑAL: <b>{action}</b> "
                f"<code>{symbol}</code> @ <b>${price:,.2f}</b>"
                f" — {strategy}"
            )
        if etype == "approved":
            return (
                f"\u2705 APROBADA: <b>{action}</b> "
                f"<code>{symbol}</code> — {event.get('reason', 'risk_check_passed')}"
            )
        if etype == "rejected":
            return (
                f"\u274c RECHAZADA: <b>{action}</b> "
                f"<code>{symbol}</code> — {event.get('reason', 'risk_rejected')}"
            )
        if etype == "executed":
            qty = float(event.get("qty", 0))
            qty_s = f"{qty:,.4f}" if qty < 1 else f"{qty:,.2f}"
            return (
                f"\U0001f4b1 EJECUTADA: <b>{action}</b> "
                f"{qty_s} <code>{symbol}</code> "
                f"@ <b>${event.get('price', 0):,.2f}</b>"
            )
        if etype == "position":
            status = event.get("status", "")
            capital = event.get("capital", 0.0)
            if status == "opened":
                return (
                    f"\U0001f4ca POSICIÓN ABIERTA: <code>{symbol}</code>"
                    f" — Capital: <b>${capital:,.2f}</b>"
                )
            if status == "closed":
                pnl = event.get("pnl", 0.0)
                sign = "+" if pnl >= 0 else ""
                return (
                    f"\U0001f4ca POSICIÓN CERRADA: <code>{symbol}</code>"
                    f" — PnL: <b>{sign}${pnl:,.2f}</b>"
                    f" — Capital: <b>${capital:,.2f}</b>"
                )
        return None

    # ------------------------------------------------------------------
    # Batch message builder
    # ------------------------------------------------------------------

    def _build_batch_message(self) -> str:
        """Build a grouped summary from _pending_events.

        Groups events by (type, symbol), builds per-type sections
        (Ejecuciones / Rechazos / Cierres), and appends bot stats footer.

        Returns:
            Formatted HTML message string, or empty string if no events.
        """
        events = self._pending_events
        if not events:
            return ""

        total = len(events)

        # Categorise events
        executed: list[dict] = []
        rejected_groups: dict[tuple[str, str], list[dict]] = {}
        closed: list[dict] = []

        for ev in events:
            etype = ev.get("type", "")
            symbol = ev.get("symbol", "?")

            if etype == "executed":
                executed.append(ev)
            elif etype == "rejected":
                reason = ev.get("reason", "risk_rejected")
                key = (symbol, reason)
                if key not in rejected_groups:
                    rejected_groups[key] = []
                rejected_groups[key].append(ev)
            elif etype == "position" and ev.get("status") == "closed":
                closed.append(ev)

        # Single-event: shorter format without section headers
        if total == 1:
            return self._single_event_line(
                executed, rejected_groups, closed,
            )

        # ── Multi-event: full grouped message ───────────────────────
        lines = ["<b>\U0001f4ca RESUMEN DEL \u00daLTIMO MINUTO</b>"]

        if executed:
            lines.append("")
            lines.append("<b>\u2705 Ejecuciones:</b>")
            for ev in executed:
                action = ev.get("action", "")
                symbol = ev.get("symbol", "?")
                qty = float(ev.get("qty", 0))
                qty_s = f"{qty:,.4f}" if qty < 1 else f"{qty:,.2f}"
                lines.append(
                    f'<b>{action}</b> {qty_s} <code>{symbol}</code>'
                    f' @ <b>${ev.get("price", 0):,.2f}</b>'
                )

        if rejected_groups:
            lines.append("")
            lines.append("<b>\u274c Rechazos:</b>")
            for (symbol, reason), evs in rejected_groups.items():
                count = len(evs)
                if count > 1:
                    lines.append(
                        f'{count}x <code>{symbol}</code>'
                        f' \u2014 {reason}'
                    )
                else:
                    action = evs[0].get("action", "")
                    lines.append(
                        f'<b>{action}</b> <code>{symbol}</code>'
                        f' \u2014 {reason}'
                    )

        if closed:
            lines.append("")
            lines.append("<b>\U0001f534 Cierres:</b>")
            for ev in closed:
                symbol = ev.get("symbol", "?")
                pnl = ev.get("pnl", 0.0)
                sign = "+" if pnl >= 0 else ""
                lines.append(
                    f'<code>{symbol}</code> \u2014 PnL:'
                    f' <b>{sign}${pnl:,.2f}</b>'
                )

        # Footer
        lines.append("")
        lines.append("\u2014\u2014\u2014")
        lines.extend(self._bot_stats_lines())

        return "\n".join(lines)

    def _single_event_line(
        self,
        executed: list[dict],
        rejected_groups: dict[tuple[str, str], list[dict]],
        closed: list[dict],
    ) -> str:
        """Format a single event message (no grouping needed)."""
        lines: list[str] = []

        if executed:
            ev = executed[0]
            action = ev.get("action", "")
            symbol = ev.get("symbol", "?")
            qty = float(ev.get("qty", 0))
            qty_s = f"{qty:,.4f}" if qty < 1 else f"{qty:,.2f}"
            lines.append(
                f'<b>{action}</b> {qty_s} <code>{symbol}</code>'
                f' @ <b>${ev.get("price", 0):,.2f}</b>'
            )
        elif rejected_groups:
            (symbol, reason), evs = next(iter(rejected_groups.items()))
            action = evs[0].get("action", "")
            lines.append(
                f'<b>{action}</b> <code>{symbol}</code>'
                f' \u2014 {reason}'
            )
        elif closed:
            ev = closed[0]
            symbol = ev.get("symbol", "?")
            pnl = ev.get("pnl", 0.0)
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f'<code>{symbol}</code> \u2014 PnL:'
                f' <b>{sign}${pnl:,.2f}</b>'
            )

        # Footer
        lines.append("")
        lines.append("\u2014\u2014\u2014")
        lines.extend(self._bot_stats_lines())

        return "\n".join(lines)

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list[str]:
        """Split a message into chunks <= max_len at newline boundaries.

        Args:
            text: The message to split.
            max_len: Maximum length per chunk (default 4000).

        Returns:
            List of message chunks, each <= max_len chars.
        """
        if not text or len(text) <= max_len:
            return [text] if text else []

        lines = text.split("\n")
        chunks: list[str] = []
        start = 0
        current_len = 0

        for i, line in enumerate(lines):
            line_len = len(line)
            # +1 for the newline separator if not first line in chunk
            sep = 1 if i > start else 0

            if current_len + sep + line_len > max_len and i > start:
                chunks.append("\n".join(lines[start:i]))
                start = i
                current_len = line_len
            else:
                current_len += sep + line_len

        if start < len(lines):
            chunks.append("\n".join(lines[start:]))

        return chunks

    # ------------------------------------------------------------------
    # Bot metrics
    # ------------------------------------------------------------------

    def _bot_stats_lines(self) -> list[str]:
        """Build the 'Estado del Bot' metric lines."""
        lines: list[str] = []
        lines.append("")
        lines.append("<b>\U0001f4ca Estado del Bot</b>")

        if self._portfolio:
            capital = self._portfolio.capital
            positions = len(self._portfolio.positions)
            drawdown = self._portfolio.get_drawdown()
            lines.append(f"<b>Capital:</b> ${capital:,.2f}")
            lines.append(f"<b>Posiciones abiertas:</b> {positions}")
            lines.append(f"<b>Drawdown:</b> {drawdown:.2%}")
        else:
            lines.append("<b>Capital:</b> N/D (sin portfolio)")

        if self._last_trade_ts:
            ago = self._fmt_ago(time.time() - self._last_trade_ts)
            lines.append(f"<b>Última operación:</b> {ago}")
        else:
            lines.append("<b>Última operación:</b> —")

        return lines

    @staticmethod
    def _fmt_ago(seconds: float) -> str:
        """Human-readable relative time."""
        if seconds < 5:
            return "Ahora"
        if seconds < 60:
            return f"Hace {int(seconds)}s"
        if seconds < 3600:
            return f"Hace {int(seconds // 60)}m"
        return f"Hace {int(seconds // 3600)}h"

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    async def _send(self, client: Any, message: str) -> None:
        """Send a formatted HTML message to Telegram."""
        if not message:
            return
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            resp = await client.post(url, json=payload, timeout=10)
            if not resp.is_success:
                logger.error(
                    "Telegram API error {}: {}",
                    resp.status_code,
                    resp.text[:300],
                )
        except Exception:
            logger.exception("Error al enviar mensaje Telegram")
