#!/usr/bin/env python3
"""RoyalTDN — TWAP Execution Engine (Time-Weighted Average Price)

Fase 4, Bloque 4 (documento 6, sección 6.4.3)

Divide órdenes grandes en lotes más pequeños ejecutados a intervalos
regulares para minimizar el impacto de mercado.

Estrategia:
  - Orden madre de ``total_shares`` se divide en ``N = duration_minutes``
    lotes iguales (o casi).
  - Cada lote se envía cada 60 segundos como orden de mercado.
  - Si ``use_limit=True``, se usa el midpoint (bid+ask)/2 como precio límite.

Uso:
    from royaltdn.execution.twap import execute_twap

    orders = await execute_twap("SPY", 500, 10, OrderSide.BUY, trading_client)
"""

import asyncio
import logging
import math
from datetime import datetime
from typing import List, Optional

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

logger = logging.getLogger("royaltdn.twap")


async def get_midpoint(
    symbol: str,
    api_key: str,
    secret_key: str,
    feed: str = "iex",
) -> Optional[float]:
    """Obtiene el midpoint (bid+ask)/2 de la última cotización.

    Args:
        symbol: Símbolo (ej: "SPY").
        api_key: Alpaca API key.
        secret_key: Alpaca secret key.
        feed: Feed de datos (default "iex").

    Returns:
        float: Precio midpoint, o None si no hay cotización.
    """
    loop = asyncio.get_running_loop()
    data_client = StockHistoricalDataClient(api_key, secret_key)

    def _fetch():
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=feed)
        quotes = data_client.get_stock_latest_quote(req)
        quote = quotes.get(symbol)
        if quote and quote.bid_price > 0 and quote.ask_price > 0:
            return (quote.bid_price + quote.ask_price) / 2
        return None

    return await loop.run_in_executor(None, _fetch)


async def execute_twap(
    symbol: str,
    total_shares: int,
    duration_minutes: int,
    side: OrderSide,
    trading_client: TradingClient,
    api_key: str = "",
    secret_key: str = "",
    use_limit: bool = False,
    feed: str = "iex",
    dry_run: bool = False,
) -> List[dict]:
    """Ejecuta una orden madre usando TWAP.

    Args:
        symbol: Símbolo a tradear.
        total_shares: Cantidad total de acciones a comprar/vender.
        duration_minutes: Duración del TWAP en minutos.
        side: OrderSide.BUY o OrderSide.SELL.
        trading_client: Cliente de trading Alpaca (sincrónico).
        api_key: Necesario si use_limit=True (para obtener quotes).
        secret_key: Necesario si use_limit=True.
        use_limit: Usar órdenes límite al midpoint (default: mercado).
        feed: Feed de datos (default "iex").
        dry_run: Si True, solo registra sin enviar órdenes.

    Returns:
        List[dict]: Lista de resultados por lote:
            {"chunk": N, "shares": int, "order_id": str|None,
             "price": float|None, "error": str|None}
    """
    if total_shares <= 0 or duration_minutes <= 0:
        logger.warning("TWAP: shares=%d, duration=%d — inválido", total_shares, duration_minutes)
        return []

    # Calcular tamaño de cada lote
    chunks = min(duration_minutes, total_shares)
    shares_per_chunk = math.ceil(total_shares / chunks)
    results: List[dict] = []

    logger.info(
        "🧠 TWAP: %s %d %s en %d min (%d lotes de ~%d acc)",
        side.name, total_shares, symbol, duration_minutes, chunks, shares_per_chunk,
    )

    remaining = total_shares

    for chunk_num in range(1, chunks + 1):
        if remaining <= 0:
            break

        chunk_shares = min(shares_per_chunk, remaining)

        if use_limit:
            midpoint = await get_midpoint(symbol, api_key, secret_key, feed)
            if midpoint is None:
                logger.warning("Sin midpoint — usando market order para lote %d", chunk_num)
                order = _submit_market(trading_client, symbol, chunk_shares, side)
                price = None
            else:
                order = _submit_limit(trading_client, symbol, chunk_shares, side, midpoint)
                price = midpoint
        else:
            order = _submit_market(trading_client, symbol, chunk_shares, side)
            price = None

        order_id = order.id if order and hasattr(order, "id") else None

        result = {
            "chunk": chunk_num,
            "shares": chunk_shares,
            "order_id": order_id,
            "price": price,
        }
        results.append(result)
        remaining -= chunk_shares

        logger.info(
            "  Lote %d/%d: %s %d %s → ID=%s",
            chunk_num, chunks, side.name, chunk_shares, symbol, order_id,
        )

        # Esperar al siguiente minuto si no es el último lote
        if chunk_num < chunks and remaining > 0:
            await asyncio.sleep(60)

    logger.info(
        "✅ TWAP completado: %d/%d acciones ejecutadas en %d lotes",
        total_shares - remaining, total_shares, len(results),
    )
    return results


def _submit_market(
    client: TradingClient,
    symbol: str,
    qty: int,
    side: OrderSide,
) -> object:
    """Envía una orden de mercado."""
    return client.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
    )


def _submit_limit(
    client: TradingClient,
    symbol: str,
    qty: int,
    side: OrderSide,
    limit_price: float,
) -> object:
    """Envía una orden límite."""
    return client.submit_order(
        LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            limit_price=round(limit_price, 2),
            time_in_force=TimeInForce.DAY,
        )
    )
