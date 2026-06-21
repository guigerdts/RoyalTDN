"""
RoyalTDN — BaseStrategy: clase base abstracta para todas las estrategias

Fase 5.1 — Common Strategy Interface (documento de diseño)

Define el contrato que toda estrategia debe cumplir:
  - generate_signal(data)  → señal o None
  - get_parameters()       → dict con parámetros actuales
  - validate()             → validez de la configuración
  - name                   → identificador único
  - timeframe              → resolución por defecto
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import pandas as pd


class BaseStrategy(ABC):
    """Clase base abstracta para estrategias de trading.

    Toda estrategia concreta debe implementar:
      - generate_signal()
      - get_parameters()
      - name (property)

    Ejemplo de uso:
        class MyStrategy(BaseStrategy):
            @property
            def name(self) -> str:
                return "my_strategy"

            def generate_signal(self, data: pd.DataFrame) -> Optional[dict]:
                ...

            def get_parameters(self) -> dict:
                ...
    """

    def __init__(self, timeframe: str = "1d", category: str = "swing"):
        self.timeframe = timeframe
        self._category = category

    # ── Propiedades obligatorias ────────────────────────────────────────

    @property
    def category(self) -> str:
        """Categoría de la estrategia (ej: 'swing', 'intraday')."""
        return self._category

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre único de la estrategia (ej: 'sma_crossover', 'rsi_reversal')."""
        ...

    # ── Métodos abstractos ──────────────────────────────────────────────

    @abstractmethod
    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Genera una señal de trading a partir de un DataFrame OHLCV.

        Args:
            data: DataFrame con columnas ``open``, ``high``, ``low``,
                  ``close``, ``volume`` (al menos ``close`` es obligatorio).
                  Puede contener más columnas (depende de la estrategia).
            symbol: Opcional. Símbolo del activo, usado para resolver
                    perfiles de parámetros (crypto vs stocks).

        Returns:
            Dict con la estructura:
                {
                    "action": "BUY" | "SELL",
                    "price": float,          # precio de referencia
                    "metadata": {...}         # info adicional (opcional)
                }
            o None si no hay señal en este momento.
        """
        ...

    def get_parameters(self) -> Dict[str, Any]:
        """Retorna los parámetros actuales de la estrategia.

        Returns:
            Dict serializable con todos los parámetros,
            ej: {"fast_period": 5, "slow_period": 20}
        """
        return {"timeframe": self.timeframe, "category": self._category}

    # ── Métodos con implementación por defecto ─────────────────────────

    def validate(self) -> bool:
        """Valida que la configuración de la estrategia sea correcta.

        Returns:
            True si la configuración es válida, False en caso contrario.
        """
        return True
