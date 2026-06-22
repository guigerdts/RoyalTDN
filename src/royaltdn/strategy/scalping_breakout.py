"""RoyalTDN — ScalpingBreakoutStrategy: breakout de rango con filtro ATR

Entra cuando el precio rompe el máximo/mínimo de N velas con suficiente
amplitud medida por ATR. Indicadores calculados con pandas.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.momentum_atr import compute_atr


class ScalpingBreakoutStrategy(BaseStrategy):
    """Breakout de rango con filtro de volatilidad (ATR).

    BUY: close > max(high[-period:]) AND price_range > ATR * multiplier.
    SELL: close < min(low[-period:]) AND price_range > ATR * multiplier.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "period": 10, "multiplier": 2.0, "timeframe": "1min",
        },
        "stocks": {
            "period": 20, "multiplier": 1.5, "timeframe": "5min",
        },
    }

    def __init__(
        self,
        period: int = 20,
        multiplier: float = 1.5,
        timeframe: str = "5min",
        category: str = "scalping",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.period = period
        self.multiplier = multiplier

    @property
    def name(self) -> str:
        return "scalping_breakout"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            period: int = profile["period"]
            multiplier: float = profile["multiplier"]
        else:
            period = self.period
            multiplier = self.multiplier

        required = ["close", "high", "low"]
        if any(c not in data.columns for c in required) or len(data) < period + 1:
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]

        atr = compute_atr(high, low, close, period)
        last_atr = float(atr.iloc[-1])
        last_close = float(close.iloc[-1])
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])
        price_range = last_high - last_low

        metadata = {
            "atr": round(last_atr, 2),
            "price_range": round(price_range, 2),
            "breakout_high": float(high.iloc[-period:].max()),
            "breakout_low": float(low.iloc[-period:].min()),
            "period": period,
        }

        # BUY: price breaks above recent high with enough range
        if last_close > float(high.iloc[-period:].max()) and price_range > last_atr * multiplier:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        # SELL: price breaks below recent low with enough range
        if last_close < float(low.iloc[-period:].min()) and price_range > last_atr * multiplier:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_period": crypto["period"],
                "crypto_multiplier": crypto["multiplier"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_period": stocks["period"],
                "stocks_multiplier": stocks["multiplier"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.period <= 0:
            logger.error("period debe ser > 0")
            return False
        if self.multiplier <= 0:
            logger.error("multiplier debe ser > 0")
            return False
        return True
