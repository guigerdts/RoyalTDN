"""
RoyalTDN — Sistema de Alertas (Fase 2)

Soporta:
- Telegram (vía Bot API con httpx)

Variables de entorno requeridas (.env):
  TELEGRAM_BOT_TOKEN=<token_de_bot>
  TELEGRAM_CHAT_ID=<tu_chat_id>
"""

import asyncio
import os
from typing import Optional

from loguru import logger
import httpx

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


async def send_telegram_message_async(message: str) -> bool:
    """
    Versión asíncrona: envía un mensaje de Telegram.
    Usar con `await` desde código async.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.debug("Telegram no configurado — salteando alerta")
        return False

    url = TELEGRAM_API_BASE.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        logger.info("📨 Telegram enviado: {}...", message[:60])
        return True
    except Exception as e:
        logger.error("Error enviando Telegram: {}", e)
        return False


def send_telegram_message(message: str) -> bool:
    """
    Versión sincrónica (compatible con código sync y async).

    - Si NO hay un event loop corriendo: usa asyncio.run() (seguro).
    - Si SÍ hay un event loop corriendo: advierte que uses la versión async.
    """
    try:
        asyncio.get_running_loop()
        logger.warning(
            "send_telegram_message() llamado desde un event loop activo. "
            "Usa 'await send_telegram_message_async()' en su lugar."
        )
        return False
    except RuntimeError:
        # No hay loop corriendo — safe to use asyncio.run()
        pass

    try:
        return asyncio.run(send_telegram_message_async(message))
    except Exception as e:
        logger.error("Error en send_telegram_message: {}", e)
        return False


async def notify_entry(symbol: str, side: str, qty: int, price: float) -> None:
    """Notifica entrada en una posición."""
    await send_telegram_message_async(
        f"🤖 <b>ENTRADA</b>\n"
        f"{side.upper()} {qty} {symbol} @ ${price:.2f}"
    )


async def notify_exit(symbol: str, side: str, qty: int, price: float, pnl: float) -> None:
    """Notifica salida de una posición con P&L."""
    emoji = "✅" if pnl >= 0 else "❌"
    await send_telegram_message_async(
        f"{emoji} <b>SALIDA</b>\n"
        f"{side.upper()} {qty} {symbol} @ ${price:.2f} | "
        f"P&L: ${pnl:.2f}"
    )


async def notify_kill_switch(reason: str) -> None:
    """Notifica activación de kill switch."""
    await send_telegram_message_async(
        f"🚨 <b>KILL SWITCH ACTIVADO</b>\n{reason}"
    )


async def notify_error(error: str) -> None:
    """Notifica error crítico en el bot."""
    await send_telegram_message_async(
        f"\u26a0\ufe0f <b>ERROR</b>\n{error}"
    )


async def notify_scanner_entry(symbol: str, action: str, qty: int, price: float, strategy: str = "scanner") -> None:
    """Notifica ejecución de una señal del Scanner."""
    await send_telegram_message_async(
        f"\U0001f514 <b>SCANNER: {action.upper()}</b>\n"
        f"{action.upper()} {qty} {symbol} @ ${price:.2f} ({strategy})"
    )


async def notify_scanner_rejection(symbol: str, reason: str) -> None:
    """Notifica que una señal del Scanner fue rechazada."""
    await send_telegram_message_async(
        f"\u26a0\ufe0f <b>Scanner:</b> se\u00f1al rechazada para {symbol} \u2014 {reason}"
    )