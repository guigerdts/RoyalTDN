#!/usr/bin/env python3
"""CellMesh Crypto Bot — Entry Point"""

import asyncio
import os
import sys
from pathlib import Path

import yaml
from loguru import logger

# Asegurar que el directorio raiz esta en sys.path
sys.path.insert(0, str(Path(__file__).parent))

from core.bus import EventBus
from core.clock import RealClock
from core.engine import EventEngine
from core.journal import Journal
from core.registry import CellRegistry
from inference.engine import InferenceEngine
from cells.loader import load_cells
from cells.base import Cell
from risk.portfolio import Portfolio
from risk.manager import RiskManager
from execution.paper_broker import PaperBroker


async def main():
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
    engine = EventEngine(clock, bus, risk_manager, broker, journal=journal)

    # Cargar celulas desde YAML
    strategies_dir = Path(__file__).parent / config["strategies_dir"]
    cells = load_cells(str(strategies_dir), inference_engine)
    for cell in cells:
        engine.register(cell)
        registry.register(cell)
        logger.info("Celula registrada: {} ({})", cell.name, cell.symbol)

    logger.info("CellMesh iniciado — {} celulas, {} simbolos, broker={}",
                len(cells), len(config["symbols"]), broker_type)

    # Iniciar feed de datos
    from data.binance_feed import BinanceFeed
    feed = BinanceFeed(config["symbols"], bus)
    asyncio.create_task(feed.start())

    # Iniciar dashboard
    from monitoring.dashboard import Dashboard
    dashboard = Dashboard(bus, portfolio)
    asyncio.create_task(dashboard.run())

    # Ejecutar engine
    try:
        await engine.run()
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        logger.info("CellMesh detenido.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Detenido por el usuario.")
