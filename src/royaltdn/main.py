"""
RoyalTDN — Entry Point Principal (Fase 4+)

Arquitectura modular: DataIngestor + SMAStrategy + Orchestrator.

Comandos:
    check                Probar conexión Alpaca Paper
    run                  Iniciar bot + consola interactiva
    status               Mostrar estado actual del bot
    logs                 Mostrar últimas líneas de log
    pause                Pausar el bot
    resume               Reanudar el bot
    scanner              Disparar scanner manual
"""

import os
import sys
import threading

from dotenv import load_dotenv
from loguru import logger

from alpaca.trading.client import TradingClient

from royaltdn.frontend.console.loguru_config import setup_logging
from royaltdn.orchestrator import Orchestrator

# ── Configuración ──────────────────────────────────────────────────────────

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SYMBOL = "SPY"


# ── Comando: check ─────────────────────────────────────────────────────────

def cmd_check():
    """Prueba la conexión con Alpaca Paper."""
    setup_logging()
    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    client = TradingClient(API_KEY, API_SECRET, paper=True)
    account = client.get_account()

    logger.info("=== Conexión Alpaca Paper exitosa ===")
    logger.info("  Estado:       {}", account.status.value)
    logger.info("  Capital:      ${:.2f}", float(account.equity))
    logger.info("  Poder compra: ${:.2f}", float(account.buying_power))
    logger.info("  PDT:          {}", account.pattern_day_trader)
    return account


# ── Comando: status ────────────────────────────────────────────────────────

def cmd_status():
    """One-shot dashboard render from JSON files."""
    from rich import print as rprint
    from royaltdn.frontend.console.components.state import StateLoader
    from royaltdn.frontend.console.log_handler import LogBuffer
    from royaltdn.frontend.console.screens.dashboard import render_dashboard

    loader = StateLoader()
    state = loader.load_all()
    log_buffer = LogBuffer()
    layout = render_dashboard(state, log_buffer)
    rprint(layout)

    bot_status = state.get("status", {}).get("bot_status", "OFFLINE")
    if bot_status == "OFFLINE":
        sys.exit(1)


# ── Comando: logs ──────────────────────────────────────────────────────────

def cmd_logs():
    """Show last 50 lines of bot.log with syntax highlighting."""
    from rich.console import Console
    from pathlib import Path

    log_file = Path("logs/bot.log")
    if not log_file.exists():
        print("No hay logs aún.")
        return

    console = Console()
    lines = log_file.read_text().splitlines()
    for line in lines[-50:]:
        styled = line
        if "CRITICAL" in line:
            styled = f"[bold red]{line}[/]"
        elif "ERROR" in line:
            styled = f"[red]{line}[/]"
        elif "WARNING" in line or "WARN" in line:
            styled = f"[yellow]{line}[/]"
        elif "INFO" in line:
            styled = f"[green]{line}[/]"
        elif "DEBUG" in line:
            styled = f"[dim]{line}[/]"
        console.print(styled)


# ── Comando: pause ─────────────────────────────────────────────────────────

def cmd_pause():
    """Send pause signal to the bot."""
    from royaltdn.frontend.console.commands import pause_bot
    pause_bot()
    print("✅ Señal de pausa enviada. El bot se pausará en el próximo ciclo.")


# ── Comando: resume ────────────────────────────────────────────────────────

def cmd_resume():
    """Send resume signal to the bot."""
    from royaltdn.frontend.console.commands import resume_bot
    resume_bot()
    print("✅ Señal de reanudación enviada.")


# ── Comando: scanner ───────────────────────────────────────────────────────

def cmd_scanner():
    """Trigger scanner manually."""
    from royaltdn.frontend.console.commands import trigger_scanner
    trigger_scanner()
    print("✅ Scanner disparado. Los resultados aparecerán en el próximo ciclo.")


# ── Comando: run ───────────────────────────────────────────────────────────

def cmd_run():
    """Arranca el bot con arquitectura modular + consola interactiva."""
    setup_logging()
    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("RoyalTDN — Arquitectura Modular (Fase 4)")
    logger.info("  Símbolo:     {}", SYMBOL)
    logger.info("  Estrategia:  SMA5/SMA20")
    logger.info("  Broker:      Alpaca Paper (IEX)")
    logger.info("  Redis:       {}", REDIS_URL)
    logger.info("  TimescaleDB: {}", "SÍ" if DATABASE_URL else "NO")
    logger.info("=" * 50)

    from royaltdn.frontend.textual import RoyalTDNApp

    orch = Orchestrator(
        api_key=API_KEY,
        secret_key=API_SECRET,
        redis_url=REDIS_URL,
        db_url=DATABASE_URL,
        symbol=SYMBOL,
    )

    t = threading.Thread(target=orch.start, daemon=True)
    t.start()

    try:
        RoyalTDNApp().run()
    finally:
        orch.stop()
        logger.info("🛑 Bot detenido.")


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print("Uso: python -m royaltdn <comando>")
        print("")
        print("Comandos:")
        print("  run         Iniciar bot + consola interactiva")
        print("  status      Mostrar estado actual del bot")
        print("  logs        Mostrar últimas líneas de log")
        print("  pause       Pausar el bot")
        print("  resume      Reanudar el bot")
        print("  scanner     Disparar scanner manual")
        print("  check       Verificar configuración")
        sys.exit(1)

    cmd = sys.argv[1]
    commands = {
        "run": cmd_run,
        "status": cmd_status,
        "logs": cmd_logs,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "scanner": cmd_scanner,
        "check": cmd_check,
    }

    if cmd not in commands:
        print(f"Comando desconocido: {cmd}")
        print("Use: python -m royaltdn <comando>")
        sys.exit(1)

    commands[cmd]()


if __name__ == "__main__":
    main()
