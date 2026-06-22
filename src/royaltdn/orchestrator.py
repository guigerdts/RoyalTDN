#!/usr/bin/env python3
"""RoyalTDN — Orchestrator: coordinador de la arquitectura modular

Fase 4, Bloque 3 (documento 6, sección 6.4.4)

Lanza y coordina:
  - DataIngestor  (task): Alpaca WebSocket → Redis ``market_bars``
  - SMAStrategy   (task): Redis ``market_bars`` → señales ``signals``
  - Bucle principal (async): consume ``signals`` → risk check → orden Alpaca

Uso desde main.py:
    from royaltdn.orchestrator import Orchestrator
    orch = Orchestrator(...)
    await orch.start()
"""

import asyncio
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger
import pandas as pd

import redis.asyncio as aioredis
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from royaltdn.brokers.base import BaseBroker, OrderResult
from royaltdn.brokers.alpaca import AlpacaBroker
from royaltdn.ingestion.data_ingestor import DataIngestor
from royaltdn.strategy.sma_strategy import SMAStrategy
from royaltdn.strategy.bollinger_rsi import BollingerRSIStrategy
from royaltdn.strategy.momentum_atr import MomentumATRStrategy
from royaltdn.strategy.factor_rotation import FactorRotationStrategy
from royaltdn.scanner import Scanner
from royaltdn.scanner.universe import is_crypto_symbol
from royaltdn.execution.twap import execute_twap
from royaltdn.risk.portfolio import PortfolioPositionManager
from royaltdn.risk_manager import (
    calculate_position_size,
    check_risk_limits,
    get_atr,
)
from royaltdn.alerts import notify_entry, notify_exit, notify_kill_switch, notify_error, send_telegram_message_async
from royaltdn.monitoring.tca import calculate_slippage
from royaltdn.storage.db import Database

# ── Status publishing (Fase 6) ─────────────────────────────────────────────

LOGS_DIR = Path("logs")

def _atomic_write(path: Path, data: dict) -> bool:
    """Write dict as JSON atomically via .tmp + os.replace.
    
    Returns True on success, False on error. Never raises.
    """
    try:
        tmp_path = path.with_suffix(".tmp")
        content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(path))
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Error writing {}: {}", path, e)
        return False


# ── Constantes de entorno (Scanner) ───────────────────────────────────────

SCANNER_TOP_N = int(os.getenv("SCANNER_TOP_N", "3"))


def _get_scan_interval_override() -> Optional[int]:
    """Read SCANNER_INTERVAL_MINUTES env var dynamically.

    Returns:
        int if env var is set to a valid positive integer.
        None if not set or invalid (logs warning on invalid).
    """
    raw = os.getenv("SCANNER_INTERVAL_MINUTES", "")
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    if raw and raw != "":
        logger.warning("SCANNER_INTERVAL_MINUTES invalid ({}), using auto", raw)
    return None

# ── Constantes ────────────────────────────────────────────────────────────

SIGNALS_STREAM = "signals"
CONSUMER_GROUP = "executor"
CONSUMER_NAME = "orchestrator"
POLL_TIMEOUT_MS = 1000  # 1s — permite detectar stop rápido


class Orchestrator:
    """Orquestador modular: ingestor → estrategia → ejecución.

    Args:
        api_key:          Alpaca API key (paper).
        secret_key:       Alpaca secret key.
        redis_url:        Redis connection string.
        db_url:           TimescaleDB connection string (opcional).
        symbol:           Símbolo a tradear (default "SPY").
        sma_fast:         Período SMA rápida (default 5).
        sma_slow:         Período SMA lenta (default 20).
        feed:             Alpaca feed (default "iex").
        scanner:          Scanner instance (opcional); si se pasa, se usa en
                          lugar de inicializar uno nuevo en _setup().
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        redis_url: str,
        db_url: str = "",
        symbol: str = "SPY",
        sma_fast: int = 5,
        sma_slow: int = 20,
        feed: str = "iex",
        twap_min_shares: int = 100,
        twap_duration_minutes: int = 10,
        twap_enabled: bool = True,
        scanner: Optional[Scanner] = None,
        auto_execute: bool = False,
        max_positions: int = 5,
        brokers: Optional[Dict[str, BaseBroker]] = None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.redis_url = redis_url
        self.db_url = db_url
        self.symbol = symbol
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow
        self.feed = feed
        self.twap_min_shares = twap_min_shares
        self.twap_duration_minutes = twap_duration_minutes
        self.twap_enabled = twap_enabled
        self.auto_execute = auto_execute
        self.max_positions = max_positions

        # Brokers
        self._brokers: Dict[str, BaseBroker] = brokers or {}
        self._broker: Optional[BaseBroker] = None

        # Clientes
        self._trading: Optional[TradingClient] = None
        self._redis: Optional[aioredis.Redis] = None
        self._db: Optional[Database] = None

        # Tasks asyncio
        self._ingestor: Optional[DataIngestor] = None
        self._strategy: Optional[SMAStrategy] = None
        self._scanner: Optional[Scanner] = scanner  # ya viene inicializado desde main
        self._ingestor_task: Optional[asyncio.Task] = None
        self._strategy_task: Optional[asyncio.Task] = None

        # Fallback: si Redis no está disponible o los threads fallan,
        # el orchestrator cambia a modo legacy (polling REST directo)
        self._use_legacy_fallback = False

        # Estado del bot
        self._running = False
        self.paused = False
        self._initial_equity: float = 0.0
        self._consecutive_losses: int = 0
        self._trades_count: int = 0
        self._killed: bool = False

        # Status publishing (Fase 6)
        self._start_time: Optional[datetime] = None
        self._last_known_equity: float = 0.0
        self._equity_stale: bool = False
        self._equity_points: list = []  # cap 1000
        self._recent_signals: list = []  # cap 20
        self._daily_signal_count: int = 0
        self._last_signal: Optional[dict] = None
        self._last_error: Optional[str] = None
        self._last_known_price: float = 0.0
        self._signal_count_by_strategy: dict = {}

        # Scanner flags (Fase 13)
        self._is_scanning: bool = False
        self._pending_scan: bool = False

        # Portfolio Position Manager (Fase 16)
        self._portfolio: PortfolioPositionManager = PortfolioPositionManager()
        self.scanner_top_n: int = SCANNER_TOP_N

        # Dynamic scan interval (Fase 18.4)
        self._current_scan_interval: int = 60

        # First-iteration guard: auto-scan no se ejecuta al arrancar (#4)
        self._first_scan_done: bool = False

        # User strategies (Fase 7)
        self.strategy_store = None
        self.user_strategies: dict = {}
        self._last_user_strategy_files: set = set()

    # ── Setup ─────────────────────────────────────────────────────────

    async def _setup(self) -> bool:
        """Inicializa conexiones y sincroniza estado del broker."""
        # Trading client (sincrónico, se usa en executor)
        self._trading = TradingClient(self.api_key, self.secret_key, paper=True)

        # Set up default AlpacaBroker if not provided via brokers dict
        if not self._broker:
            self._broker = AlpacaBroker(self.api_key, self.secret_key, paper=True)
            if "stocks" not in self._brokers:
                self._brokers["stocks"] = self._broker

        # Scanner — viene desde main.py; el Orchestrator no lo crea
        if self._scanner is not None:
            logger.info("Scanner recibido desde main.py — listo para usar")
        else:
            logger.warning("Scanner no disponible — operando sin escaneo multi-activo")

        # User strategies (Fase 7)
        try:
            from royaltdn.strategy.strategy_store import StrategyStore
            self.strategy_store = StrategyStore()
            self._load_user_strategies()
        except Exception as e:
            logger.warning("Strategy store no disponible ({})", e)

        # Redis (async) — OPCIONAL: si falla, activa fallback legacy
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Conectado a Redis: {}", self.redis_url)

            # Crear consumer group para signals (si no existe)
            try:
                await self._redis.xgroup_create(
                    SIGNALS_STREAM,
                    CONSUMER_GROUP,
                    id="$",
                    mkstream=True,
                )
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
        except Exception as e:
            logger.warning("Redis no disponible ({}) — activando fallback legacy", e)
            self._redis = None
            self._use_legacy_fallback = True

        # DB (opcional)
        if self.db_url:
            self._db = Database(self.db_url)
            connected = await self._db.connect()
            if not connected:
                logger.warning("TimescaleDB no disponible — trades solo en logs")

        # Sincronizar estado de todos los brokers
        try:
            account = self._trading.get_account()
            self._initial_equity = float(account.equity)

            # Sincronizar posiciones desde TODOS los brokers
            total_positions = 0
            for broker_name, broker in self._brokers.items():
                try:
                    positions = broker.get_open_positions()
                    for pos in positions:
                        sym = pos.get("symbol", "")
                        if not sym:
                            continue
                        qty = float(pos.get("qty", 0))
                        side = "long" if qty > 0 else "short"
                        price = float(pos.get("entry", 0) or pos.get("current_price", 0) or 0)
                        if price == 0.0:
                            price = float(pos.get("current", 0) or 0)
                        self._portfolio.open_position(
                            sym, int(abs(qty)), price,
                            strategy="legacy", side=side, broker=broker_name,
                        )
                        total_positions += 1
                except Exception as e:
                    logger.warning("Error sincronizando posiciones desde '{}': {}", broker_name, e)

            logger.info(
                "Estado inicial — Capital: ${:.2f} | Posiciones: {}",
                self._initial_equity,
                self._portfolio.position_count(),
            )
        except Exception as e:
            logger.error("Error sincronizando estado del broker: {}", e)
            return False

        # Status publishing init (Fase 6)
        self._start_time = datetime.now(timezone.utc)
        self._last_known_equity = self._initial_equity
        try:
            self._publish_status()
            logger.info("Status inicial publicado en logs/")
        except Exception as e:
            logger.warning("Error publicando status inicial: {}", e)

        return True

    # ── Lanzar tareas asyncio ─────────────────────────────────────────

    async def _start_ingestor(self):
        """Lanza DataIngestor como tarea asyncio."""
        symbols = [self.symbol]
        self._ingestor = DataIngestor(
            self.api_key,
            self.secret_key,
            self.redis_url,
            symbols=symbols,
            feed=self.feed,
        )
        loop = asyncio.get_running_loop()
        self._ingestor_task = loop.create_task(
            self._ingestor.run(),
            name="data-ingestor",
        )
        logger.info("DataIngestor task creada ({})", self.symbol)

    async def _start_strategy(self):
        """Lanza SMAStrategy como tarea asyncio."""
        self._strategy = SMAStrategy(
            self.redis_url,
            symbol=self.symbol,
            sma_fast=self.sma_fast,
            sma_slow=self.sma_slow,
        )
        loop = asyncio.get_running_loop()
        self._strategy_task = loop.create_task(
            self._strategy.run(),
            name="sma-strategy",
        )
        logger.info("SMAStrategy task creada")

    # ── Ejecución de señales ─────────────────────────────────────────

    def _get_broker_for_symbol(self, symbol: str) -> BaseBroker:
        """Route a symbol to the correct broker.

        Crypto symbols (containing ``"/"``) → crypto broker.
        Stock/ETF symbols → stocks broker.

        Returns:
            BaseBroker instance.
        """
        if is_crypto_symbol(symbol) and "crypto" in self._brokers:
            return self._brokers["crypto"]
        return self._brokers.get("stocks", self._broker)

    def _is_market_open(self, symbol: str) -> bool:
        """Check if the market is currently open for a given symbol.

        Delegates to the symbol's broker for the authoritative check.
        """
        broker = self._get_broker_for_symbol(symbol)
        return broker.is_market_open(symbol)

    def close_position(self, symbol: str) -> bool:
        """Close an open position via the correct broker.

        Args:
            symbol: Symbol to close.

        Returns:
            True if the position was closed successfully.
        """
        broker = self._get_broker_for_symbol(symbol)
        return broker.close_position(symbol)

    async def _get_atr_value(self, symbol: Optional[str] = None) -> float:
        """Calcula ATR usando el broker correspondiente al symbol.

        Uses the symbol's broker (``broker.get_bars()``) instead of
        creating a fresh Alpaca data client each time.

        Args:
            symbol: Symbol to calculate ATR for. Defaults to ``self.symbol``.

        Returns:
            float: ATR value.
        """
        symbol = symbol or self.symbol
        broker = self._get_broker_for_symbol(symbol)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: get_atr(broker=broker, symbol=symbol),
        )

    # ── Console IPC signal polling (Fase 8) ───────────────────────────

    def _check_signals(self) -> None:
        """Check console IPC signal files and act on them."""
        import os as _os

        # Pause/Resume signal
        pause_file = _os.path.join("logs", "pause_signal.json")
        if _os.path.exists(pause_file):
            try:
                with open(pause_file) as f:
                    import json as _json
                    cmd = _json.load(f)
                action = cmd.get("action")
                if action == "pause":
                    self.paused = True
                    logger.info("⏸️  Bot pausado por comando de consola")
                elif action == "resume":
                    self.paused = False
                    logger.info("▶️  Bot reanudado por comando de consola")
                _os.remove(pause_file)
            except Exception as e:
                logger.warning("Error al leer comando de pausa: {}", e)

        # Scanner trigger signal (Fase 13 — async via _pending_scan flag)
        scanner_file = _os.path.join("logs", "scan_now_signal.json")
        if _os.path.exists(scanner_file):
            try:
                _os.remove(scanner_file)
                if self._scanner is not None and not self._is_scanning:
                    self._pending_scan = True
                    logger.info("Scanner manual: senal detectada — scan encolado")
            except Exception as e:
                logger.warning("Error al procesar senal de scanner manual: {}", e)

    # ── Status publishing (Fase 6) ────────────────────────────────────

    def _get_current_equity(self) -> float:
        """Fetch combined equity across ALL configured brokers.

        Returns:
            float: combined equity value.

        On error: returns last known value, sets _equity_stale.
        """
        try:
            total = 0.0
            for name, broker in self._brokers.items():
                try:
                    total += broker.get_account_balance()
                except Exception as e:
                    logger.warning("Error fetching equity from broker '{}': {}", name, e)
            self._last_known_equity = total
            self._equity_stale = False
            return total
        except Exception as e:
            logger.warning("Error fetching equity: {}", e)
            self._equity_stale = True
            return self._last_known_equity

    def _build_equity_curve(self) -> list:
        """Append current equity point, cap at 1000."""
        now = datetime.now(timezone.utc)
        equity = self._last_known_equity if self._last_known_equity else self._initial_equity
        self._equity_points.append({
            "timestamp": now.isoformat(),
            "equity": equity,
        })
        if len(self._equity_points) > 1000:
            self._equity_points = self._equity_points[-1000:]
        return self._equity_points

    def _build_positions_list(self) -> list:
        """Build open positions list from PortfolioPositionManager."""
        positions = self._portfolio.get_all_positions()
        if not positions:
            return []
        result = []
        for key, pos in positions.items():
            result.append({
                "symbol": pos.symbol,
                "side": pos.side,
                "qty": pos.qty,
                "entry_price": pos.entry_price,
                "current_price": self._last_known_price if self._last_known_price else pos.entry_price,
                "entry_at": pos.opened_at.isoformat(),
                "strategy": pos.strategy,
                "broker": pos.broker,
            })
        return result

    def _build_strategies_list(self) -> list:
        """Build strategies status list from scanner + config + user strategies."""
        strategies_list = []
        if self._scanner and hasattr(self._scanner, 'strategies'):
            for name, strategy in self._scanner.strategies.items():
                params = strategy.get_parameters() if hasattr(strategy, 'get_parameters') else {}
                valid = strategy.validate() if hasattr(strategy, 'validate') else True
                strategies_list.append({
                    "name": name,
                    "active": True,
                    "params": params,
                    "validation": valid,
                    "last_signal": self._signal_count_by_strategy.get(name),
                    "signal_count": self._signal_count_by_strategy.get(name, 0),
                    "symbol": getattr(strategy, 'symbol', self.symbol),
                    "timeframe": getattr(strategy, 'timeframe', '1d'),
                    "category": getattr(strategy, 'category', 'swing'),
                })
        else:
            strategies_list.append({
                "name": "sma_crossover",
                "active": True,
                "params": {"fast_period": self.sma_fast, "slow_period": self.sma_slow},
                "validation": True,
                "last_signal": self._last_action,
                "signal_count": self._trades_count,
                "symbol": self.symbol,
                "timeframe": "1d",
                "category": "swing",
            })

        # User strategies (Fase 7) — skip inactive
        for name, strat in self.user_strategies.items():
            is_active = strat.config.get("active", True) if hasattr(strat, "config") else True
            if not is_active:
                continue
            strategies_list.append({
                "name": f"user_{name}",
                "active": is_active,
                "params": strat.get_parameters() if hasattr(strat, 'get_parameters') else {},
                "validation": strat.validate() if hasattr(strat, 'validate') else True,
                "last_signal": self._signal_count_by_strategy.get(f"user_{name}"),
                "signal_count": self._signal_count_by_strategy.get(f"user_{name}", 0),
                "symbol": strat.symbols[0] if strat.symbols else "ALL",
                "timeframe": strat.timeframe,
                "category": getattr(strat, 'category', 'swing'),
            })

        return strategies_list

    def _calc_scan_interval(self) -> int:
        """Calculate scan interval from active strategy categories.

        Returns:
            Minimum interval (minutes) among active strategy categories.
            Override via SCANNER_INTERVAL_MINUTES env var wins if set.
        """
        override = _get_scan_interval_override()
        if override is not None:
            return override

        categories: set[str] = set()
        for s in self._build_strategies_list():
            if s.get("active", True):
                categories.add(s.get("category", "swing"))

        if "scalping" in categories:
            return 2
        if "intraday" in categories:
            return 15
        if "swing" in categories:
            return 240
        return 60

    # ── User strategies (Fase 7) ─────────────────────────────────────

    def _load_user_strategies(self):
        """Load all user strategies from disk into self.user_strategies."""
        if not self.strategy_store:
            return
        from royaltdn.strategy.dynamic import DynamicStrategy

        configs = self.strategy_store.load_all()
        self.user_strategies.clear()
        count = 0
        for cfg in configs:
            name = cfg.get("name", "unnamed")
            try:
                strat = DynamicStrategy(cfg)
                if strat.validate():
                    self.user_strategies[name] = strat
                    count += 1
                    logger.info("Estrategia de usuario cargada: {}", name)
                else:
                    logger.warning("Estrategia de usuario inválida (validación): {}", name)
            except Exception as e:
                logger.warning("Error cargando estrategia {}: {}", name, e)

        # Track current files for watcher
        self._last_user_strategy_files = set()
        import glob as glob_mod
        try:
            self._last_user_strategy_files = {
                f for f in glob_mod.glob(os.path.join(self.strategy_store.store_dir, "*.json"))
                if not f.endswith(".tmp")
            }
        except Exception:
            pass

        logger.info("Estrategias de usuario cargadas: {}", count)

    def _watch_user_strategies(self):
        """Check for new/removed/changed user strategies on disk."""
        if not self.strategy_store:
            return
        from royaltdn.strategy.dynamic import DynamicStrategy

        import glob as glob_mod
        try:
            current_files = {
                f for f in glob_mod.glob(os.path.join(self.strategy_store.store_dir, "*.json"))
                if not f.endswith(".tmp")
            }
        except Exception:
            return

        previous = self._last_user_strategy_files
        new_files = current_files - previous
        removed_files = previous - current_files

        # Load new/changed strategies
        if new_files:
            for fpath in sorted(new_files):
                try:
                    with open(fpath, "r") as f:
                        import json as json_mod
                        cfg = json_mod.load(f)
                    name = cfg.get("name", "unnamed")
                    strat = DynamicStrategy(cfg)
                    if strat.validate():
                        self.user_strategies[name] = strat
                        logger.info("Watcher: nueva estrategia detectada - {}", name)
                    else:
                        logger.warning("Watcher: estrategia inválida - {}", name)
                except Exception as e:
                    logger.warning("Watcher: error cargando {}: {}", fpath, e)

        # Remove deleted strategies
        if removed_files:
            for fpath in removed_files:
                fname = os.path.basename(fpath)
                for name in list(self.user_strategies.keys()):
                    sanitized = name.lower().replace(" ", "_").replace("-", "_")
                    if sanitized in fname:
                        self.user_strategies.pop(name, None)
                        logger.info("Watcher: estrategia eliminada - {}", name)
                        break

        self._last_user_strategy_files = current_files

    def _last_signal_summary(self) -> Optional[dict]:
        """Return last signal summary or None."""
        if not self._last_signal:
            return None
        return {
            "action": self._last_signal.get("action"),
            "price": self._last_signal.get("price"),
            "symbol": self._last_signal.get("symbol", self.symbol),
            "strategy": self._last_signal.get("strategy", "sma_crossover"),
            "timestamp": self._last_signal.get("timestamp"),
            "metadata": self._last_signal.get("metadata", {}),
        }

    def _publish_status(self) -> None:
        """Write all 7 JSON status files atomically to logs/.

        Order: equity → positions → signals → strategies → trades → status (LAST).
        status.json is LAST so its presence and timestamp are authoritative.
        Never raises — errors are logged.
        """
        now = datetime.now(timezone.utc)
        uptime = int((now - self._start_time).total_seconds()) if self._start_time else 0

        # Track equity point
        equity = self._get_current_equity()
        equity_curve = self._build_equity_curve()

        # 1. equity.json
        pnl_day = equity - self._initial_equity
        pnl_day_pct = round(pnl_day / self._initial_equity * 100, 2) if self._initial_equity > 0 else 0.0
        self._last_known_equity = equity

        _atomic_write(LOGS_DIR / "equity.json", {
            "initial_equity": self._initial_equity,
            "current_equity": equity,
            "pnl_day": round(pnl_day, 2),
            "pnl_day_pct": pnl_day_pct,
            "drawdown": 0.0,
            "drawdown_pct": 0.0,
            "sharpe": 0.0,
            "equity_curve": equity_curve,
            "updated_at": now.isoformat(),
            "stale": self._equity_stale,
        })

        # 2. positions.json
        open_positions = self._build_positions_list()
        _atomic_write(LOGS_DIR / "positions.json", {
            "open_positions": open_positions,
            "total_open": len(open_positions),
            "updated_at": now.isoformat(),
        })

        # 3. signals.json
        _atomic_write(LOGS_DIR / "signals.json", {
            "today_count": self._daily_signal_count,
            "last_signals": self._recent_signals[-20:],
            "updated_at": now.isoformat(),
        })

        # 4. strategies.json
        _atomic_write(LOGS_DIR / "strategies.json", {
            "strategies": self._build_strategies_list(),
            "updated_at": now.isoformat(),
        })

        # 5. trades.json — only if trades exist
        if self._trades_count > 0:
            trades_path = LOGS_DIR / "trades.json"
            existing = {}
            try:
                if trades_path.exists():
                    raw = trades_path.read_text(encoding="utf-8")
                    if raw.strip():
                        existing = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                existing = {}
            _atomic_write(trades_path, existing or {
                "total_trades": 0, "win_rate": 0, "profit_factor": 0, "total_pnl": 0,
                "trades": [], "updated_at": now.isoformat(),
            })

        # 6. status.json (LAST — authoritative)
        bot_status = "PAUSADO" if self.paused else ("KILLED" if self._killed else "ONLINE")
        override = _get_scan_interval_override()
        _atomic_write(LOGS_DIR / "status.json", {
            "bot_status": bot_status,
            "paused": self.paused,
            "mode": "legacy" if self._use_legacy_fallback else "modular",
            "timestamp": now.isoformat(),
            "last_signal": self._last_signal_summary(),
            "last_error": self._last_error,
            "uptime_seconds": uptime,
            "symbols": [self.symbol],
            "scanner_enabled": self._scanner is not None,
            "scanner_interval_minutes": self._current_scan_interval,
            "scanner_interval_source": "env" if override is not None else "auto",
            "version": "1.0.0",
        })

    def _append_trade(self, trade: dict) -> None:
        """Append a completed trade to logs/trades.json.

        Reads existing, appends, recalculates summary metrics, writes back atomically.
        """
        path = LOGS_DIR / "trades.json"

        existing = {}
        try:
            if path.exists():
                raw = path.read_text(encoding="utf-8")
                if raw.strip():
                    existing = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            existing = {}

        trades = existing.get("trades", [])
        trades.append(trade)

        total = len(trades)
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        losses = total - wins
        gross_profit = sum(t["pnl"] for t in trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t.get("pnl", 0) < 0))

        output = {
            "total_trades": total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
            "total_pnl": round(total_pnl, 2),
            "trades": trades,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write(path, output)

    async def _submit_order(self, side: OrderSide, qty: int, symbol: Optional[str] = None) -> Optional[object]:
        """Envía orden directa o TWAP si supera el umbral.

        Si la orden es grande (``qty >= twap_min_shares``) y TWAP está
        habilitado, delega en ``execute_twap`` para repartir en lotes.
        """
        if qty <= 0:
            logger.warning("Qty {} inválida — orden cancelada", qty)
            return None

        # TWAP para órdenes grandes
        if self.twap_enabled and qty >= self.twap_min_shares:
            logger.info(
                "📐 TWAP: %d >= %d (umbral) — dividiendo en lotes de %d min",
                qty, self.twap_min_shares, self.twap_duration_minutes,
            )
            results = await execute_twap(
                symbol=symbol or self.symbol,
                total_shares=qty,
                duration_minutes=self.twap_duration_minutes,
                side=side,
                trading_client=self._trading,
                api_key=self.api_key,
                secret_key=self.secret_key,
                feed=self.feed,
            )

            # Registrar cada lote en DB
            if self._db and self._db.is_connected:
                for r in results:
                    if r.get("order_id"):
                        await self._db.insert_order({
                            "order_id": r["order_id"],
                            "symbol": symbol or self.symbol,
                            "side": side.name,
                            "qty": r["shares"],
                            "order_type": "market",
                            "status": "new",
                            "filled_price": None,
                            "filled_qty": None,
                            "created_at": datetime.now(),
                        })

            return results

        # Orden directa (normal) — delegated to correct broker per symbol
        sym = symbol or self.symbol
        broker = self._get_broker_for_symbol(sym)
        result = broker.submit_order(
            symbol=sym,
            side=side.name.lower(),
            qty=qty,
        )
        if result:
            logger.info(
                "📤 Orden: {} {} {} — ID: {}",
                side.name, qty, symbol or self.symbol, result.order_id,
            )

            if self._db and self._db.is_connected:
                await self._db.insert_order({
                    "order_id": result.order_id,
                    "symbol": symbol or self.symbol,
                    "side": side.name,
                    "qty": qty,
                    "order_type": "market",
                    "status": result.status,
                    "filled_price": result.price if result.price else None,
                    "filled_qty": qty,  # market order approximation
                    "created_at": datetime.now(),
                })

        return result

    @staticmethod
    def _get_order_id(result: object) -> Optional[str]:
        """Extrae order_id de un resultado de orden (single, OrderResult o TWAP)."""
        if result is None:
            return None
        if isinstance(result, OrderResult):
            return result.order_id
        if isinstance(result, list):
            # TWAP: usar ID del último lote
            last = result[-1] if result else {}
            return last.get("order_id")
        return getattr(result, "id", None)

    @staticmethod
    def _get_filled_price(result: object) -> Optional[float]:
        """Extrae filled_avg_price de un resultado de orden."""
        if result is None:
            return None
        if isinstance(result, OrderResult):
            return result.price if result.price else None
        if isinstance(result, list) or isinstance(result, dict):
            return None  # TWAP: no hay filled price agregado
        if hasattr(result, "filled_avg_price") and result.filled_avg_price:
            return float(result.filled_avg_price)
        return None

    async def _execute_scanner_signals(self, signals: List[dict]) -> None:
        """Execute top-N scanner signals through the risk pipeline.
        
        Pipeline gates per signal:
        1. Kill switch check
        2. Duplicate position check (same symbol)
        3. Max positions check
        4. SPY + legacy mode conflict
        5. Market hours check (stocks only)
        6. Per-symbol exposure > 25%
        7. RiskManager limits
        
        If all gates pass: ATR sizing → broker order → PPM tracking → trade record → Telegram.
        """
        if not self.auto_execute:
            logger.info("Scanner auto-execute disabled — signals logged only")
            for sig in signals:
                logger.info(f"Scanner signal (not executed): {sig.get('symbol')} {sig.get('action')}")
            return
        
        # Gate 0: Kill switch check before batch — combine equity across brokers
        total_equity = self._get_current_equity()
        
        kill, reason = check_risk_limits(
            self._trading.get_account(), self._initial_equity, self._consecutive_losses,
        )
        if kill:
            logger.warning(f"Scanner: kill switch triggered ({reason}) — closing ALL positions")
            closed = self._portfolio.close_all_positions()
            for pos in closed:
                broker = self._get_broker_for_symbol(pos.symbol)
                try:
                    await self._submit_order(OrderSide.SELL, int(pos.qty), symbol=pos.symbol)
                except Exception as e:
                    logger.warning("Error closing {} via {}: {}", pos.symbol, pos.broker, e)
            # Also close positions directly on each broker as safety net
            for bname, broker in self._brokers.items():
                try:
                    open_positions = broker.get_open_positions()
                    for p in open_positions:
                        sym = p.get("symbol", "")
                        if sym:
                            broker.close_position(sym)
                except Exception as e:
                    logger.warning("Error closing positions on broker '{}': {}", bname, e)
            self._killed = True
            return
        
        for signal in signals:
            symbol = signal.get("symbol", "")
            action = signal.get("action", "BUY")
            broker = self._get_broker_for_symbol(symbol)
            
            # Gate 1: Duplicate position
            if self._portfolio.has_position(symbol, broker=broker._broker_name if hasattr(broker, '_broker_name') else None):
                logger.info(f"Signal rejected: {symbol} - position already open")
                continue
            
            # Gate 2: Max positions
            if self._portfolio.position_count() >= self.max_positions:
                logger.info(f"Signal rejected: {symbol} - max positions reached ({self._portfolio.position_count()}/{self.max_positions})")
                continue
            
            # Gate 3: SPY + legacy conflict
            if symbol == "SPY" and self._use_legacy_fallback and self._portfolio.has_position("SPY"):
                logger.info(f"Signal rejected: {symbol} - legacy mode already holds SPY")
                continue
            
            # Gate 4: Market hours — use broker.is_market_open
            if not self._is_market_open(symbol):
                logger.info(f"Signal rejected: {symbol} - market closed")
                continue
            
            # Gate 5: Per-symbol exposure — use combined equity
            broker_name = getattr(broker, '_broker_name', 'alpaca')
            sym_exposure = self._portfolio.get_symbol_exposure(symbol, total_equity, broker=broker_name)
            if sym_exposure > 0.25:
                logger.info(f"Signal rejected: {symbol} - exposure {sym_exposure:.1%} exceeds 25% limit")
                continue
            
            # Gate 6: RiskManager limits
            if not self._killed:
                kill2, reason2 = check_risk_limits(
                    self._trading.get_account(), self._initial_equity, self._consecutive_losses,
                )
                if kill2:
                    logger.warning(f"Signal rejected: {symbol} - {reason2}")
                    continue
            
            # Calculate ATR-based position size via broker
            atr = get_atr(broker=broker, symbol=symbol)
            qty = calculate_position_size(self._trading.get_account(), atr)
            
            if qty <= 0:
                logger.warning(f"Signal rejected: {symbol} - invalid position size ({qty})")
                continue
            
            # Submit order via correct broker
            side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
            entry = await self._submit_order(side, qty, symbol=symbol)
            
            if entry:
                filled_price = self._get_filled_price(entry) or float(signal.get("price", 0))
                
                # Track position in PPM with broker name
                self._portfolio.open_position(
                    symbol=symbol,
                    qty=float(qty),
                    entry_price=filled_price,
                    strategy="scanner",
                    broker=broker_name,
                )
                
                # Record trade
                trade_record = {
                    "symbol": symbol,
                    "side": "long",
                    "entry_price": filled_price,
                    "exit_price": 0.0,
                    "qty": qty,
                    "pnl": 0.0,
                    "entry_at": datetime.now(timezone.utc).isoformat(),
                    "exit_at": None,
                    "strategy": "scanner",
                    "source": "scanner",
                    "broker": broker_name,
                }
                try:
                    self._append_trade(trade_record)
                except Exception as e:
                    logger.warning(f"Error recording scanner trade: {e}")
                
                # Telegram notification
                try:
                    from royaltdn.alerts import notify_entry
                    await notify_entry(symbol, "buy", qty, filled_price)
                except Exception as e:
                    logger.warning(f"Telegram notification error: {e}")
                
                logger.info(f"Scanner signal EXECUTED: BUY {qty} {symbol} @ ${filled_price:.2f} (broker={broker_name})")

    async def _execute_signal(self, signal: dict) -> None:
        """Procesa una señal: risk check → posición → orden → DB → alerta."""
        action = signal.get("action")
        price = float(signal.get("price", 0))

        if action not in ("BUY", "SELL"):
            logger.warning("Señal desconocida: {}", action)
            return

        logger.info("🚦 Procesando señal {} @ {:.2f}", action, price)

        symbol_for_order = signal.get("symbol", self.symbol)
        broker_for_signal = self._get_broker_for_symbol(symbol_for_order)
        broker_name = getattr(broker_for_signal, '_broker_name', 'alpaca')

        # ── Risk check (kill switch touches ALL brokers) ──
        if not self._killed:
            kill, reason = check_risk_limits(
                self._trading.get_account(),
                self._initial_equity,
                self._consecutive_losses,
            )
            if kill:
                await notify_kill_switch(reason)
                logger.error("🛑 {}", reason)

                # Cerrar todas las posiciones desde PPM
                closed = self._portfolio.close_all_positions()
                for pos in closed:
                    await self._submit_order(OrderSide.SELL, int(pos.qty), symbol=pos.symbol)

                # Safety net: close positions on every broker
                for bname, broker in self._brokers.items():
                    try:
                        open_positions = broker.get_open_positions()
                        for p in open_positions:
                            sym = p.get("symbol", "")
                            if sym:
                                broker.close_position(sym)
                    except Exception:
                        pass

                self._killed = True
                return

        if self._killed:
            logger.warning("Bot KILLED — ignorando señal")
            return

        # ── Track signal (Fase 6) ──
        self._daily_signal_count += 1
        self._last_signal = {
            "action": action,
            "symbol": symbol_for_order,
            "price": price,
            "strategy": signal.get("strategy", "sma_crossover"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": signal.get("metadata", {}),
        }
        self._recent_signals.append(self._last_signal)
        if len(self._recent_signals) > 20:
            self._recent_signals = self._recent_signals[-20:]
        self._last_known_price = price

        # ── BUY ──
        if action == "BUY" and not self._portfolio.has_position(symbol_for_order, broker=broker_name):
            # Calcular ATR y tamaño de posición usando el broker correcto
            atr = await self._get_atr_value(symbol=symbol_for_order)
            account = self._trading.get_account()
            qty = calculate_position_size(account, atr)

            # Capturar arrival price (último precio conocido antes de ejecutar)
            arrival_price = price
            exec_method = "twap" if self.twap_enabled and qty >= self.twap_min_shares else "market"

            entry = await self._submit_order(OrderSide.BUY, qty, symbol=symbol_for_order)

            if entry:
                self._portfolio.open_position(
                    symbol=symbol_for_order,
                    qty=float(qty),
                    entry_price=arrival_price,
                    strategy="sma_crossover",
                    broker=broker_name,
                )

            if price > 0:
                await notify_entry(symbol_for_order, "buy", qty, price)

        # ── SELL (cierre) ──
        elif action == "SELL" and self._portfolio.has_position(symbol_for_order, broker=broker_name):
            pos = self._portfolio.get_position(symbol_for_order, broker=broker_name)
            if not pos:
                logger.warning(f"No position found for {symbol_for_order} on {broker_name}")
                return

            # Capturar arrival price antes de ejecutar
            arrival_price = price
            exec_method = "twap" if self.twap_enabled and pos.qty >= self.twap_min_shares else "market"

            exit_result = await self._submit_order(OrderSide.SELL, int(pos.qty), symbol=symbol_for_order)

            # P&L
            pnl = (price - pos.entry_price) * float(pos.qty)

            # Slippage (filled vs arrival)
            filled_price = self._get_filled_price(exit_result)
            slippage_bps = calculate_slippage(filled_price, arrival_price) if filled_price else None

            if price > 0:
                await notify_exit(symbol_for_order, "sell", int(pos.qty), price, pnl)

            # Registrar trade en DB (con TCA)
            if self._db and self._db.is_connected and pos.opened_at:
                await self._db.insert_trade({
                    "symbol": symbol_for_order,
                    "side": "long",
                    "entry_price": pos.entry_price,
                    "exit_price": price,
                    "qty": int(pos.qty),
                    "pnl": pnl,
                    "entry_order_id": None,
                    "exit_order_id": self._get_order_id(exit_result),
                    "entry_at": pos.opened_at,
                    "exit_at": datetime.now(timezone.utc),
                    "strategy": "sma_crossover",
                    "slippage_bps": slippage_bps,
                    "arrival_price": arrival_price,
                    "execution_method": exec_method,
                })

            # Actualizar contador de pérdidas
            if pnl < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0

            self._trades_count += 1

            # Append trade to logs/trades.json (Fase 6)
            trade_record = {
                "symbol": symbol_for_order,
                "side": "long",
                "entry_price": pos.entry_price,
                "exit_price": price,
                "qty": int(pos.qty),
                "pnl": round(pnl, 2),
                "entry_at": pos.opened_at.isoformat(),
                "exit_at": datetime.now(timezone.utc).isoformat(),
                "strategy": "sma_crossover",
                "slippage_bps": slippage_bps,
                "execution_method": exec_method,
                "broker": broker_name,
            }
            try:
                self._append_trade(trade_record)
            except Exception as e:
                logger.warning("Error appending trade: {}", e)

            self._portfolio.close_position(symbol_for_order, broker=broker_name)

    # ── Monitor de salud de tareas ──────────────────────────────────

    def _check_task_health(self) -> bool:
        """Verifica que las tareas del ingestor y estrategia estén vivas.

        Returns:
            True  → todo bien
            False → al menos una tarea murió (el ingestor)
        """
        if self._ingestor_task and self._ingestor_task.done():
            # Verificar si fue una excepción no cancelada
            if not self._ingestor_task.cancelled():
                exc = self._ingestor_task.exception()
                logger.error(
                    "⚠️ DataIngestor task MURIÓ con error: %s — activando fallback legacy",
                    exc,
                )
            else:
                logger.warning("DataIngestor task cancelada")
            return False

        if self._strategy_task and self._strategy_task.done():
            if not self._strategy_task.cancelled():
                exc = self._strategy_task.exception()
                logger.warning(
                    "SMAStrategy task MURIÓ: %s — continuando sin estrategia",
                    exc,
                )
            else:
                logger.warning("SMAStrategy task cancelada")
            # No activamos fallback solo por la estrategia

        return True

    async def _stop_strategy(self):
        """Detiene la tarea de la estrategia."""
        if self._strategy and self._strategy_task and not self._strategy_task.done():
            try:
                self._strategy.stop()
                self._strategy_task.cancel()
                # Dar tiempo para que la cancelación se propague
                try:
                    await asyncio.wait_for(self._strategy_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                logger.info("SMAStrategy detenido")
            except Exception as e:
                logger.debug("Error deteniendo SMAStrategy: {}", e)

    # ── Loop principal ──────────────────────────────────────────────

    async def _main_loop(self):
        """Bucle principal: consume señales de Redis y ejecuta.

        Monitorea la salud de las tareas del ingestor cada 10 iteraciones.
        Si el ingestor muere, sale del loop y ``start()`` maneja el fallback.
        """
        self._running = True
        _health_counter = 0

        while self._running and not self._killed:
            # Verificar salud de tareas cada 10 iteraciones
            _health_counter += 1
            if _health_counter >= 10:
                _health_counter = 0
                if not self._check_task_health():
                    self._use_legacy_fallback = True
                    await self._stop_strategy()
                    await send_telegram_message_async(
                        "ℹ️ <b>LEGACY FALLBACK</b>\n"
                        "DataIngestor task murió — cambiando a modo legacy (REST polling)"
                    )
                    break

            try:
                result = await self._redis.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={SIGNALS_STREAM: ">"},
                    count=5,
                    block=POLL_TIMEOUT_MS,
                )

                if not result:
                    continue

                for stream_name, messages in result:
                    for msg_id, fields in messages:
                        logger.debug("Signal recibida: {} {}", msg_id, fields)
                        await self._execute_signal(fields)
                        await self._redis.xack(SIGNALS_STREAM, CONSUMER_GROUP, msg_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error en main loop: {}", e, exc_info=True)
                await notify_error(str(e))
                await asyncio.sleep(5)

    # ── Async scanner wrapper (Fase 13) ──────────────────────────

    async def _run_scanner(self) -> Optional[List[dict]]:
        """Runs Scanner.scan() in a thread executor to avoid blocking the event loop.

        Uses loop.run_in_executor() with configurable timeout.
        Flags _is_scanning to prevent concurrent scans.

        Returns:
            List of signal dicts on success, None on failure.
        """
        if self._is_scanning:
            logger.info("Scanner: already running — skipping")
            return None
        if self._scanner is None:
            logger.warning("Scanner: not available — skipping")
            return None

        self._is_scanning = True
        self._pending_scan = False
        loop = asyncio.get_running_loop()
        timeout = int(os.getenv("SCANNER_TIMEOUT", "300"))

        try:
            future = loop.run_in_executor(None, self._scanner.scan)
            signals = await asyncio.wait_for(future, timeout=timeout)
            count = len(signals) if signals else 0
            logger.info("Scanner: completed — {} signals generated", count)
            return signals
        except asyncio.TimeoutError:
            logger.warning("Scanner: timeout after {}s — cancelling scan", timeout)
            future.cancel()
            return None
        except Exception as e:
            err = str(e)
            if "401" in err or "403" in err:
                logger.error("Scanner: auth error: {} — aborting", err)
            else:
                logger.warning("Scanner: error: {}", err)
            return None
        finally:
            self._is_scanning = False

    # ── Fallback legacy (polling REST) ─────────────────────────────

    async def _run_legacy_loop(self):
        """Modo legacy: polling REST sobre Alpaca Historical Data.

        Se usa cuando Redis no está disponible o los threads fallan.
        Reemplaza el pipeline ingestor → Redis → strategy con polling
        directo: cada N segundos pide las últimas velas, calcula SMA
        y ejecuta la señal en el broker.

        Risk manager (``check_risk_limits``, ``calculate_position_size``) y
        alertas (Telegram) están activos — todo pasa por ``_execute_signal``.

        Este modo es menos preciso (datos no en tiempo real) pero
        mantiene el bot operativo sin Redis.
        """
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        # Usar try/except por si la librería no está instalada
        try:
            data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
        except Exception as e:
            logger.critical(
                "No se pudo inicializar Alpaca Historical Data Client: %s", e,
            )
            await notify_error(f"Fallo crítico en legacy mode: {e}")
            return

        poll_interval = 60  # segundos entre polls

        self._running = True
        logger.info("=" * 50)
        logger.info("🔄 MODO LEGACY ACTIVO — polling cada {}s", poll_interval)
        logger.info("  Risk manager:    ACTIVO")
        logger.info("  Alertas Telegram: ACTIVAS")
        logger.info("  TWAP:             {}", "ACTIVO" if self.twap_enabled else "INACTIVO")
        logger.info("  Scanner:          {}", "ACTIVO" if self._scanner else "NO DISPONIBLE")
        logger.info("=" * 50)
        await send_telegram_message_async(
            f"ℹ️ <b>LEGACY FALLBACK</b>\n"
            f"RoyalTDN en modo LEGACY — REST polling c/{poll_interval}s\n"
            f"Símbolo: {self.symbol} SMA{self.sma_fast}/{self.sma_slow}\n"
            f"Risk manager activo — alertas en tiempo real reducido"
        )

        # Contador para el scanner (se ejecuta cada intervalo calculado)
        # Intervalo se recalcula por ciclo desde _calc_scan_interval()
        scanner_cycle = 0
        self._current_scan_interval = self._calc_scan_interval()
        scanner_iterations = int((self._current_scan_interval * 60) / poll_interval) if self._current_scan_interval > 0 else 0

        while self._running and not self._killed:
            try:
                # ── Console IPC signals (Fase 8) ──
                self._check_signals()

                # ── Scanner manual: se ejecuta INCLUSO si el bot está pausado ──
                #     El scan manual solo actualiza scanner_results.json y guarda
                #     señales; NO ejecuta trades cuando está pausado.
                if self._scanner and self._pending_scan and not self._is_scanning:
                    logger.info("Scanner manual: detectada senal — ejecutando scan...")
                    signals = await self._run_scanner()
                    if signals:
                        top_signals = self._scanner.get_top_signals(n=SCANNER_TOP_N)
                        logger.info(
                            "Scanner manual: %d senales generadas — top %d",
                            len(signals), len(top_signals),
                        )
                        # Solo ejecutar trades si el bot NO está pausado
                        if not self.paused:
                            await self._execute_scanner_signals(top_signals)
                        else:
                            logger.info(
                                "Scanner manual: bot PAUSADO — senales guardadas en "
                                "scanner_results.json, trades NO ejecutados"
                            )
                    else:
                        logger.warning("Scanner manual: NO se generaron senales")
                    await asyncio.sleep(poll_interval)
                    continue

                if self.paused:
                    self._publish_status()
                    import time as _time
                    _time.sleep(60)
                    continue

                # ── Recalculate scan interval each cycle ──
                self._current_scan_interval = self._calc_scan_interval()
                scanner_iterations = int(
                    (self._current_scan_interval * 60) / poll_interval
                ) if self._current_scan_interval > 0 else 0

                # ── First-iteration guard: auto-scan NO se ejecuta al arrancar (#4) ──
                if not self._first_scan_done:
                    self._first_scan_done = True
                    logger.info("DEBUG: primera iteracion, saltando escaneo automatico")
                else:
                    # ── Auto-scan (solo cuando el bot NO está pausado) ──
                    if self._scanner and scanner_iterations > 0:
                        scanner_cycle += 1
                        if scanner_cycle >= scanner_iterations:
                            scanner_cycle = 0
                            logger.info("Scanner: ejecutando escaneo automatico...")
                            signals = await self._run_scanner()
                            if signals:
                                top_signals = self._scanner.get_top_signals(n=self.scanner_top_n)
                                if top_signals:
                                    logger.info(
                                        "Scanner: %d senales generadas — ejecutando top %d via scanner pipeline",
                                        len(signals), len(top_signals),
                                    )
                                    await self._execute_scanner_signals(top_signals)
                                    await asyncio.sleep(poll_interval)
                                    continue
                                else:
                                    logger.info("Scanner: sin senales — usando SPY por defecto")

                # ── User strategies watcher (Fase 7) ──
                try:
                    self._watch_user_strategies()
                except Exception as e:
                    logger.warning("User strategies watcher error: {}", e)

                # 1. Obtener últimas velas
                now = datetime.now(timezone.utc)
                request = StockBarsRequest(
                    symbol_or_symbols=self.symbol,
                    timeframe=TimeFrame.Minute,
                    limit=self.sma_slow + 5,  # suficientes para ambos SMAs
                    feed=self.feed,
                )
                bars = data_client.get_stock_bars(request)

                # 2. Extraer cierres (Alpaca retorna dict[str, list[Bar]])
                symbol_bars = bars.data.get(self.symbol, [])
                if len(symbol_bars) < self.sma_slow:
                    logger.debug(
                        "Esperando datos (%d/%d velas)",
                        len(symbol_bars), self.sma_slow,
                    )
                    await asyncio.sleep(poll_interval)
                    continue

                # Ordenar por timestamp por si vienen desordenados
                symbol_bars.sort(key=lambda b: b.timestamp)
                closes = [float(b.close) for b in symbol_bars]

                # 3. Calcular SMA inline
                curr_fast = sum(closes[-self.sma_fast:]) / self.sma_fast
                curr_slow = sum(closes[-self.sma_slow:]) / self.sma_slow

                # Valores previos (último valor antes del más reciente)
                prev_fast = sum(closes[-(self.sma_fast + 1):-1]) / self.sma_fast
                prev_slow = sum(closes[-(self.sma_slow + 1):-1]) / self.sma_slow

                # 4. Detectar cruce
                action = None
                if prev_fast <= prev_slow and curr_fast > curr_slow:
                    action = "BUY"
                elif prev_fast >= prev_slow and curr_fast < curr_slow:
                    action = "SELL"

                if action:
                    signal = {
                        "action": action,
                        "price": closes[-1],
                        "symbol": self.symbol,
                        "timestamp": now.isoformat(),
                        "fast_sma": round(curr_fast, 2),
                        "slow_sma": round(curr_slow, 2),
                    }
                    logger.info("Señal legacy: {} {} @ {:.2f}", self.symbol, action, closes[-1])
                    await self._execute_signal(signal)

                # ── User strategy evaluation (Fase 7) ──
                if self.user_strategies and len(symbol_bars) >= 50:
                    ohlcv = {
                        "open":   [float(b.open)   for b in symbol_bars],
                        "high":   [float(b.high)   for b in symbol_bars],
                        "low":    [float(b.low)    for b in symbol_bars],
                        "close":  closes,
                        "volume": [float(b.volume) for b in symbol_bars],
                    }
                    data = pd.DataFrame(ohlcv)
                    for name, strat in list(self.user_strategies.items()):
                        # Skip inactive strategies (Fase 11)
                        if hasattr(strat, "config") and not strat.config.get("active", True):
                            continue
                        try:
                            symbols = strat.symbols
                            if symbols and self.symbol not in symbols and "ALL" not in symbols:
                                continue
                            signal = strat.generate_signal(data)
                            if signal:
                                signal["symbol"] = signal.get("symbol", self.symbol)
                                logger.info(
                                    "Señal usuario %s: %s %s @ %.2f",
                                    name, self.symbol, signal["action"], closes[-1],
                                )
                                await self._execute_signal(signal)
                        except Exception as e:
                            logger.warning("Error en estrategia usuario {}: {}", name, e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                err_str = f"{e}"
                # No alarmar por errores esperados fuera de mercado
                if "429" in err_str:
                    logger.warning("Rate limit Alpaca — esperando {}s", poll_interval)
                elif "401" in err_str or "403" in err_str:
                    logger.error("Auth error en legacy loop: {}", err_str)
                    await notify_error(f"Auth error en legacy mode: {err_str}")
                    await asyncio.sleep(poll_interval * 3)
                    continue
                else:
                    logger.warning("Error en legacy loop: {}", err_str)
                await asyncio.sleep(poll_interval)

            # Publish status at end of cycle (Fase 6)
            try:
                self._publish_status()
            except Exception as e:
                logger.warning("Status publish error: {}", e)

            await asyncio.sleep(poll_interval)

        logger.info("Legacy loop finalizado")

    # ── Start / Stop ────────────────────────────────────────────────

    async def start(self):
        """Arranca todos los módulos y el bucle principal.

        Si Redis no está disponible, activa fallback legacy (polling REST).
        """
        logger.info("=" * 50)
        logger.info("RoyalTDN — Arquitectura Modular Iniciando")
        logger.info("=" * 50)

        if not await self._setup():
            logger.error("Setup falló — abortando")
            return

        # Elegir modo de operación
        if self._use_legacy_fallback:
            logger.info("🔄 MODO FALLBACK LEGACY — usando polling REST (sin Redis Streams)")
            await self._run_legacy_loop()
        else:
            # Lanzar tareas asyncio (ingestor + estrategia)
            try:
                await self._start_ingestor()
                await asyncio.sleep(0.5)
                await self._start_strategy()
            except Exception as e:
                logger.error("Error lanzando tareas: {}\n{}", e, traceback.format_exc())
                logger.info("🔄 Fallback a modo legacy")
                self._use_legacy_fallback = True
                await self._run_legacy_loop()
                await self._shutdown()
                return

            # Bucle principal con Redis Streams
            # Si _main_loop sale por task death, _use_legacy_fallback queda True
            await self._main_loop()

            # Transición automática a legacy si el ingestor murió durante la ejecución
            if self._use_legacy_fallback and self._running and not self._killed:
                logger.info("=" * 50)
                logger.info("🔄 TRANSICIÓN AUTOMÁTICA A MODO LEGACY (polling REST)")
                logger.info("  La tarea de ingesta falló — continuando con polling directo")
                logger.info("  Risk manager y alertas siguen activos")
                logger.info("=" * 50)
                await self._run_legacy_loop()

        # Cleanup
        await self._shutdown()

    async def _shutdown(self):
        """Detiene tareas y cierra conexiones."""
        logger.info("Deteniendo RoyalTDN...")

        # Publish final status (Fase 6) — BEFORE closing connections
        try:
            self._publish_status()
            logger.info("Status final publicado en logs/")
        except Exception as e:
            logger.warning("Error publicando status final: {}", e)

        # Detener estrategia
        if self._strategy:
            try:
                self._strategy.stop()
                logger.info("SMAStrategy detenido")
            except Exception as e:
                logger.debug("Error deteniendo SMAStrategy: {}", e)

        # Cancelar tarea de estrategia
        if self._strategy_task and not self._strategy_task.done():
            self._strategy_task.cancel()
            try:
                await asyncio.wait_for(self._strategy_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Detener ingestor
        if self._ingestor:
            try:
                self._ingestor.stop()
                logger.info("DataIngestor detenido")
            except Exception as e:
                logger.debug("Error deteniendo DataIngestor: {}", e)

        # Cancelar tarea de ingestor
        if self._ingestor_task and not self._ingestor_task.done():
            self._ingestor_task.cancel()
            try:
                await asyncio.wait_for(self._ingestor_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Cerrar DB
        if self._db:
            await self._db.close()

        # Cerrar Redis
        if self._redis:
            await self._redis.close()

        # Resumen final
        if self._trading:
            account = self._trading.get_account()
            final_equity = float(account.equity)
            pnl_total = final_equity - self._initial_equity
            logger.info("=" * 50)
            logger.info("BOT DETENIDO")
            logger.info("  Capital inicial: ${:.2f}", self._initial_equity)
            logger.info("  Capital final:   ${:.2f}", final_equity)
            logger.info("  P&L total:       ${:.2f}", pnl_total)
            logger.info("  Trades:          {}", self._trades_count)
            logger.info("  Losses seguidas: {}", self._consecutive_losses)
            logger.info("=" * 50)

    def stop(self):
        """Señal de parada desde otro hilo o signal handler."""
        self._running = False
        logger.info("Señal de parada recibida")

    # ── Factory method sincrónico ───────────────────────────────────

    @classmethod
    def run(
        cls,
        api_key: str,
        secret_key: str,
        redis_url: str,
        db_url: str = "",
        symbol: str = "SPY",
        sma_fast: int = 5,
        sma_slow: int = 20,
        feed: str = "iex",
    ):
        """Factory sincrónico: crea, arranca y corre el orchestrator.

        Útil para entry points CLI:
            Orchestrator.run(...)
        """
        orch = cls(
            api_key=api_key,
            secret_key=secret_key,
            redis_url=redis_url,
            db_url=db_url,
            symbol=symbol,
            sma_fast=sma_fast,
            sma_slow=sma_slow,
            feed=feed,
        )

        try:
            asyncio.run(orch.start())
        except KeyboardInterrupt:
            orch.stop()
            logger.info("Detenido por usuario.")
