"""RoyalTDN — ScalpingOrderFlowStrategy: flujo de órdenes por volumen

Detecta desequilibrios de flujo mediante picos de volumen por encima
de un umbral y su relación con el volumen promedio. Proxy simplificado
de order flow sin order book real.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy


class ScalpingOrderFlowStrategy(BaseStrategy):
    """Order flow simplificado basado en volumen.

    BUY: volumen > threshold AND ratio volumen > imbalance_ratio
         (presión compradora: volumen alto con precio subiendo).
    SELL: volumen > threshold AND ratio volumen > imbalance_ratio
          (presión vendedora: volumen alto con precio bajando).
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "volume_threshold": 1_000_000, "imbalance_ratio": 2.0, "timeframe": "1min",
        },
        "stocks": {
            "volume_threshold": 500_000, "imbalance_ratio": 1.5, "timeframe": "5min",
        },
    }

    def __init__(
        self,
        volume_threshold: int = 500_000,
        imbalance_ratio: float = 1.5,
        timeframe: str = "5min",
        category: str = "scalping",
        volume_period: int = 20,
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.volume_threshold = volume_threshold
        self.imbalance_ratio = imbalance_ratio
        self.volume_period = volume_period

    @property
    def name(self) -> str:
        return "scalping_orderflow"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            volume_threshold: int = profile["volume_threshold"]
            imbalance_ratio: float = profile["imbalance_ratio"]
        else:
            volume_threshold = self.volume_threshold
            imbalance_ratio = self.imbalance_ratio

        required = ["close", "volume"]
        if any(c not in data.columns for c in required) or len(data) < self.volume_period + 1:
            return None

        close = data["close"]
        volume = data["volume"]

        last_volume = float(volume.iloc[-1])
        avg_volume = float(volume.rolling(self.volume_period).mean().iloc[-1])

        if avg_volume <= 0 or last_volume <= volume_threshold:
            return None

        volume_ratio = last_volume / avg_volume
        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) > 1 else last_close

        metadata = {
            "volume_ratio": round(volume_ratio, 2),
            "last_volume": int(last_volume),
            "avg_volume": int(avg_volume),
            "volume_threshold": volume_threshold,
            "imbalance_ratio": imbalance_ratio,
        }

        # BUY: volume spike + price rising (aggressive buying)
        if volume_ratio > imbalance_ratio and last_close > prev_close:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        # SELL: volume spike + price falling (aggressive selling)
        if volume_ratio > imbalance_ratio and last_close < prev_close:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_volume_threshold": crypto["volume_threshold"],
                "crypto_imbalance_ratio": crypto["imbalance_ratio"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_volume_threshold": stocks["volume_threshold"],
                "stocks_imbalance_ratio": stocks["imbalance_ratio"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.volume_threshold <= 0:
            logger.error("volume_threshold debe ser > 0")
            return False
        if self.imbalance_ratio <= 0:
            logger.error("imbalance_ratio debe ser > 0")
            return False
        if self.volume_period <= 0:
            logger.error("volume_period debe ser > 0")
            return False
        return True
