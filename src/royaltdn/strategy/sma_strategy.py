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
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import redis.asyncio as aioredis

logger = logging.getLogger("royaltdn.strategy.sma")

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


class SMAStrategy:
    """Consume barras de ``market_bars`` y publica señales en ``signals``.

    Configuración por defecto: SMA5 y SMA20 sobre el símbolo SPY.
    """

    INPUT_STREAM = "market_bars"
    OUTPUT_STREAM = "signals"
    CONSUMER_GROUP = "strategy-engine"
    CONSUMER_NAME = "sma-strategy"
    POLL_TIMEOUT_MS = 5000  # 5s — permite detectar stop limpio

    def __init__(
        self,
        redis_url: str,
        symbol: str = "SPY",
        sma_fast: int = 5,
        sma_slow: int = 20,
    ):
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

    # ── Procesamiento de barra ──────────────────────────────────────────

    def process_bar(self, bar: dict) -> Optional[Dict]:
        """Procesa una barra y retorna una señal si hay cruce.

        Método público y **puro** (no toca Redis) — ideal para tests.

        ``bar`` debe tener al menos ``close`` (str o float).
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
            logger.info("Conectado a Redis: %s", self.redis_url)

            # Crear consumer group (ignora si ya existe)
            try:
                await self._redis.xgroup_create(
                    self.INPUT_STREAM,
                    self.CONSUMER_GROUP,
                    id="$",     # solo mensajes nuevos
                    mkstream=True,
                )
                logger.info(
                    "Consumer group '%s' creado en '%s'",
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
            logger.error("Error conectando a Redis: %s", e)
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
                "🚦 SEÑAL %s %s @ %.2f → %s",
                signal["action"],
                signal["symbol"],
                signal["price"],
                msg_id,
            )
        except Exception as e:
            logger.error("Error publicando señal: %s", e)

    # ── Loop principal ──────────────────────────────────────────────────

    async def run(self):
        """Loop asíncrono: lee barras de Redis, calcula señales."""
        if not await self._connect_redis():
            logger.error("No se pudo conectar a Redis — abortando")
            return

        self._running = True
        logger.info(
            "SMAStrategy iniciada: %s SMA%s/%s",
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
                    logger.error("Error en loop principal: %s", e)
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.setLevel(logging.DEBUG)

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    symbol = os.getenv("STRATEGY_SYMBOL", "SPY")

    logger.info("Arrancando SMAStrategy para %s...", symbol)
    engine = SMAStrategy(redis_url=redis_url, symbol=symbol)

    async def _run():
        await engine.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Detenido por usuario.")


if __name__ == "__main__":
    main()
