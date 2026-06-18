#!/usr/bin/env python3
"""RoyalTDN — Motor de Estrategia SMA Crossover sobre Redis Streams

Fase 4, Bloque 2 — Consumidor de barras, generador de señales
(documento 6, sección 6.4.4)

Lee barras del stream ``market_bars`` (publicadas por DataIngestor),
calcula SMA5/SMA20 en tiempo real y publica señales BUY/SELL en el
stream ``signals`` cuando detecta cruces.

Uso standalone:
    python -m royaltdn.strategy.sma_strategy

Uso desde el bot (tarea asyncio):
    task = asyncio.create_task(strategy.run())
"""

import os
import json
import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
import pandas as pd
import redis.asyncio as aioredis

from royaltdn.strategy.base import BaseStrategy

# ── Cálculo de SMA (puro, sin dependencias externas) ──────────────────


def compute_sma(prices: List[float], window: int) -> Optional[float]:
    """Media simple de los últimos ``window`` precios."""
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def detect_cross(
    prev_fast: Optional[float],
    prev_slow: Optional[float],
    curr_fast: float,
    curr_slow: float,
) -> Optional[str]:
    """Detecta cruce entre SMA rápida y lenta.

    Retorna ``"BUY"`` si la rápida CRUZA ARRIBA de la lenta,
    ``"SELL"`` si CRUZA ABAJO, o ``None`` si no hay cruce.

    El primer cálculo (previos == None) no genera señal.
    """
    if prev_fast is None or prev_slow is None:
        return None  # todavía no hay referencia

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "BUY"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "SELL"
    return None


# ── Motor de estrategia ──────────────────────────────────────────────


class SMAStrategy(BaseStrategy):
    """Consume barras de ``market_bars`` y publica señales en ``signals``.

    Configuración por defecto: SMA5 y SMA20 sobre el símbolo SPY.
    Hereda de BaseStrategy e implementa generate_signal() para uso
    con DataFrames (backtesting/scanner) además del streaming vía Redis.
    """

    INPUT_STREAM = "market_bars"
    OUTPUT_STREAM = "signals"
    CONSUMER_GROUP = "strategy-engine"
    CONSUMER_NAME = "sma-strategy"
    POLL_TIMEOUT_MS = 5000  # 5s — permite detectar stop limpio

    def __init__(
        self,
        redis_url: str = None,
        symbol: str = "SPY",
        sma_fast: int = 5,
        sma_slow: int = 20,
        timeframe: str = "1d",
    ):
        super().__init__(timeframe=timeframe)
        self.redis_url = redis_url
        self.symbol = symbol
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow

        # Buffer circular: guardamos hasta SMA_SLOW precios de cierre
        self._prices: deque = deque(maxlen=sma_slow)

        # Últimos valores de SMA para detectar cruce
        self._prev_fast: Optional[float] = None
        self._prev_slow: Optional[float] = None

        # Última acción publicada (para no duplicar señales)
        self._last_action: Optional[str] = None

        self._redis: aioredis.Redis | None = None
        self._running = False

    # ── Propiedades ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "sma_crossover"

    # ── Implementación BaseStrategy ─────────────────────────────────────

    def generate_signal(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Genera señal a partir de un DataFrame OHLCV.

        Usa el cierre (``close``) para calcular SMA rápida y lenta,
        y detecta el cruce entre el valor actual y el anterior.

        Args:
            data: DataFrame con columna ``close`` (obligatorio).

        Returns:
            Dict con action, price y metadata, o None si no hay señal.
        """
        if "close" not in data.columns:
            logger.warning("generate_signal: faltan columnas (close)")
            return None

        closes = data["close"].dropna().tolist()
        if len(closes) < self.sma_slow:
            return None

        # Valores actuales
        curr_fast = compute_sma(closes, self.sma_fast)
        curr_slow = compute_sma(closes, self.sma_slow)

        if curr_fast is None or curr_slow is None:
            return None

        # Valores previos (para detectar cruce)
        prev_fast = compute_sma(closes[:-1], self.sma_fast)
        prev_slow = compute_sma(closes[:-1], self.sma_slow)

        action = detect_cross(prev_fast, prev_slow, curr_fast, curr_slow)
        if action is None:
            return None

        return {
            "action": action,
            "price": float(closes[-1]),
            "metadata": {
                "sma_fast": round(curr_fast, 2),
                "sma_slow": round(curr_slow, 2),
                "fast_period": self.sma_fast,
                "slow_period": self.sma_slow,
            },
        }

    def get_parameters(self) -> Dict[str, Any]:
        """Retorna los parámetros actuales de la estrategia."""
        return {
            "fast_period": self.sma_fast,
            "slow_period": self.sma_slow,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }

    def validate(self) -> bool:
        """Valida que SMA rápida < SMA lenta y ambos > 0."""
        if self.sma_fast <= 0 or self.sma_slow <= 0:
            logger.error("SMAStrategy: periods deben ser > 0")
            return False
        if self.sma_fast >= self.sma_slow:
            logger.error(
                "SMAStrategy: fast_period (%d) debe ser < slow_period (%d)",
                self.sma_fast, self.sma_slow,
            )
            return False
        return True

    # ── Procesamiento de barra (streaming) ─────────────────────────────

    def process_bar(self, bar: dict) -> Optional[Dict]:
        """Procesa una barra y retorna una señal si hay cruce.

        Método público y **puro** (no toca Redis) — ideal para tests.

        ``bar`` debe tener al menos ``close`` (str o float).
        Es el equivalente a generate_signal() para streaming bar-a-bar.
        """
        close = float(bar["close"])
        self._prices.append(close)

        prices = list(self._prices)
        curr_fast = compute_sma(prices, self.sma_fast)
        curr_slow = compute_sma(prices, self.sma_slow)

        if curr_fast is None or curr_slow is None:
            return None  # buffer todavía insuficiente

        action = detect_cross(self._prev_fast, self._prev_slow, curr_fast, curr_slow)

        # Actualizar estado
        self._prev_fast = curr_fast
        self._prev_slow = curr_slow

        if action is None or action == self._last_action:
            return None  # mismo estado, no repetir señal

        self._last_action = action
        return {
            "symbol": bar.get("symbol", self.symbol),
            "action": action,
            "price": close,
            "sma_fast": round(curr_fast, 2),
            "sma_slow": round(curr_slow, 2),
            "timestamp": bar.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }

    # ── Redis ───────────────────────────────────────────────────────────

    async def _connect_redis(self) -> bool:
        """Conecta a Redis y crea el consumer group si no existe."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Conectado a Redis: {}", self.redis_url)

            # Crear consumer group (ignora si ya existe)
            try:
                await self._redis.xgroup_create(
                    self.INPUT_STREAM,
                    self.CONSUMER_GROUP,
                    id="$",     # solo mensajes nuevos
                    mkstream=True,
                )
                logger.info(
                    "Consumer group '{}' creado en '{}'",
                    self.CONSUMER_GROUP,
                    self.INPUT_STREAM,
                )
            except aioredis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.debug("Consumer group ya existe")
                else:
                    raise

            return True
        except Exception as e:
            logger.error("Error conectando a Redis: {}", e)
            self._redis = None
            return False

    async def _publish_signal(self, signal: dict) -> None:
        """Publica una señal en el stream ``signals``."""
        if not self._redis:
            return
        try:
            # Redis Streams requiere valores string
            data = {k: str(v) for k, v in signal.items()}
            msg_id = await self._redis.xadd(
                self.OUTPUT_STREAM,
                data,
                maxlen=10_000,
                approximate=True,
            )
            logger.info(
                "🚦 SEÑAL {} {} @ {:.2f} → {}",
                signal["action"],
                signal["symbol"],
                signal["price"],
                msg_id,
            )
        except Exception as e:
            logger.error("Error publicando señal: {}", e)

    # ── Loop principal ──────────────────────────────────────────────────

    async def run(self):
        """Loop asíncrono: lee barras de Redis, calcula señales."""
        if not self.validate():
            logger.error("SMAStrategy no pasó validación — abortando")
            return

        if not await self._connect_redis():
            logger.error("No se pudo conectar a Redis — abortando")
            return

        self._running = True
        logger.info(
            "SMAStrategy iniciada: {} SMA{}/{}",
            self.symbol,
            self.sma_fast,
            self.sma_slow,
        )

        try:
            while self._running:
                try:
                    # Leer lotes de barras (BLOCK 0 = espera indefinida)
                    result = await self._redis.xreadgroup(
                        groupname=self.CONSUMER_GROUP,
                        consumername=self.CONSUMER_NAME,
                        streams={self.INPUT_STREAM: ">"},
                        count=10,
                        block=self.POLL_TIMEOUT_MS,
                    )

                    if not result:
                        continue  # timeout sin datos

                    # result es [(stream, [(msg_id, {fields}), ...]), ...]
                    for stream_name, messages in result:
                        for msg_id, fields in messages:
                            await self._process_and_ack(msg_id, fields)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error en loop principal: {}", e)
                    await asyncio.sleep(1)
        finally:
            await self._cleanup()

    async def _process_and_ack(self, msg_id: str, fields: dict) -> None:
        """Procesa una barra y hace ACK en Redis."""
        # Filtrar solo el símbolo que nos interesa
        if fields.get("symbol") != self.symbol:
            await self._redis.xack(self.INPUT_STREAM, self.CONSUMER_GROUP, msg_id)
            return

        signal = self.process_bar(fields)
        if signal:
            await self._publish_signal(signal)

        await self._redis.xack(self.INPUT_STREAM, self.CONSUMER_GROUP, msg_id)

    async def _cleanup(self):
        """Cierra conexiones."""
        if self._redis:
            await self._redis.close()
        logger.info("SMAStrategy detenida.")

    # ── Interfaz pública ───────────────────────────────────────────────

    def stop(self):
        """Detiene el motor (thread-safe)."""
        self._running = False


# ── Entry point standalone ────────────────────────────────────────────


def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    symbol = os.getenv("STRATEGY_SYMBOL", "SPY")

    logger.info("Arrancando SMAStrategy para {}...", symbol)
    engine = SMAStrategy(redis_url=redis_url, symbol=symbol)

    async def _run():
        await engine.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Detenido por usuario.")


if __name__ == "__main__":
    main()
