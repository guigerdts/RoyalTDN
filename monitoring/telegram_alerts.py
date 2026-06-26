"""Telegram alerts — consolidados por trade + métricas del bot.

Acumula eventos de trading (signal → approved → executed → position)
agrupados por ``trade_id`` y envía un único mensaje por operación
con el detalle completo y el estado actual del portfolio.

Los eventos ``rejected`` se envían inmediatamente (el ciclo termina ahí).
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
    ) -> None:
        """Initialise the Telegram alert system.

        Args:
            bus: EventBus instance to subscribe to.
            bot_token: Telegram Bot API token.
            chat_id: Numeric chat or channel ID.
            portfolio: Optional Portfolio instance for live metrics.
        """
        self._token = bot_token
        self._chat_id = chat_id
        self._portfolio = portfolio
        self._queue = bus.subscribe()
        self._running = False

        # Acumulador: trade_id → dict con partes del mensaje
        self._pending: dict[str, dict[str, Any]] = {}
        self._last_trade_ts: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Run the alert loop — consume events from the bus queue."""
        import httpx

        self._running = True
        logger.info(
            "TelegramAlerts iniciado — chat_id={}",
            self._chat_id,
        )

        async with httpx.AsyncClient() as client:
            while self._running:
                try:
                    event = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                await self._handle_event(client, event)

    def stop(self) -> None:
        """Gracefully stop the alert loop."""
        self._running = False
        logger.info("TelegramAlerts detenido")

    # ------------------------------------------------------------------
    # Event router
    # ------------------------------------------------------------------

    async def _handle_event(self, client: Any, event: dict[str, Any]) -> None:
        """Route a single event to the accumulation or send logic."""
        etype = event.get("type", "")
        trade_id: str = event.get("trade_id", "") or ""

        if etype not in ("signal", "approved", "rejected", "executed", "position"):
            return

        # ── Signal (inicia acumulación) ──────────────────────────────
        if etype == "signal":
            if trade_id:
                self._pending[trade_id] = {
                    "symbol": event.get("symbol", "?"),
                    "action": event.get("action", ""),
                    "price": event.get("price", 0.0),
                    "strategy": event.get("strategy", "?"),
                }
            else:
                # Sin trade_id (legacy) — mensaje individual
                await self._send(client, self._fmt_single(event))
            return

        # ── Approved ─────────────────────────────────────────────────
        if etype == "approved":
            if trade_id and trade_id in self._pending:
                self._pending[trade_id].update({
                    "approved": True,
                    "reason": event.get("reason", "risk_check_passed"),
                })
            return

        # ── Rejected (cierre inmediato) ──────────────────────────────
        if etype == "rejected":
            pending = self._pending.pop(trade_id, {}) if trade_id else {}
            msg = self._fmt_rejected(event, pending)
            await self._send(client, msg)
            return

        # ── Executed ─────────────────────────────────────────────────
        if etype == "executed":
            if trade_id and trade_id in self._pending:
                self._pending[trade_id].update({
                    "executed": True,
                    "qty": event.get("qty", 0),
                    "exec_price": event.get("price", 0.0),
                })
            return

        # ── Position (cierre del ciclo) ──────────────────────────────
        if etype == "position":
            status = event.get("status", "")

            if not trade_id:
                await self._send(client, self._fmt_single(event))
                return

            if status == "opened":
                pending = self._pending.pop(trade_id, {})
                if pending:
                    pending["capital"] = event.get("capital", 0.0)
                    self._last_trade_ts = time.time()
                    msg = self._fmt_trade(pending)
                    await self._send(client, msg)

            elif status == "closed":
                self._last_trade_ts = time.time()
                msg = self._fmt_close(event)
                await self._send(client, msg)

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
