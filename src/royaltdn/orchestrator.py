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
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from royaltdn.ingestion.data_ingestor import DataIngestor
from royaltdn.strategy.sma_strategy import SMAStrategy
from royaltdn.execution.twap import execute_twap
from royaltdn.risk_manager import (
    calculate_position_size,
    check_risk_limits,
    get_atr,
)
from royaltdn.alerts import notify_entry, notify_exit, notify_kill_switch, notify_error, send_telegram_message_async
from royaltdn.monitoring.tca import calculate_slippage
from royaltdn.storage.db import Database

logger = logging.getLogger("royaltdn.orchestrator")

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

        # Clientes
        self._trading: Optional[TradingClient] = None
        self._redis: Optional[aioredis.Redis] = None
        self._db: Optional[Database] = None

        # Tasks asyncio
        self._ingestor: Optional[DataIngestor] = None
        self._strategy: Optional[SMAStrategy] = None
        self._ingestor_task: Optional[asyncio.Task] = None
        self._strategy_task: Optional[asyncio.Task] = None

        # Fallback: si Redis no está disponible o los threads fallan,
        # el orchestrator cambia a modo legacy (polling REST directo)
        self._use_legacy_fallback = False

        # Estado del bot
        self._running = False
        self._position: Optional[str] = None         # "long" | None
        self._position_qty: int = 0
        self._last_entry_price: float = 0.0
        self._last_entry_order_id: Optional[str] = None
        self._last_entry_at: Optional[datetime] = None
        self._initial_equity: float = 0.0
        self._consecutive_losses: int = 0
        self._trades_count: int = 0
        self._killed: bool = False

    # ── Setup ─────────────────────────────────────────────────────────

    async def _setup(self) -> bool:
        """Inicializa conexiones y sincroniza estado del broker."""
        # Trading client (sincrónico, se usa en executor)
        self._trading = TradingClient(self.api_key, self.secret_key, paper=True)

        # Redis (async) — OPCIONAL: si falla, activa fallback legacy
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Conectado a Redis: %s", self.redis_url)

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
            logger.warning("Redis no disponible (%s) — activando fallback legacy", e)
            self._redis = None
            self._use_legacy_fallback = True

        # DB (opcional)
        if self.db_url:
            self._db = Database(self.db_url)
            connected = await self._db.connect()
            if not connected:
                logger.warning("TimescaleDB no disponible — trades solo en logs")

        # Sincronizar estado del broker
        try:
            account = self._trading.get_account()
            self._initial_equity = float(account.equity)

            # Posición actual
            try:
                pos = self._trading.get_open_position(self.symbol)
                qty = float(pos.qty)
                self._position = "long" if qty > 0 else ("short" if qty < 0 else None)
                self._position_qty = int(abs(qty))
            except Exception:
                self._position = None
                self._position_qty = 0

            logger.info(
                "Estado inicial — Capital: $%.2f | Posición: %s (%d acc)",
                self._initial_equity,
                self._position or "none",
                self._position_qty,
            )
        except Exception as e:
            logger.error("Error sincronizando estado del broker: %s", e)
            return False

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
        logger.info("DataIngestor task creada (%s)", self.symbol)

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

    async def _get_atr_value(self) -> float:
        """Calcula ATR usando Alpaca REST (sincrónico en executor)."""
        loop = asyncio.get_running_loop()
        from alpaca.data.historical import StockHistoricalDataClient
        data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
        return await loop.run_in_executor(
            None, lambda: get_atr(data_client, self.symbol),
        )

    async def _submit_order(self, side: OrderSide, qty: int) -> Optional[object]:
        """Envía orden directa o TWAP si supera el umbral.

        Si la orden es grande (``qty >= twap_min_shares``) y TWAP está
        habilitado, delega en ``execute_twap`` para repartir en lotes.
        """
        if qty <= 0:
            logger.warning("Qty %d inválida — orden cancelada", qty)
            return None

        # TWAP para órdenes grandes
        if self.twap_enabled and qty >= self.twap_min_shares:
            logger.info(
                "📐 TWAP: %d >= %d (umbral) — dividiendo en lotes de %d min",
                qty, self.twap_min_shares, self.twap_duration_minutes,
            )
            results = await execute_twap(
                symbol=self.symbol,
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
                            "symbol": self.symbol,
                            "side": side.name,
                            "qty": r["shares"],
                            "order_type": "market",
                            "status": "new",
                            "filled_price": None,
                            "filled_qty": None,
                            "created_at": datetime.now(),
                        })

            return results

        # Orden directa (normal)
        order = self._trading.submit_order(
            MarketOrderRequest(
                symbol=self.symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
            )
        )
        logger.info("📤 Orden: %s %d %s — ID: %s", side.name, qty, self.symbol, order.id)

        if self._db and self._db.is_connected:
            await self._db.insert_order({
                "order_id": order.id,
                "symbol": self.symbol,
                "side": side.name,
                "qty": qty,
                "order_type": "market",
                "status": getattr(order, "status", "new"),
                "filled_price": float(order.filled_avg_price) if hasattr(order, "filled_avg_price") and order.filled_avg_price else None,
                "filled_qty": int(order.filled_qty) if hasattr(order, "filled_qty") and order.filled_qty else None,
                "created_at": datetime.now(),
            })

        return order

    @staticmethod
    def _get_order_id(result: object) -> Optional[str]:
        """Extrae order_id de un resultado de orden (single o TWAP)."""
        if result is None:
            return None
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
        if isinstance(result, list) or isinstance(result, dict):
            return None  # TWAP: no hay filled price agregado
        if hasattr(result, "filled_avg_price") and result.filled_avg_price:
            return float(result.filled_avg_price)
        return None

    async def _execute_signal(self, signal: dict) -> None:
        """Procesa una señal: risk check → posición → orden → DB → alerta."""
        action = signal.get("action")
        price = float(signal.get("price", 0))

        if action not in ("BUY", "SELL"):
            logger.warning("Señal desconocida: %s", action)
            return

        logger.info("🚦 Procesando señal %s @ %.2f", action, price)

        # ── Risk check ──
        if not self._killed:
            kill, reason = check_risk_limits(
                self._trading.get_account(),
                self._initial_equity,
                self._consecutive_losses,
            )
            if kill:
                await notify_kill_switch(reason)
                logger.error("🛑 %s", reason)

                # Cerrar posición si existe
                if self._position == "long" and self._position_qty > 0:
                    await self._submit_order(OrderSide.SELL, self._position_qty)

                self._killed = True
                return

        if self._killed:
            logger.warning("Bot KILLED — ignorando señal")
            return

        # ── BUY ──
        if action == "BUY" and self._position != "long":
            # Calcular ATR y tamaño de posición
            atr = await self._get_atr_value()
            account = self._trading.get_account()
            qty = calculate_position_size(account, atr)

            # Capturar arrival price (último precio conocido antes de ejecutar)
            arrival_price = price
            exec_method = "twap" if self.twap_enabled and qty >= self.twap_min_shares else "market"

            # Si estábamos en short, cerrar primero
            if self._position == "short":
                await self._submit_order(OrderSide.BUY, self._position_qty)
                await asyncio.sleep(2)

            entry = await self._submit_order(OrderSide.BUY, qty)
            self._position = "long"
            self._position_qty = qty
            self._last_entry_price = arrival_price
            self._last_entry_order_id = self._get_order_id(entry)
            self._last_entry_at = datetime.now(timezone.utc)

            if price > 0:
                await notify_entry(self.symbol, "buy", qty, price)

        # ── SELL (cierre) ──
        elif action == "SELL" and self._position == "long":
            # Capturar arrival price antes de ejecutar
            arrival_price = price
            exec_method = "twap" if self.twap_enabled and self._position_qty >= self.twap_min_shares else "market"

            exit_result = await self._submit_order(OrderSide.SELL, self._position_qty)

            # P&L
            pnl = (price - self._last_entry_price) * self._position_qty

            # Slippage (filled vs arrival)
            filled_price = self._get_filled_price(exit_result)
            slippage_bps = calculate_slippage(filled_price, arrival_price) if filled_price else None

            if price > 0:
                await notify_exit(self.symbol, "sell", self._position_qty, price, pnl)

            # Registrar trade en DB (con TCA)
            if self._db and self._db.is_connected and self._last_entry_at:
                await self._db.insert_trade({
                    "symbol": self.symbol,
                    "side": "long",
                    "entry_price": self._last_entry_price,
                    "exit_price": price,
                    "qty": self._position_qty,
                    "pnl": pnl,
                    "entry_order_id": self._last_entry_order_id,
                    "exit_order_id": self._get_order_id(exit_result),
                    "entry_at": self._last_entry_at,
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
            self._position = None
            self._position_qty = 0

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
                logger.debug("Error deteniendo SMAStrategy: %s", e)

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
                        logger.debug("Signal recibida: %s %s", msg_id, fields)
                        await self._execute_signal(fields)
                        await self._redis.xack(SIGNALS_STREAM, CONSUMER_GROUP, msg_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error en main loop: %s", e, exc_info=True)
                await notify_error(str(e))
                await asyncio.sleep(5)

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
        logger.info("🔄 MODO LEGACY ACTIVO — polling cada %ds", poll_interval)
        logger.info("  Risk manager:    ACTIVO")
        logger.info("  Alertas Telegram: ACTIVAS")
        logger.info("  TWAP:             %s", "ACTIVO" if self.twap_enabled else "INACTIVO")
        logger.info("=" * 50)
        await send_telegram_message_async(
            f"ℹ️ <b>LEGACY FALLBACK</b>\n"
            f"RoyalTDN en modo LEGACY — REST polling c/{poll_interval}s\n"
            f"Símbolo: {self.symbol} SMA{self.sma_fast}/{self.sma_slow}\n"
            f"Risk manager activo — alertas en tiempo real reducido"
        )

        while self._running and not self._killed:
            try:
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
                    logger.info("Señal legacy: %s %s @ %.2f", self.symbol, action, closes[-1])
                    await self._execute_signal(signal)

            except asyncio.CancelledError:
                break
            except Exception as e:
                err_str = f"{e}"
                # No alarmar por errores esperados fuera de mercado
                if "429" in err_str:
                    logger.warning("Rate limit Alpaca — esperando %ds", poll_interval)
                elif "401" in err_str or "403" in err_str:
                    logger.error("Auth error en legacy loop: %s", err_str)
                    await notify_error(f"Auth error en legacy mode: {err_str}")
                    await asyncio.sleep(poll_interval * 3)
                    continue
                else:
                    logger.warning("Error en legacy loop: %s", err_str)
                await asyncio.sleep(poll_interval)

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
                logger.error("Error lanzando tareas: %s\n%s", e, traceback.format_exc())
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

        # Detener estrategia
        if self._strategy:
            try:
                self._strategy.stop()
                logger.info("SMAStrategy detenido")
            except Exception as e:
                logger.debug("Error deteniendo SMAStrategy: %s", e)

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
                logger.debug("Error deteniendo DataIngestor: %s", e)

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
            logger.info("  Capital inicial: $%.2f", self._initial_equity)
            logger.info("  Capital final:   $%.2f", final_equity)
            logger.info("  P&L total:       $%.2f", pnl_total)
            logger.info("  Trades:          %d", self._trades_count)
            logger.info("  Losses seguidas: %d", self._consecutive_losses)
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
