#!/usr/bin/env python3
"""RoyalTDN — Data Ingestor con Alpaca WebSocket + Redis Streams

Fase 4, Bloque 1 — Arquitectura modular (documento 6, sección 6.4.4)
Documento 3, sección 3.1.4 — Ingestión de datos en tiempo real

Se conecta al WebSocket de Alpaca, recibe barras de 1 minuto y las
publica en un stream de Redis llamado ``market_bars``.

Uso standalone:
    python -m royaltdn.ingestion.data_ingestor

Uso desde el bot (thread):
    thread = DataIngestor.as_thread(api_key, secret_key, redis_url)
    thread.start()
"""

import os
import sys
import asyncio
import logging
import traceback
from threading import Thread
from typing import List, Optional

from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed
import redis.asyncio as aioredis

logger = logging.getLogger("royaltdn.ingestor")


class DataIngestor:
    """Ingiere barras de 1 minuto desde Alpaca y las publica en Redis Streams.

    Normaliza cada barra a:
        {symbol, timestamp, open, high, low, close, volume}

    Las publica en el stream ``market_bars`` con un maxlen de 10.000
    (suficiente para ~7 días de trading en un símbolo).
    """

    STREAM_KEY = "market_bars"
    MAXLEN = 10_000

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        redis_url: str,
        symbols: Optional[List[str]] = None,
        feed: str = "iex",
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.redis_url = redis_url
        self.symbols = symbols or ["SPY"]

        # Normalizar feed: acepta string o enum
        if isinstance(feed, str):
            try:
                self.feed = DataFeed(feed)
            except ValueError:
                logger.warning("Feed '%s' no reconocido, usando IEX", feed)
                self.feed = DataFeed.IEX
        else:
            self.feed = feed

        self._redis: Optional[aioredis.Redis] = None
        self._stream: Optional[StockDataStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Callback de Alpaca ──────────────────────────────────────────────

    async def _handle_bar(self, bar) -> None:
        """Recibe una Bar de Alpaca y la publica en Redis Stream."""
        try:
            # Soporta tanto Bar object como dict (raw_data)
            if isinstance(bar, dict):
                data = {
                    "symbol": bar.get("symbol", ""),
                    "timestamp": str(bar.get("timestamp", "")),
                    "open": str(bar.get("open", 0)),
                    "high": str(bar.get("high", 0)),
                    "low": str(bar.get("low", 0)),
                    "close": str(bar.get("close", 0)),
                    "volume": str(int(bar.get("volume", 0))),
                }
            else:
                data = {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp.isoformat(),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(int(bar.volume)),
                }

            if not self._redis:
                return

            msg_id = await self._redis.xadd(
                self.STREAM_KEY,
                data,
                maxlen=self.MAXLEN,
                approximate=True,
            )
            logger.debug("Bar %s %s -> %s", data["symbol"], data["timestamp"], msg_id)

        except Exception as e:
            logger.error("Error procesando barra: %s\n%s", e, traceback.format_exc())

    # ── Conexión Redis ──────────────────────────────────────────────────

    async def _connect_redis(self) -> bool:
        """Conecta a Redis. Retorna True si funciona."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Conectado a Redis: %s", self.redis_url)
            return True
        except Exception as e:
            logger.warning("Redis no disponible (%s) — funciona sin persistencia", e)
            self._redis = None
            return False

    # ── Arranque ────────────────────────────────────────────────────────

    async def _run_async(self):
        """Loop principal asíncrono."""
        self._loop = asyncio.get_running_loop()

        # Conectar Redis (falla suave — sigue sin persistencia)
        await self._connect_redis()

        # ── Configurar WebSocket Alpaca ──
        logger.info(
            "Iniciando StockDataStream(feed=%s, raw_data=False, symbols=%s)",
            self.feed.value if hasattr(self.feed, 'value') else self.feed,
            self.symbols,
        )
        try:
            self._stream = StockDataStream(
                api_key=self.api_key,
                secret_key=self.secret_key,
                feed=self.feed,
                raw_data=False,
            )

            self._stream.subscribe_bars(self._handle_bar, *self.symbols)
            logger.info(
                "Ingestor iniciado: %d símbolo(s) en feed '%s'",
                len(self.symbols),
                self.feed.value if hasattr(self.feed, 'value') else self.feed,
            )

            # run() es blocking — llama a _run_forever internamente
            try:
                self._stream.run()
            except RuntimeError as e:
                # Posible nested asyncio.run — intentar con _run_forever directo
                if "cannot be called from a running event loop" in str(e):
                    logger.warning("Nested event loop detected, using _run_forever directly")
                    if hasattr(self._stream, '_run_forever'):
                        await self._stream._run_forever()
                    else:
                        raise
                else:
                    raise

        except Exception as e:
            logger.error(
                "Error fatal en ingestor: %s\n%s",
                e, traceback.format_exc(),
            )
            raise

        finally:
            await self._cleanup()

    async def _cleanup(self):
        """Cierra conexiones."""
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("Ingestor detenido.")

    def start(self):
        """Arranca el ingestor (bloqueante)."""
        asyncio.run(self._run_async())

    def stop(self):
        """Detiene el WebSocket desde otro hilo."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception as e:
                logger.debug("Error al detener stream: %s", e)

    # ── Modo thread-friendly ────────────────────────────────────────────

    @classmethod
    def as_thread(
        cls,
        api_key: str,
        secret_key: str,
        redis_url: str,
        symbols: Optional[List[str]] = None,
        feed: str = "iex",
    ) -> Thread:
        """Retorna un Thread que corre el ingestor."""
        ingestor = cls(api_key, secret_key, redis_url, symbols, feed)

        def _run():
            try:
                ingestor.start()
            except Exception as e:
                logger.error("Ingestor thread murió: %s\n%s", e, traceback.format_exc())

        thread = Thread(target=_run, name="data-ingestor", daemon=True)
        thread.ingestor = ingestor  # type: ignore[attr-defined]
        return thread


# ── Entry point standalone ────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.setLevel(logging.DEBUG)

    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    symbols_raw = os.getenv("INGESTOR_SYMBOLS", "SPY,QQQ,IWM")
    symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]
    feed = os.getenv("ALPACA_FEED", "iex")

    if not api_key or not secret_key:
        logger.error(
            "Faltan ALPACA_API_KEY / ALPACA_SECRET_KEY. Configuralas en .env"
        )
        sys.exit(1)

    logger.info("Arrancando DataIngestor: feed=%s symbols=%s", feed, symbols)
    ingestor = DataIngestor(api_key, secret_key, redis_url, symbols, feed)

    try:
        ingestor.start()
    except KeyboardInterrupt:
        logger.info("Detenido por usuario.")
    except Exception as e:
        logger.error("Error fatal: %s\n%s", e, traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
