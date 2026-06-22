"""RoyalTDN — SwingBreakoutStrategy: range breakout with volume confirmation

Detects breakouts above resistance or below support with volume
confirmation on daily timeframe for both crypto and stocks.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy


class SwingBreakoutStrategy(BaseStrategy):
    """Swing breakout with volume confirmation.

    BUY:  close > max(high[-period:]) AND volume > SMA(volume).
    SELL: close < min(low[-period:]) AND volume > SMA(volume).

    Attributes:
        breakout_period: Lookback period for resistance/support levels.
        volume_confirm: Whether to require volume confirmation.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "breakout_period": 20, "volume_confirm": True, "timeframe": "1d",
        },
        "stocks": {
            "breakout_period": 30, "volume_confirm": True, "timeframe": "1d",
        },
    }

    def __init__(
        self,
        breakout_period: int = 30,
        volume_confirm: bool = True,
        timeframe: str = "1d",
        category: str = "swing",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.breakout_period = breakout_period
        self.volume_confirm = volume_confirm

    @property
    def name(self) -> str:
        return "swing_breakout"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            breakout_period: int = profile["breakout_period"]
            volume_confirm: bool = profile["volume_confirm"]
        else:
            breakout_period = self.breakout_period
            volume_confirm = self.volume_confirm

        required = ["close", "high", "low", "volume"]
        if any(c not in data.columns for c in required) or len(data) < breakout_period + 1:
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]

        last_close = float(close.iloc[-1])
        last_volume = float(volume.iloc[-1])
        recent_high = float(high.iloc[-breakout_period:].max())
        recent_low = float(low.iloc[-breakout_period:].min())
        volume_sma = float(volume.rolling(window=breakout_period).mean().iloc[-1])

        volume_ok = last_volume > volume_sma if volume_confirm else True

        metadata = {
            "breakout_high": recent_high,
            "breakout_low": recent_low,
            "volume_ratio": round(last_volume / volume_sma, 2) if volume_sma > 0 else 0.0,
            "breakout_period": breakout_period,
            "volume_confirm": volume_confirm,
        }

        if volume_ok and last_close > recent_high:
            return {"action": "BUY", "price": last_close, "metadata": metadata}
        if volume_ok and last_close < recent_low:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_breakout_period": crypto["breakout_period"],
                "crypto_volume_confirm": crypto["volume_confirm"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_breakout_period": stocks["breakout_period"],
                "stocks_volume_confirm": stocks["volume_confirm"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.breakout_period <= 1:
            logger.error("breakout_period must be > 1")
            return False
        return True
