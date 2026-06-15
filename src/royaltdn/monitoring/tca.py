#!/usr/bin/env python3
"""RoyalTDN — Transaction Cost Analysis (TCA)

Fase 4, Bloque 5 (documento 6, sección 6.4.5)

Mide el slippage entre el precio de decisión (arrival price) y el
precio real de ejecución. El slippage se expresa en basis points (bps).

Fórmula:
    slippage_bps = (execution_price - arrival_price) / arrival_price * 10_000

Usos:
    - Evaluar calidad de ejecución (TWAP vs mercado directa).
    - Detectar problemas de liquidez.
    - Ajustar parámetros de ejecución.

Uso:
    from royaltdn.monitoring.tca import calculate_slippage

    slippage = calculate_slippage(fill_price=150.50, arrival_price=150.00)
    # → 33.33 bps (0.33% de deslizamiento)
"""

import logging
from typing import Optional

logger = logging.getLogger("royaltdn.tca")


def calculate_slippage(
    execution_price: float,
    arrival_price: float,
) -> Optional[float]:
    """Calcula el slippage en basis points (bps) entre el precio de
    ejecución y el precio de llegada (arrival price).

    Args:
        execution_price: Precio medio real de la ejecución (filled_avg_price).
        arrival_price: Precio de mercado en el momento de la decisión
            (último tick antes de enviar la orden).

    Returns:
        float: Slippage en bps (1 bps = 0.01%). Positivo = peor precio
        para el comprador (más caro), negativo = mejor precio.
        None si alguno de los precios es inválido.
    """
    if not arrival_price or arrival_price <= 0:
        logger.debug("Arrival price inválido: %s", arrival_price)
        return None

    if not execution_price or execution_price <= 0:
        logger.debug("Execution price inválido: %s", execution_price)
        return None

    slippage = (execution_price - arrival_price) / arrival_price * 10_000
    logger.debug("Slippage: %.2f bps (exec=%.2f, arrival=%.2f)", slippage, execution_price, arrival_price)
    return round(slippage, 2)
