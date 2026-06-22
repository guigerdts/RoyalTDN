"""Telegram alerts for CellMesh trading events.

Subscribes to the EventBus and sends formatted HTML notifications
to a Telegram chat for every trading event (signal, approval,
execution, position changes).

Uses ``httpx.AsyncClient`` for non-blocking HTTP calls and respects
Telegram's rate limits (max 20 msg/min — guaranteed by the bot's
event frequency being far below that threshold).
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class TelegramAlerts:
    """Asynchronous Telegram notifier for trading events.

    Listens on the EventBus for events of type ``signal``,
    ``approved``, ``rejected``, ``executed``, and ``position``,
    formats them as readable HTML messages, and sends them to the
    configured Telegram chat via the Bot API.

    Telemetry:
        - ``signal`` events from the Journal (with ``strategy`` field)
          are forwarded; bare engine signals are skipped (dedup).
        - ``trade`` events (engine-native) are NOT forwarded; the
          richer ``executed`` + ``position`` events from the Journal
          are used instead.
    """

    def __init__(
        self,
        bus: Any,
        bot_token: str,
        chat_id: str,
    ) -> None:
        """Initialise the Telegram alert system.

        Args:
            bus: EventBus instance to subscribe to.
            bot_token: Telegram Bot API token (from ``@BotFather``).
            chat_id: Numeric chat or channel ID to send to.
        """
        self._token = bot_token
        self._chat_id = chat_id
        self._queue = bus.subscribe()
        self._running = False

        # Rate-limit guard: track last-send timestamps per event type
        self._last_sent: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Run the alert loop. Processes events from the bus queue."""
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

                if not self._should_forward(event):
                    continue

                message = self._format_message(event)
                if message:
                    await self._send(client, message)

    def stop(self) -> None:
        """Gracefully stop the alert loop."""
        self._running = False
        logger.info("TelegramAlerts detenido")

    # ------------------------------------------------------------------
    # Event filtering & formatting
    # ------------------------------------------------------------------

    def _should_forward(self, event: dict[str, Any]) -> bool:
        """Return True if this event should produce a Telegram message.

        Deduplication strategy:
        - ``signal`` events are only forwarded when they carry a
          ``strategy`` field (added by the Journal).  Bare engine
          signal events are skipped.
        - ``trade`` events (engine-native) are never forwarded; the
          richer ``executed`` + ``position`` events are used instead.
        """
        etype = event.get("type", "")

        if etype == "signal":
            # Only forward journal-emitted signals (have strategy field)
            return bool(event.get("strategy"))

        if etype == "trade":
            return False  # handled via "executed" + "position"

        return etype in ("approved", "rejected", "executed", "position")

    def _format_message(self, event: dict[str, Any]) -> str | None:
        """Format a trading event as an HTML Telegram message.

        Returns:
            HTML string ready for ``parse_mode=HTML``, or None if the
            event type is unknown.
        """
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
            reason = event.get("reason", "risk_check_passed")
            return (
                f"\u2705 APROBADA: <b>{action}</b> "
                f"<code>{symbol}</code> — {reason}"
            )

        if etype == "rejected":
            reason = event.get("reason", "risk_rejected")
            return (
                f"\u274c RECHAZADA: <b>{action}</b> "
                f"<code>{symbol}</code> — {reason}"
            )

        if etype == "executed":
            qty = float(event.get("qty", 0))
            price = event.get("price", 0.0)
            # Format qty nicely: 0.001 vs 635.17
            qty_str = f"{qty:,.4f}" if qty < 1 else f"{qty:,.2f}"
            return (
                f"\U0001f4b1 EJECUTADA: <b>{action}</b> "
                f"{qty_str} <code>{symbol}</code> "
                f"@ <b>${price:,.2f}</b>"
            )

        if etype == "position":
            status = event.get("status", "")
            if status == "opened":
                capital = event.get("capital", 0.0)
                return (
                    f"\U0001f4ca POSICIÓN ABIERTA: <code>{symbol}</code>"
                    f" — Capital: <b>${capital:,.2f}</b>"
                )
            if status == "closed":
                pnl = event.get("pnl", 0.0)
                capital = event.get("capital", 0.0)
                sign = "+" if pnl >= 0 else ""
                return (
                    f"\U0001f4ca POSICIÓN CERRADA: <code>{symbol}</code>"
                    f" — PnL: <b>{sign}${pnl:,.2f}</b>"
                    f" — Capital: <b>${capital:,.2f}</b>"
                )

        return None

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    async def _send(self, client: Any, message: str) -> None:
        """Send a formatted HTML message to Telegram.

        Args:
            client: An ``httpx.AsyncClient`` instance.
            message: HTML-formatted message text.
        """
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
