#!/usr/bin/env python3
"""CellMesh Crypto Bot — Entry Point"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Add src/ to sys.path for development runs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from royaltdn.core.bus import EventBus
from royaltdn.core.clock import RealClock
from royaltdn.core.engine import EventEngine
from royaltdn.core.journal import Journal
from royaltdn.core.registry import CellRegistry
from royaltdn.core.trade_tracker import TradeTracker
from royaltdn.inference.engine import InferenceEngine
from royaltdn.cells.loader import load_cells
from royaltdn.cells.base import Cell
from royaltdn.risk.portfolio import Portfolio
from royaltdn.risk.manager import RiskManager
from royaltdn.execution.paper_broker import PaperBroker


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the bot entry point."""
    parser = argparse.ArgumentParser(description="CellMesh Crypto Bot")
    parser.add_argument(
        "--optimize", action="store_true",
        help="Enable periodic strategy optimization",
    )
    return parser.parse_args()


async def _optimization_scheduler(
    interval_days: int = 30,
    metric: str = "sharpe",
    trials: int = 100,
) -> None:
    """Periodic optimization background task.

    Runs ``scripts/optimize.py`` at the configured interval.
    Optimization is spawned as a subprocess to avoid blocking
    the bot's event loop.

    Args:
        interval_days: Days between optimization runs (default 30).
        metric: Objective metric to optimize (default ``"sharpe"``).
        trials: Number of Optuna trials per strategy (default 100).
    """
    logger.info("Scheduler de optimizacion iniciado — cada {} dia(s)", interval_days)

    while True:
        next_run = datetime.now(timezone.utc) + timedelta(days=interval_days)
        logger.info("Proxima optimizacion programada para {}", next_run.isoformat())

        # Sleep until the next scheduled run
        await asyncio.sleep(interval_days * 86400)

        logger.info("Iniciando optimizacion periodica programada...")
        try:
            script_path = Path(__file__).parent / "scripts" / "optimize.py"
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(script_path),
                "--strategy", "all",
                "--trials", str(trials),
                "--metric", metric,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=86400,  # 24h max per run
            )
            if proc.returncode == 0:
                logger.info("Optimizacion periodica completada exitosamente")
                if stdout:
                    logger.info("Optimize output:\n{}", stdout.decode("utf-8", errors="replace"))
            else:
                logger.error("Optimizacion periodica fallo (codigo {})", proc.returncode)
                if stderr:
                    logger.error("Optimize stderr:\n{}", stderr.decode("utf-8", errors="replace"))
        except asyncio.TimeoutError:
            logger.error("Optimizacion periodica excedio el tiempo limite (24h)")
            if proc:
                proc.kill()
        except Exception as exc:
            logger.exception("Error en optimizacion periodica: {}", exc)


async def main():
    args = parse_args()

    # Cargar config
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Inicializar componentes
    bus = EventBus()
    clock = RealClock()
    inference_engine = InferenceEngine()
    registry = CellRegistry()

    # Portfolio y Risk
    portfolio = Portfolio(initial_capital=config["initial_capital"])
    risk_manager = RiskManager(
        portfolio,
        max_positions=config["max_positions"],
        max_drawdown=config["max_drawdown"],
        config_path=config_path,
    )

    # Broker
    broker_type = config.get("broker", "paper")
    if broker_type == "binance":
        try:
            from execution.binance_broker import BinanceBroker
            api_key = os.getenv("BINANCE_API_KEY", "")
            api_secret = os.getenv("BINANCE_SECRET_KEY", "")
            broker = BinanceBroker(api_key, api_secret, testnet=config.get("testnet", True))
        except Exception as e:
            logger.warning("Binance broker no disponible ({}), usando paper", e)
            broker = PaperBroker(initial_capital=config["initial_capital"])
    else:
        broker = PaperBroker(initial_capital=config["initial_capital"])
    
    broker.set_bus(bus)

    # Journal estructurado
    journal = Journal(log_path="logs/trading.log", bus=bus)

    # Engine
    trade_tracker = TradeTracker()
    engine = EventEngine(clock, bus, risk_manager, broker, journal=journal, trade_tracker=trade_tracker)

    # Cargar celulas desde YAML
    strategies_dir = Path(__file__).parent / config["strategies_dir"]
    cells = load_cells(str(strategies_dir), inference_engine)
    for cell in cells:
        engine.register(cell)
        registry.register(cell)
        logger.info("Celula registrada: {} ({})", cell.name, cell.symbol)

    logger.info("CellMesh iniciado — {} celulas, {} simbolos, broker={}",
                len(cells), len(config["symbols"]), broker_type)

    # Iniciar hot-reload watcher (siempre activo)
    from core.hot_reload import HotReloader
    reloader = HotReloader(
        strategies_dir=str(strategies_dir),
        engine=engine,
        inference_engine=inference_engine,
        poll_interval=60,
    )
    asyncio.create_task(reloader.watch())

    # Iniciar feed de datos
    from data.binance_feed import BinanceFeed
    feed = BinanceFeed(config["symbols"], bus)
    asyncio.create_task(feed.start())

    # Iniciar dashboard
    from royaltdn.monitoring.dashboard import Dashboard
    dashboard = Dashboard(portfolio, trade_tracker, engine)
    asyncio.create_task(dashboard.run())

    # Iniciar alertas Telegram (si configuradas)
    telegram_alerts = None
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if telegram_token and telegram_chat_id:
        from royaltdn.monitoring.telegram_alerts import TelegramAlerts
        telegram_alerts = TelegramAlerts(
            bus, telegram_token, telegram_chat_id,
            portfolio=portfolio, batch_interval=60,
        )
        asyncio.create_task(telegram_alerts.start())
    else:
        logger.warning(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID no configurados "
            "— alertas Telegram desactivadas"
        )

    # ── Periodic optimization scheduler ──────────────────────────────────
    if args.optimize:
        opt_config = config.get("optimization", {})
        interval_days = opt_config.get("interval_days", 30)
        opt_metric = opt_config.get("metric", "sharpe")
        opt_trials = opt_config.get("trials", 100)

        logger.info("Optimizacion periodica activada — cada {} dia(s), metrica={}",
                     interval_days, opt_metric)
        asyncio.create_task(_optimization_scheduler(
            interval_days=interval_days,
            metric=opt_metric,
            trials=opt_trials,
        ))
    else:
        logger.debug("Optimizacion periodica desactivada (usar --optimize para activar)")

    # Ejecutar engine
    try:
        await engine.run()
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        if telegram_alerts:
            telegram_alerts.stop()
        logger.info("CellMesh detenido.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Detenido por el usuario.")
