"""
RoyalTDN — FactorRotationStrategy: rotación mensual de ETFs

Fase 5.5 — Estrategia 3

Calcula un score de momentum / volatilidad (Sharpe simplificado) para
cada ETF del universo. La señal "RANK" incluye el score en metadata
para que el scanner/orchestrador decida el ranking.

Indicadores calculados con pandas (sin dependencias externas).
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from royaltdn.strategy.base import BaseStrategy

logger = logging.getLogger("royaltdn.strategy.factor_rotation")


class FactorRotationStrategy(BaseStrategy):
    """Rotación mensual de ETFs sectoriales por momentum/volatilidad.

    Para cada símbolo, calcula:
      - momentum: retorno de momentum_period días
      - volatility: desviación estándar de retornos diarios
      - score = momentum / volatility (Sharpe simplificado)

    La señal "RANK" incluye el score en metadata. El scanner es
    responsable de rankear los activos y decidir compra/venta.
    """

    def __init__(
        self,
        etf_universe: Optional[List[str]] = None,
        momentum_period: int = 126,
        volatility_period: int = 20,
        top_n: int = 3,
        rebalance_day: int = 1,
        timeframe: str = "1d",
    ):
        super().__init__(timeframe=timeframe)
        self.etf_universe = etf_universe or [
            "XLF", "XLE", "XLK", "XLV", "XLI",
            "XLP", "XLY", "XLB", "XLU", "XRT",
        ]
        self.momentum_period = momentum_period
        self.volatility_period = volatility_period
        self.top_n = top_n
        self.rebalance_day = rebalance_day

    # ── Propiedades ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "factor_rotation"

    # ── BaseStrategy ────────────────────────────────────────────────────

    def generate_signal(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Calcula score de momentum/volatilidad para un símbolo.

        Args:
            data: DataFrame con columna ``close``.

        Returns:
            Dict con action="RANK", price y metadata con score,
            o None si datos insuficientes.
        """
        if "close" not in data.columns:
            logger.warning("generate_signal: faltan columnas (close)")
            return None

        close = data["close"]
        need = self.momentum_period + 1
        if len(close) < need:
            return None  # datos insuficientes

        # Momentum: retorno de momentum_period días
        momentum = (close.iloc[-1] / close.iloc[-self.momentum_period]) - 1

        # Volatilidad: std de retornos diarios
        daily_returns = close.pct_change().dropna()
        vol = daily_returns.iloc[-self.volatility_period:].std()

        # Score Sharpe simplificado
        score = momentum / vol if vol > 0 else 0.0

        last_close = float(close.iloc[-1])
        last_momentum = float(momentum)
        last_vol = float(vol)
        last_score = float(score)

        return {
            "action": "RANK",
            "price": last_close,
            "metadata": {
                "momentum": round(last_momentum * 100, 2),
                "volatility": round(last_vol * 100, 2),
                "score": round(last_score, 4),
                "momentum_period": self.momentum_period,
                "volatility_period": self.volatility_period,
            },
        }

    def get_parameters(self) -> Dict[str, Any]:
        """Retorna los parámetros actuales."""
        return {
            "etf_universe": self.etf_universe,
            "momentum_period": self.momentum_period,
            "volatility_period": self.volatility_period,
            "top_n": self.top_n,
            "rebalance_day": self.rebalance_day,
            "timeframe": self.timeframe,
        }

    def validate(self) -> bool:
        """Valida parámetros."""
        if self.momentum_period <= 0:
            logger.error("momentum_period debe ser > 0")
            return False
        if self.volatility_period <= 0:
            logger.error("volatility_period debe ser > 0")
            return False
        if self.top_n <= 0:
            logger.error("top_n debe ser > 0")
            return False
        if len(self.etf_universe) < self.top_n:
            logger.error(
                "etf_universe (%d) debe tener al menos top_n (%d) ETFs",
                len(self.etf_universe), self.top_n,
            )
            return False
        return True
