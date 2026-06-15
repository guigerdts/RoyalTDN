"""
RoyalTDN — Entry Point Principal (Fase 4+)

Arquitectura modular: DataIngestor + SMAStrategy + Orchestrator.

Comandos:
    check                Probar conexión Alpaca Paper
    run                  Ejecutar bot con arquitectura modular
    run-legacy           Ejecutar bot con polling REST (respaldo)
"""

import logging
import os
import sys

from dotenv import load_dotenv

from alpaca.trading.client import TradingClient

from royaltdn.orchestrator import Orchestrator

# ── Configuración ──────────────────────────────────────────────────────────

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SYMBOL = "SPY"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("royaltdn")


# ── Comando: check ─────────────────────────────────────────────────────────

def cmd_check():
    """Prueba la conexión con Alpaca Paper."""
    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    client = TradingClient(API_KEY, API_SECRET, paper=True)
    account = client.get_account()

    logger.info("=== Conexión Alpaca Paper exitosa ===")
    logger.info("  Estado:       %s", account.status.value)
    logger.info("  Capital:      $%.2f", float(account.equity))
    logger.info("  Poder compra: $%.2f", float(account.buying_power))
    logger.info("  PDT:          %s", account.pattern_day_trader)
    return account


# ── Comando: run ───────────────────────────────────────────────────────────

def cmd_run():
    """Arranca el bot con arquitectura modular (Fase 4)."""
    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("RoyalTDN — Arquitectura Modular (Fase 4)")
    logger.info("  Símbolo:     %s", SYMBOL)
    logger.info("  Estrategia:  SMA5/SMA20")
    logger.info("  Broker:      Alpaca Paper (IEX)")
    logger.info("  Redis:       %s", REDIS_URL)
    logger.info("  TimescaleDB: %s", "SÍ" if DATABASE_URL else "NO")
    logger.info("=" * 50)

    Orchestrator.run(
        api_key=API_KEY,
        secret_key=API_SECRET,
        redis_url=REDIS_URL,
        db_url=DATABASE_URL,
        symbol=SYMBOL,
    )


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print("Uso: python -m royaltdn <check|run|run-legacy>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "check":
        cmd_check()
    elif command == "run":
        cmd_run()
    elif command == "run-legacy":
        # Redirigir al módulo legacy
        from royaltdn.legacy_polling import main as legacy_main
        sys.argv = [sys.argv[0], *sys.argv[2:]] if len(sys.argv) > 2 else [sys.argv[0]]
        legacy_main()
    else:
        print(f"Comando desconocido: {command}")
        print("Usa: check | run | run-legacy")
        sys.exit(1)


if __name__ == "__main__":
    main()
