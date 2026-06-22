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


def _calc_gap(value: float, threshold: float, direction: str) -> float:
    """Calcula el gap porcentual entre un valor y su umbral.

    Args:
        value: Valor real.
        threshold: Umbral de referencia.
        direction: ``"above"`` si la condición es value >= threshold,
                   ``"below"`` si la condición es value <= threshold.

    Returns:
        0.0 si la condición ya se cumple (met).
        Porcentaje absoluto de distancia si no se cumple.
    """
    if direction == "above":
        if value >= threshold:
            return 0.0
        return abs((value - threshold) / threshold) * 100 if threshold != 0 else 0.0
    else:  # below
        if value <= threshold:
            return 0.0
        return abs((value - threshold) / threshold) * 100 if threshold != 0 else 0.0


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

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explica por qué se generó (o no) una señal de trading.

        Método concreto (NO abstract) para compatibilidad hacia atrás.
        Las estrategias pueden sobrescribirlo para devolver explicaciones
        detalladas con indicadores, condiciones y señal.

        Args:
            data: DataFrame OHLCV con al menos columna ``close``.
            symbol: Opcional. Símbolo del activo, usado para resolución
                    de perfiles (crypto vs stocks).

        Returns:
            Dict con la estructura:
                {
                    "indicators": {},        # dict con valores calculados
                    "conditions": [],        # lista de condition dicts
                    "signal": None,          # dict de señal o None
                }

            Cada condition dict tiene:
                {
                    "name": str,             # nombre legible de la condición
                    "met": bool,             # True si la condición se cumple
                    "value": float,          # valor real
                    "threshold": float,      # umbral de referencia
                    "gap_pct": float,        # gap % (0.0 si met=True)
                    "direction": str,        # "above" | "below"
                }

            signal dict (cuando hay señal):
                {
                    "action": "BUY" | "SELL",
                    "price": float,
                    "reason": str,
                }
        """
        return {"indicators": {}, "conditions": [], "signal": None}

    def validate(self) -> bool:
        """Valida que la configuración de la estrategia sea correcta.

        Returns:
            True si la configuración es válida, False en caso contrario.
        """
        return True
