"""RoyalTDN — SwingReversionStrategy: mean reversion via z-score

Detects overbought/oversold conditions using z-score of closing price
relative to SMA, with lookback period configurable per profile.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy


class SwingReversionStrategy(BaseStrategy):
    """Mean reversion via z-score for swing trading.

    z-score = (close - SMA) / STD over lookback_period.

    SELL when z-score > +threshold (overbought).
    BUY  when z-score < -threshold (oversold).

    Attributes:
        lookback_period: Period for SMA and STD calculation.
        z_score_threshold: Z-score threshold to trigger signal.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "lookback_period": 20, "z_score_threshold": 2.0, "timeframe": "1d",
        },
        "stocks": {
            "lookback_period": 30, "z_score_threshold": 1.5, "timeframe": "1d",
        },
    }

    def __init__(
        self,
        lookback_period: int = 30,
        z_score_threshold: float = 1.5,
        timeframe: str = "1d",
        category: str = "swing",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.lookback_period = lookback_period
        self.z_score_threshold = z_score_threshold

    @property
    def name(self) -> str:
        return "swing_reversion"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            lookback_period: int = profile["lookback_period"]
            z_score_threshold: float = profile["z_score_threshold"]
        else:
            lookback_period = self.lookback_period
            z_score_threshold = self.z_score_threshold

        if "close" not in data.columns or len(data) < lookback_period + 1:
            return None

        close = data["close"]
        sma = close.rolling(window=lookback_period).mean()
        std = close.rolling(window=lookback_period).std(ddof=0)

        last_close = float(close.iloc[-1])
        last_sma = float(sma.iloc[-1])
        last_std = float(std.iloc[-1])

        if last_std == 0:
            return None

        z_score = (last_close - last_sma) / last_std

        metadata = {
            "z_score": round(z_score, 4),
            "sma": round(last_sma, 2),
            "std": round(last_std, 2),
            "lookback_period": lookback_period,
        }

        if z_score > z_score_threshold:
            return {"action": "SELL", "price": last_close, "metadata": metadata}
        if z_score < -z_score_threshold:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        return None

    def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_lookback_period": crypto["lookback_period"],
                "crypto_z_score_threshold": crypto["z_score_threshold"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_lookback_period": stocks["lookback_period"],
                "stocks_z_score_threshold": stocks["z_score_threshold"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.lookback_period <= 1:
            logger.error("lookback_period must be > 1")
            return False
        if self.z_score_threshold <= 0:
            logger.error("z_score_threshold must be > 0")
            return False
        return True
