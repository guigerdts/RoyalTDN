"""RoyalTDN — ScalpingSpreadStrategy: expansión de rango para scalping

Detecta expansiones de volatilidad midiendo el rango (high-low) actual
contra su media móvil. Cuando el rango supera N veces el promedio,
se considera una expansión y se genera señal en la dirección del precio.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy


class ScalpingSpreadStrategy(BaseStrategy):
    """Volatilidad por expansión de rango (high-low).

    BUY/SELL cuando el rango actual supera SMA(rango) * threshold,
    indicando una expansión de volatilidad.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "spread_period": 10, "spread_threshold": 2.0, "timeframe": "1min",
        },
        "stocks": {
            "spread_period": 20, "spread_threshold": 1.5, "timeframe": "5min",
        },
    }

    def __init__(
        self,
        spread_period: int = 20,
        spread_threshold: float = 1.5,
        timeframe: str = "5min",
        category: str = "scalping",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.spread_period = spread_period
        self.spread_threshold = spread_threshold

    @property
    def name(self) -> str:
        return "scalping_spread"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            spread_period: int = profile["spread_period"]
            spread_threshold: float = profile["spread_threshold"]
        else:
            spread_period = self.spread_period
            spread_threshold = self.spread_threshold

        required = ["close", "high", "low"]
        if any(c not in data.columns for c in required) or len(data) < spread_period + 1:
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]

        price_range = high - low
        avg_range = price_range.rolling(spread_period).mean()

        last_range = float(price_range.iloc[-1])
        last_avg = float(avg_range.iloc[-1])

        if last_avg <= 0:
            return None

        range_ratio = last_range / last_avg
        last_close = float(close.iloc[-1])
        last_open = float(data["open"].iloc[-1]) if "open" in data.columns else last_close

        metadata = {
            "range": round(last_range, 2),
            "avg_range": round(last_avg, 2),
            "range_ratio": round(range_ratio, 2),
            "spread_period": spread_period,
        }

        if range_ratio > spread_threshold:
            if last_close > last_open:
                return {"action": "BUY", "price": last_close, "metadata": metadata}
            if last_close < last_open:
                return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_spread_period": crypto["spread_period"],
                "crypto_spread_threshold": crypto["spread_threshold"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_spread_period": stocks["spread_period"],
                "stocks_spread_threshold": stocks["spread_threshold"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.spread_period <= 0:
            logger.error("spread_period debe ser > 0")
            return False
        if self.spread_threshold <= 0:
            logger.error("spread_threshold debe ser > 0")
            return False
        return True
