"""
RoyalTDN — LiquidityFilter: filtro de liquidez para el scanner

Fase 5.6 — Filtro de Liquidez

Filtra símbolos por:
- Volumen mínimo
- Precio mínimo
- Spread máximo (opcional)
"""

from typing import List, Any

from loguru import logger


class LiquidityFilter:
    """Filtra símbolos por criterios de liquidez.

    Usa Alpaca data_client.get_latest_bar() para obtener la última
    barra de cada símbolo y verifica volumen, precio y spread.
    """

    def __init__(
        self,
        min_volume: int = 500_000,
        min_price: float = 5.0,
        max_spread_pct: float = 0.5,
    ):
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_spread_pct = max_spread_pct

    def filter(self, symbols: List[str], data_client: Any) -> List[str]:
        """Filtra lista de símbolos por liquidez.

        Args:
            symbols: Lista de símbolos a filtrar.
            data_client: Instancia de StockHistoricalDataClient de alpaca-py.

        Returns:
            Lista de símbolos que pasan el filtro.
        """
        if not symbols:
            return []

        passed = []
        from tqdm import tqdm
        import sys

        for symbol in tqdm(
            symbols,
            desc="Filtrando por liquidez",
            unit="sym",
            file=sys.stdout,
            bar_format="{desc}: {n}/{total} — {percentage:.0f}% completado. ~{remaining}",
        ):
            try:
                bar = data_client.get_latest_bar(symbol)

                # Verificar que la barra existe y tiene datos
                if bar is None:
                    continue

                volume = getattr(bar, "volume", None)
                close = getattr(bar, "close", None)

                # Filtro de volumen
                if volume is None or volume < self.min_volume:
                    continue

                # Filtro de precio
                if close is None or close < self.min_price:
                    continue

                # Filtro de spread (si está disponible en la barra)
                # Alpaca Bar no siempre tiene bid/ask en get_latest_bar
                # Solo filtrar si los datos están disponibles
                bid = getattr(bar, "bid_price", None)
                ask = getattr(bar, "ask_price", None)
                if bid is not None and ask is not None and bid > 0 and ask > 0:
                    spread_pct = ((ask - bid) / ((ask + bid) / 2)) * 100
                    if spread_pct > self.max_spread_pct:
                        continue

                passed.append(symbol)

            except Exception:
                # Silenciosamente saltar símbolos que fallen
                continue

        logger.info("LiquidityFilter: {}/{} símbolos pasaron", len(passed), len(symbols))
        return passed
