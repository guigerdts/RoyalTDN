"""Telegram notification alerts for the CellMesh bot.

Sends trade execution notifications via the Telegram Bot API.
Supports both synchronous (``requests``) and asynchronous
(``aiohttp``) transports where available.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


async def send_telegram_message(
    message: str,
    token: str = "",
    chat_id: str = "",
) -> None:
    """Send a text message via the Telegram Bot API.

    Uses ``loop.run_in_executor`` with ``requests.post`` to avoid
    blocking the event loop. Falls back gracefully if ``requests``
    is not installed or if the API call fails.

    Args:
        message: The plain-text message to send.
        token: Telegram bot token.
        chat_id: Target chat or channel ID.
    """
    if not token or not chat_id:
        logger.warning("Telegram token/chat_id no configurados — mensaje no enviado")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}

    def _post() -> None:
        try:
            import requests

            resp = requests.post(url, json=payload, timeout=10)
            if not resp.ok:
                logger.error(
                    "Telegram API error: {} — {}",
                    resp.status_code,
                    resp.text[:200],
                )
        except ImportError:
            logger.warning("requests no instalado — no se pudo enviar mensaje Telegram")
        except Exception:
            logger.exception("Error al enviar mensaje Telegram")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _post)


async def notify_trade(
    trade: dict[str, Any],
    token: str = "",
    chat_id: str = "",
) -> None:
    """Send a formatted trade notification to Telegram.

    The message includes the symbol, side, quantity, and price
    of the executed trade.

    Args:
        trade: Trade dict with keys ``symbol``, ``side``/``action``,
            ``qty``, and ``price``.
        token: Telegram bot token.
        chat_id: Target chat ID.
    """
    symbol = trade.get("symbol", "?")
    side = trade.get("side", trade.get("action", "?"))
    qty = trade.get("qty", 0)
    price = trade.get("price", 0.0)

    message = (
        f"\U0001f504 {symbol} {side} {qty} @ ${price:.2f}"
    )
    await send_telegram_message(message, token=token, chat_id=chat_id)
