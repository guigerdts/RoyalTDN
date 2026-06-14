"""
RoyalTDN — Sistema de Alertas (Fase 2)

Basado en documento 04_ruta_implementacion_fase0_fase1.md, sección 4.1.6.

Soporta:
- Telegram (usando python-telegram-bot)

Variables de entorno requeridas (.env):
  TELEGRAM_BOT_TOKEN=<token_de_bot>
  TELEGRAM_CHAT_ID=<tu_chat_id>
"""

import logging
import os

logger = logging.getLogger("royaltdn.alerts")


def send_telegram_message(message: str) -> bool:
    """
    Envía un mensaje de Telegram al chat configurado.

    Args:
        message: Texto del mensaje a enviar.

    Returns:
        bool: True si se envió correctamente, False si falló o no está configurado.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.debug("Telegram no configurado — salteando alerta")
        return False

    try:
        # Lazy import para no romper si no está instalado
        import asyncio

        from telegram import Bot

        bot = Bot(token=token)

        async def _send():
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")

        asyncio.run(_send())
        logger.info(f"📨 Telegram enviado: {message[:60]}...")
        return True

    except ImportError:
        logger.warning("python-telegram-bot no instalado — salteando alerta")
        return False
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")
        return False


def notify_entry(symbol: str, side: str, qty: int, price: float) -> None:
    """Notifica entrada en una posición."""
    send_telegram_message(
        f"🤖 <b>ENTRADA</b>\n"
        f"{side.upper()} {qty} {symbol} @ ${price:.2f}"
    )


def notify_exit(symbol: str, side: str, qty: int, price: float, pnl: float) -> None:
    """Notifica salida de una posición con P&L."""
    emoji = "✅" if pnl >= 0 else "❌"
    send_telegram_message(
        f"{emoji} <b>SALIDA</b>\n"
        f"{side.upper()} {qty} {symbol} @ ${price:.2f} | "
        f"P&L: ${pnl:.2f}"
    )


def notify_kill_switch(reason: str) -> None:
    """Notifica activación de kill switch."""
    send_telegram_message(
        f"🚨 <b>KILL SWITCH ACTIVADO</b>\n{reason}"
    )


def notify_error(error: str) -> None:
    """Notifica error crítico en el bot."""
    send_telegram_message(
        f"⚠️ <b>ERROR</b>\n{error}"
    )
