"""
RoyalTDN — MomentumATRStrategy: momentum con filtro de volatilidad

Fase 5.4 — Estrategia 2

Entra cuando el retorno de N días es positivo y la volatilidad (ATR%)
está controlada. Sale cuando el momentum de corto plazo se vuelve negativo.

Indicadores calculados con pandas (sin dependencias externas).
"""

import logging
from typing import Any, Dict, Optional

import pandas as pd

from royaltdn.strategy.base import BaseStrategy

logger = logging.getLogger("royaltdn.strategy.momentum_atr")


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range (ATR).

    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = EMA(TR, period) con Wilder smoothing.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder smoothing: EMA con alpha = 1/period
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


class MomentumATRStrategy(BaseStrategy):
    """Momentum de N días con filtro de volatilidad (ATR%).

    Compra cuando el retorno de momentum_period días es positivo y
    el ATR como porcentaje del precio está por debajo de atr_max_pct.
    Vende cuando el retorno de exit_period días se vuelve negativo.
    """

    def __init__(
        self,
        momentum_period: int = 20,
        atr_period: int = 20,
        atr_max_pct: float = 2.0,
        exit_momentum_negative: bool = True,
        exit_period: int = 5,
        timeframe: str = "1d",
    ):
        super().__init__(timeframe=timeframe)
        self.momentum_period = momentum_period
        self.atr_period = atr_period
        self.atr_max_pct = atr_max_pct
        self.exit_momentum_negative = exit_momentum_negative
        self.exit_period = exit_period

    # ── Propiedades ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "momentum_atr"

    # ── BaseStrategy ────────────────────────────────────────────────────

    def generate_signal(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Genera señal de momentum con filtro de volatilidad.

        Args:
            data: DataFrame con columnas ``open``, ``high``, ``low``,
                  ``close`` (obligatorio close).

        Returns:
            Dict con action, price y metadata, o None.
        """
        if "close" not in data.columns:
            logger.warning("generate_signal: faltan columnas (close)")
            return None

        close = data["close"]
        need = max(self.momentum_period, self.atr_period) + 1
        if len(close) < need:
            return None  # datos insuficientes

        # Retorno de momentum_period días
        momentum_return = (close.iloc[-1] / close.iloc[-self.momentum_period]) - 1

        # ATR como % del precio
        has_ohlc = all(c in data.columns for c in ("high", "low"))
        if has_ohlc:
            atr = compute_atr(data["high"], data["low"], close, self.atr_period)
        else:
            # Fallback: ATR aproximado solo con close
            atr = close.diff().abs().rolling(self.atr_period).mean()

        last_atr = float(atr.iloc[-1])
        last_close = float(close.iloc[-1])
        atr_pct = (last_atr / last_close) * 100 if last_close > 0 else 0.0

        metadata = {
            "momentum_return": round(float(momentum_return) * 100, 2),
            "atr_pct": round(atr_pct, 2),
            "atr": round(last_atr, 2),
        }

        # SEÑAL BUY: momentum positivo + volatilidad controlada
        if momentum_return > 0 and atr_pct < self.atr_max_pct:
            return {
                "action": "BUY",
                "price": last_close,
                "metadata": metadata,
            }

        # SEÑAL SELL: momentum de corto plazo negativo
        if self.exit_momentum_negative and len(close) > self.exit_period:
            short_return = (
                close.iloc[-1] / close.iloc[-self.exit_period]
            ) - 1
            if short_return < 0:
                return {
                    "action": "SELL",
                    "price": last_close,
                    "metadata": metadata,
                }

        return None

    def get_parameters(self) -> Dict[str, Any]:
        """Retorna los parámetros actuales."""
        return {
            "momentum_period": self.momentum_period,
            "atr_period": self.atr_period,
            "atr_max_pct": self.atr_max_pct,
            "exit_momentum_negative": self.exit_momentum_negative,
            "exit_period": self.exit_period,
            "timeframe": self.timeframe,
        }

    def validate(self) -> bool:
        """Valida parámetros."""
        if self.momentum_period <= 0:
            logger.error("momentum_period debe ser > 0")
            return False
        if self.atr_period <= 0:
            logger.error("atr_period debe ser > 0")
            return False
        if self.atr_max_pct <= 0:
            logger.error("atr_max_pct debe ser > 0")
            return False
        if self.exit_period <= 0:
            logger.error("exit_period debe ser > 0")
            return False
        return True
