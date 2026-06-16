"""
RoyalTDN — BollingerRSIStrategy: mean reversion intradía

Fase 5.3 — Estrategia 1

Entra cuando el precio toca la banda inferior de Bollinger y el RSI
está sobrevendido. Sale cuando alcanza la banda media, RSI sobrecomprado,
o tras un máximo de barras en hold.

Indicadores calculados con pandas (sin dependencias externas).
"""

import logging
from typing import Any, Dict, Optional

import pandas as pd

from royaltdn.strategy.base import BaseStrategy

logger = logging.getLogger("royaltdn.strategy.bollinger_rsi")


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    """Media simple móvil."""
    return series.rolling(window=window).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI) — Wilder smoothing.

    Fórmula:
      RSI = 100 - (100 / (1 + RS))
      RS = avg_gain / avg_loss

    Usa Wilder smoothing (EMA con alpha = 1/period).
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = delta.clip(upper=0).abs()

    # Wilder smoothed RSI: ewm(alpha=1/period, adjust=False)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    return rsi


class BollingerRSIStrategy(BaseStrategy):
    """Mean reversion con Bollinger Bands + RSI.

    Compra cuando precio toca banda inferior y RSI < umbral sobreventa.
    Vende cuando precio toca banda media o RSI > umbral sobrecompra,
    o tras max_bars_hold barras.
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: int = 30,
        rsi_overbought: int = 70,
        exit_bb_middle: bool = True,
        exit_rsi_overbought: bool = True,
        max_bars_hold: int = 30,
        timeframe: str = "5min",
    ):
        super().__init__(timeframe=timeframe)
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.exit_bb_middle = exit_bb_middle
        self.exit_rsi_overbought = exit_rsi_overbought
        self.max_bars_hold = max_bars_hold

    # ── Propiedades ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "bollinger_rsi"

    # ── Indicadores ─────────────────────────────────────────────────────

    def _compute_bollinger(self, close: pd.Series) -> Dict[str, pd.Series]:
        """Calcula Bollinger Bands.

        Returns:
            dict con 'middle', 'upper', 'lower' (pd.Series).
        """
        middle = compute_sma(close, self.bb_period)
        std = close.rolling(window=self.bb_period, min_periods=self.bb_period).std()
        upper = middle + self.bb_std * std
        lower = middle - self.bb_std * std
        return {"middle": middle, "upper": upper, "lower": lower}

    # ── BaseStrategy ────────────────────────────────────────────────────

    def generate_signal(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Genera señal de mean reversion.

        Args:
            data: DataFrame con columna ``close`` (obligatorio).

        Returns:
            Dict con action, price y metadata, o None.
        """
        if "close" not in data.columns:
            logger.warning("generate_signal: faltan columnas (close)")
            return None

        close = data["close"]
        if len(close) < max(self.bb_period, self.rsi_period) + 1:
            return None  # datos insuficientes

        # Calcular indicadores
        bb = self._compute_bollinger(close)
        rsi = compute_rsi(close, self.rsi_period)

        last_close = float(close.iloc[-1])
        last_lower = float(bb["lower"].iloc[-1])
        last_middle = float(bb["middle"].iloc[-1])
        last_rsi = float(rsi.iloc[-1])

        metadata = {
            "bb_lower": round(last_lower, 2),
            "bb_middle": round(last_middle, 2),
            "bb_upper": round(float(bb["upper"].iloc[-1]), 2),
            "rsi": round(last_rsi, 2),
        }

        # SEÑAL BUY: precio en banda inferior + RSI sobrevendido
        if last_close <= last_lower and last_rsi < self.rsi_oversold:
            return {
                "action": "BUY",
                "price": last_close,
                "metadata": metadata,
            }

        # SEÑAL SELL: precio alcanza banda media o RSI sobrecomprado
        sell_signal = False
        if self.exit_bb_middle and last_close >= last_middle:
            sell_signal = True
        if self.exit_rsi_overbought and last_rsi > self.rsi_overbought:
            sell_signal = True

        if sell_signal:
            return {
                "action": "SELL",
                "price": last_close,
                "metadata": metadata,
            }

        return None

    def get_parameters(self) -> Dict[str, Any]:
        """Retorna los parámetros actuales."""
        return {
            "bb_period": self.bb_period,
            "bb_std": self.bb_std,
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "exit_bb_middle": self.exit_bb_middle,
            "exit_rsi_overbought": self.exit_rsi_overbought,
            "max_bars_hold": self.max_bars_hold,
            "timeframe": self.timeframe,
        }

    def validate(self) -> bool:
        """Valida parámetros."""
        if self.bb_period <= 0:
            logger.error("bb_period debe ser > 0")
            return False
        if self.bb_std <= 0:
            logger.error("bb_std debe ser > 0")
            return False
        if self.rsi_period <= 0:
            logger.error("rsi_period debe ser > 0")
            return False
        if not (0 < self.rsi_oversold < self.rsi_overbought < 100):
            logger.error(
                "0 < rsi_oversold(%d) < rsi_overbought(%d) < 100",
                self.rsi_oversold, self.rsi_overbought,
            )
            return False
        return True
