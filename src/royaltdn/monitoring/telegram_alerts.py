"""Telegram alerts — niveles de verbosidad, umbrales, event-driven + batch.

Comportamiento por nivel:

- **silent**: Solo errores críticos. Sin notificaciones de trading.
- **normal**: Entry/exit al instante + resumen horario (si cambió equity > X%).
- **verbose**: Entry/exit al instante + resumen cada 15 min (si cambió equity > X%).
- **debug**: Todo lo anterior + eventos de señal/rechazo en tiempo real.

El resumen periódico usa threshold gating: si equity no varió más del umbral
configurado y no hubo eventos nuevos, se salta el envío (sin ruido repetitivo).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

# ── Niveles de verbosidad ──────────────────────────────────────────────────
LEVEL_SILENT = "silent"
LEVEL_NORMAL = "normal"
LEVEL_VERBOSE = "verbose"
LEVEL_DEBUG = "debug"
VALID_LEVELS = (LEVEL_SILENT, LEVEL_NORMAL, LEVEL_VERBOSE, LEVEL_DEBUG)

# Intervalos de resumen por nivel (segundos)
SUMMARY_INTERVAL: dict[str, int] = {
    LEVEL_SILENT: 0,       # sin resumen periódico
    LEVEL_NORMAL: 3600,    # 1 hora
    LEVEL_VERBOSE: 900,    # 15 min
    LEVEL_DEBUG: 300,      # 5 min
}


class TelegramAlerts:
    """Telegram notifier con niveles, umbrales y buffer batch.

    Args:
        bus: EventBus para suscribirse.
        bot_token: Token de la API de Telegram.
        chat_id: Chat ID numérico.
        portfolio: Portfolio opcional para métricas.
        batch_interval: Segundos entre flushes batch (default 60, legacy).
        level: Nivel de verbosidad (silent|normal|verbose|debug).
        equity_threshold_pct: % mínimo de cambio en equity para enviar resumen.
        summary_interval: Segundos entre resúmenes periódicos (0 = default por nivel).
    """

    def __init__(
        self,
        bus: Any,
        bot_token: str,
        chat_id: str,
        portfolio: Any = None,
        batch_interval: int = 60,
        level: str = LEVEL_NORMAL,
        equity_threshold_pct: float = 1.0,
        summary_interval: int = 0,
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._portfolio = portfolio
        self._queue = bus.subscribe()
        self._running = False

        # ── Nivel de verbosidad ───────────────────────────────────────
        self._level = level if level in VALID_LEVELS else LEVEL_NORMAL

        # ── Threshold gating ──────────────────────────────────────────
        self._equity_threshold_pct = max(equity_threshold_pct, 0.0)
        self._last_summary_equity: float = 0.0
        self._last_summary_ts: float = 0.0
        self._events_since_last_summary: int = 0

        # ── Intervalo de resumen ──────────────────────────────────────
        self._summary_interval = (
            summary_interval if summary_interval > 0
            else SUMMARY_INTERVAL.get(self._level, 900)
        )

        # ── Acumuladores (contexto de trade) ──────────────────────────
        self._pending: dict[str, dict[str, Any]] = {}
        self._last_trade_ts: float = 0.0

        # ── Batch buffer ──────────────────────────────────────────────
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
            "TelegramAlerts iniciado — nivel={}, chat_id={}",
            self._level, self._chat_id,
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
        """Gracefully stop — flush remaining events first."""
        self._running = False
        import httpx

        async with httpx.AsyncClient() as client:
            await self._flush(client)
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        logger.info("TelegramAlerts detenido")

    # ------------------------------------------------------------------
    # Event router (con niveles + envío inmediato)
    # ------------------------------------------------------------------

    async def _handle_event(self, client: Any, event: dict[str, Any]) -> None:
        """Route event según nivel: inmediato o buffer."""
        etype = event.get("type", "")
        trade_id: str = event.get("trade_id", "") or ""

        if etype not in ("signal", "approved", "rejected", "executed", "position"):
            return

        # ── Signal — store context (nunca se envía) ───────────────────
        if etype == "signal":
            if trade_id:
                self._pending[trade_id] = {
                    "symbol": event.get("symbol", "?"),
                    "action": event.get("action", ""),
                    "price": event.get("price", 0.0),
                    "strategy": event.get("strategy", "?"),
                }
            return

        # ── Approved — update context (nunca se envía) ────────────────
        if etype == "approved":
            if trade_id and trade_id in self._pending:
                self._pending[trade_id].update({
                    "approved": True,
                    "reason": event.get("reason", "risk_check_passed"),
                })
            return

        # ── Rejected — buffer (en debug se envía también inmediato) ──
        if etype == "rejected":
            if trade_id:
                self._pending.pop(trade_id, None)
            self._pending_events.append(event)
            self._events_since_last_summary += 1

            if self._level == LEVEL_DEBUG:
                msg = self._fmt_single(event)
                if msg:
                    await self._send(client, msg)
            return

        # ── Executed — ENVÍO INMEDIATO (excepto silent) ──────────────
        if etype == "executed":
            if trade_id and trade_id in self._pending:
                self._pending[trade_id].update({
                    "executed": True,
                    "qty": event.get("qty", 0),
                    "exec_price": event.get("price", 0.0),
                })
            self._pending_events.append(event)
            self._events_since_last_summary += 1

            if self._level not in (LEVEL_SILENT,):
                msg = self._fmt_entry_immediate(event)
                await self._send(client, msg)
            return

        # ── Position — ENVÍO INMEDIATO en closed (excepto silent) ────
        if etype == "position":
            status = event.get("status", "")

            if status == "opened":
                if trade_id:
                    self._pending.pop(trade_id, None)
                return

            if status == "closed":
                self._last_trade_ts = time.time()
                self._pending_events.append(event)
                self._events_since_last_summary += 1

                if self._level not in (LEVEL_SILENT,):
                    msg = self._fmt_exit_immediate(event)
                    await self._send(client, msg)
                return

    # ------------------------------------------------------------------
    # Periodic flush (con threshold gating)
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        """Background task: periodic summary with threshold gating."""
        import httpx

        while self._running:
            interval = self._summary_interval
            if interval <= 0:
                await asyncio.sleep(60)
                continue

            await asyncio.sleep(interval)
            if self._level == LEVEL_SILENT:
                continue

            # ── Threshold gating ─────────────────────────────────────
            threshold = self._equity_threshold_pct
            equity = self._get_equity()
            equity_change_pct = 0.0
            if self._last_summary_equity > 0 and equity > 0:
                equity_change_pct = abs(equity - self._last_summary_equity) / self._last_summary_equity * 100

            has_events = self._events_since_last_summary > 0
            equity_moved = equity_change_pct >= threshold

            if not has_events and not equity_moved:
                continue  # threshold gate: nada cambió, no enviamos

            # ── Build and send summary ───────────────────────────────
            async with httpx.AsyncClient() as client:
                msg = self._build_summary_message()
                if msg:
                    chunks = self._split_message(msg)
                    for chunk in chunks:
                        await self._send(client, chunk)

                # Flush pending events + reset counter
                self._pending_events.clear()
                self._events_since_last_summary = 0

            if equity > 0:
                self._last_summary_equity = equity
            self._last_summary_ts = time.time()

    async def _flush(self, client: Any) -> None:
        """Legacy flush — drain buffer and send (used at shutdown)."""
        if not self._pending_events:
            return
        message = self._build_batch_message()
        self._pending_events.clear()
        chunks = self._split_message(message)
        for chunk in chunks:
            await self._send(client, chunk)

    # ------------------------------------------------------------------
    # Immediate formatters (event-driven)
    # ------------------------------------------------------------------

    def _fmt_entry_immediate(self, event: dict[str, Any]) -> str:
        """Mensaje inmediato para nueva operación ejecutada."""
        symbol = event.get("symbol", "?")
        action = event.get("action", "")
        qty = float(event.get("qty", 0))
        price = float(event.get("price", 0))
        qty_s = f"{qty:,.4f}" if qty < 1 else f"{qty:,.2f}"

        lines = [
            f"<b>\U0001f7e2 ENTRADA: {action}</b> {qty_s} <code>{symbol}</code>",
            f"Precio: <b>${price:,.2f}</b>",
        ]
        lines.extend(self._bot_stats_lines())
        return "\n".join(lines)

    def _fmt_exit_immediate(self, event: dict[str, Any]) -> str:
        """Mensaje inmediato para cierre de posición."""
        symbol = event.get("symbol", "?")
        pnl = event.get("pnl", 0.0)
        capital = event.get("capital", 0.0)
        sign = "+" if pnl >= 0 else ""

        lines = [
            f"<b>\U0001f534 SALIDA: <code>{symbol}</code></b>",
            f"PnL: <b>{sign}${pnl:,.2f}</b>  |  Capital: <b>${capital:,.2f}</b>",
        ]
        lines.extend(self._bot_stats_lines())
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Periodic summary builder (con threshold gating)
    # ------------------------------------------------------------------

    def _build_summary_message(self) -> str:
        """Build a periodic status summary from pending events + bot stats.

        Returns:
            Formatted HTML message, or empty if nothing to report.
        """
        events = self._pending_events
        equity = self._get_equity()
        equity_change = ""
        if self._last_summary_equity > 0 and equity > 0:
            pct = (equity - self._last_summary_equity) / self._last_summary_equity * 100
            sign = "+" if pct >= 0 else ""
            equity_change = f" ({sign}{pct:.2f}%)"

        # Build header
        elapsed = ""
        if self._last_summary_ts > 0:
            ago = time.time() - self._last_summary_ts
            elapsed = f" ({self._fmt_ago(ago)})"

        label = self._summary_label()
        lines = [f"<b>\U0001f4ca {label}{elapsed}</b>"]

        if equity > 0:
            lines.append(f"<b>Capital:</b> ${equity:,.2f}{equity_change}")

        if self._portfolio:
            positions = len(self._portfolio.positions)
            drawdown = self._portfolio.get_drawdown()
            lines.append(f"<b>Posiciones:</b> {positions}  |  "
                         f"<b>Drawdown:</b> {drawdown:.2%}")

        # ── Agrupar eventos del período ──────────────────────────────
        rejected_groups: dict[tuple[str, str], list[dict]] = {}
        closed_count = 0

        for ev in events:
            etype = ev.get("type", "")
            symbol = ev.get("symbol", "?")

            if etype == "rejected":
                reason = ev.get("reason", "risk_rejected")
                key = (symbol, reason)
                if key not in rejected_groups:
                    rejected_groups[key] = []
                rejected_groups[key].append(ev)
            elif etype == "position" and ev.get("status") == "closed":
                closed_count += 1

        if rejected_groups:
            lines.append("")
            lines.append(f"<b>\u274c Rechazos ({sum(len(v) for v in rejected_groups.values())}):</b>")
            for (symbol, reason), evs in rejected_groups.items():
                count = len(evs)
                prefix = f"{count}x " if count > 1 else ""
                lines.append(f" {prefix}<code>{symbol}</code> \u2014 {reason}")

        if closed_count > 0:
            lines.append("")
            lines.append(f"<b>\U0001f534 Salidas:</b> {closed_count} posiciones cerradas")

        # Footer stats
        lines.append("")
        lines.append("\u2014\u2014\u2014")
        lines.extend(self._bot_stats_lines())

        return "\n".join(lines)

    @staticmethod
    def _summary_label() -> str:
        """Human label for the summary period (refreshed each call)."""
        hour = time.localtime().tm_hour
        if hour < 6:
            return "Resumen nocturno"
        if hour < 12:
            return "Resumen matutino"
        if hour < 18:
            return "Resumen vespertino"
        return "Resumen nocturno"

    # ------------------------------------------------------------------
    # Legacy message builders (mantenidos para tests compat)
    # ------------------------------------------------------------------

    def _fmt_trade(self, pending: dict[str, Any]) -> str:
        """Mensaje consolidado de una operación completa (abierta)."""
        lines = ["<b>\U0001f514 NUEVA OPERACIÓN</b>"]

        lines.append(
            f'<b>Señal:</b> {pending["action"]} '
            f'{pending["symbol"]} @ <b>${pending["price"]:,.2f}</b>'
            f' — {pending["strategy"]}'
        )

        if pending.get("approved"):
            lines.append(
                f'<b>Aprobación:</b> \u2705 '
                f'{pending.get("reason", "risk_check_passed")}'
            )

        if pending.get("executed"):
            qty = float(pending["qty"])
            qty_s = f"{qty:,.4f}" if qty < 1 else f"{qty:,.2f}"
            lines.append(
                f'<b>Ejecución:</b> {pending["action"]} '
                f'{qty_s} {pending["symbol"]} '
                f'@ <b>${pending["exec_price"]:,.2f}</b>'
            )

        lines.append(
            f'<b>Posición:</b> ABIERTA'
            f' — Capital: <b>${pending.get("capital", 0):,.2f}</b>'
        )

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
    # Legacy batch message builder (mantenido para tests compat)
    # ------------------------------------------------------------------

    def _build_batch_message(self) -> str:
        """Build a grouped summary from _pending_events (legacy).

        Mantenido para compatibilidad con tests existentes.
        """
        events = self._pending_events
        if not events:
            return ""

        total = len(events)

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

        if total == 1:
            return self._single_event_line(
                executed, rejected_groups, closed,
            )

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

    def _get_equity(self) -> float:
        """Get current equity from portfolio, or 0 if unavailable."""
        if self._portfolio:
            try:
                return self._portfolio.capital
            except Exception:
                return 0.0
        return 0.0

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
