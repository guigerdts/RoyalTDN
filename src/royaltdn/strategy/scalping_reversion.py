"""RoyalTDN — ScalpingReversionStrategy: mean reversion de corto plazo

Entra cuando el precio se desvía significativamente de la media móvil
(desviación estándar), anticipando una reversión estadística.
Indicadores calculados con pandas (sin dependencias externas).
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy


class ScalpingReversionStrategy(BaseStrategy):
    """Mean reversion para scalping usando bandas de desviación estándar.

    BUY: close < SMA - deviation * STD  (oversold).
    SELL: close > SMA + deviation * STD  (overbought).
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "period": 10, "deviation": 2.0, "timeframe": "1min",
        },
        "stocks": {
            "period": 14, "deviation": 1.5, "timeframe": "3min",
        },
    }

    def __init__(
        self,
        period: int = 14,
        deviation: float = 1.5,
        timeframe: str = "3min",
        category: str = "scalping",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.period = period
        self.deviation = deviation

    @property
    def name(self) -> str:
        return "scalping_reversion"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            period: int = profile["period"]
            deviation: float = profile["deviation"]
        else:
            period = self.period
            deviation = self.deviation

        if "close" not in data.columns or len(data) < period + 1:
            return None

        close = data["close"]
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()

        last_close = float(close.iloc[-1])
        last_sma = float(sma.iloc[-1])
        last_std = float(std.iloc[-1])

        if last_std == 0:
            return None

        lower_band = last_sma - deviation * last_std
        upper_band = last_sma + deviation * last_std

        metadata = {
            "sma": round(last_sma, 2),
            "std": round(last_std, 2),
            "lower_band": round(lower_band, 2),
            "upper_band": round(upper_band, 2),
            "deviation": deviation,
            "period": period,
        }

        if last_close < lower_band:
            return {"action": "BUY", "price": last_close, "metadata": metadata}
        if last_close > upper_band:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_period": crypto["period"],
                "crypto_deviation": crypto["deviation"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_period": stocks["period"],
                "stocks_deviation": stocks["deviation"],
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
        if self.deviation <= 0:
            logger.error("deviation debe ser > 0")
            return False
        return True
