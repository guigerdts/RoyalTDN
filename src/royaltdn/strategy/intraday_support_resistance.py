"""RoyalTDN — IntradaySupportResistanceStrategy: support and resistance

Identifies S/R zones from recent highs/lows and generates signals
when price bounces off them.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy


class IntradaySupportResistanceStrategy(BaseStrategy):
    """Intraday support and resistance with bounce confirmation.

    BUY: price near support zone with bullish candle (bounce up).
    SELL: price near resistance zone with bearish candle (bounce down).

    Attributes:
        sr_period: Lookback window for S/R zone detection.
        bounce_pct: Distance threshold from zone as price fraction.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "sr_period": 20, "bounce_pct": 0.005, "timeframe": "15min",
        },
        "stocks": {
            "sr_period": 30, "bounce_pct": 0.003, "timeframe": "1H",
        },
    }

    def __init__(
        self,
        sr_period: int = 30,
        bounce_pct: float = 0.003,
        timeframe: str = "1H",
        category: str = "intraday",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.sr_period = sr_period
        self.bounce_pct = bounce_pct

    @property
    def name(self) -> str:
        return "intraday_support_resistance"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate support/resistance bounce signal.

        Args:
            data: OHLCV DataFrame with close, high, low columns.
            symbol: Optional ticker, resolves crypto/stocks profile.

        Returns:
            Dict with action, price, metadata or None.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            sr_period: int = profile["sr_period"]
            bounce_pct: float = profile["bounce_pct"]
        else:
            sr_period = self.sr_period
            bounce_pct = self.bounce_pct

        if any(c not in data.columns for c in ("close", "high", "low")) or len(data) < sr_period + 2:
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]

        resistance = float(high.iloc[-sr_period:-1].max())
        support = float(low.iloc[-sr_period:-1].min())
        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        zone_width = (resistance - support) * bounce_pct

        metadata = {
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "zone_width": round(zone_width, 4),
            "sr_period": sr_period,
        }

        # Near support + bounce up → BUY
        near_support = abs(last_close - support) <= max(zone_width, support * bounce_pct)
        if near_support and last_close > prev_close:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        # Near resistance + bounce down → SELL
        near_resistance = abs(last_close - resistance) <= max(zone_width, resistance * bounce_pct)
        if near_resistance and last_close < prev_close:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Return current strategy parameters.

        Args:
            symbol: If None returns both profiles, otherwise resolves
                    by symbol type.

        Returns:
            Dict with profile parameters.
        """
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_sr_period": crypto["sr_period"],
                "crypto_bounce_pct": crypto["bounce_pct"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_sr_period": stocks["sr_period"],
                "stocks_bounce_pct": stocks["bounce_pct"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        """Validate strategy configuration.

        Returns:
            True if params are valid, False otherwise.
        """
        if self.sr_period <= 0:
            logger.error("sr_period must be > 0")
            return False
        if self.bounce_pct <= 0:
            logger.error("bounce_pct must be > 0")
            return False
        return True
