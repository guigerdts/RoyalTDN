"""RoyalTDN — IntradayTrendStrategy: intraday trend via EMA crossover + ATR filter

Simplified ADX proxy: fast/slow EMA crossover with ATR% as trend
strength filter for crypto (15min) and stocks (1H).
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.momentum_atr import compute_atr


class IntradayTrendStrategy(BaseStrategy):
    """Intraday trend following with EMA crossover and ATR filter.

    BUY: EMA_fast > EMA_slow AND ATR% > threshold.
    SELL: EMA_fast < EMA_slow AND ATR% > threshold.

    Attributes:
        trend_period: Period for ATR calculation (volatility filter).
        adx_threshold: Minimum ATR% to confirm trend strength.
        ema_fast: Fast EMA period for crossover.
        ema_slow: Slow EMA period for crossover.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "trend_period": 14, "adx_threshold": 25,
            "ema_fast": 7, "ema_slow": 20, "timeframe": "15min",
        },
        "stocks": {
            "trend_period": 20, "adx_threshold": 20,
            "ema_fast": 9, "ema_slow": 26, "timeframe": "1H",
        },
    }

    def __init__(
        self,
        trend_period: int = 20,
        adx_threshold: float = 20.0,
        ema_fast: int = 9,
        ema_slow: int = 26,
        timeframe: str = "1H",
        category: str = "intraday",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.trend_period = trend_period
        self.adx_threshold = adx_threshold
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    @property
    def name(self) -> str:
        return "intraday_trend"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate trend signal based on EMA crossover with ATR filter.

        Args:
            data: OHLCV DataFrame with close, high, low columns.
            symbol: Optional ticker, resolves crypto/stocks profile.

        Returns:
            Dict with action, price, metadata or None.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            trend_period: int = profile["trend_period"]
            adx_threshold: float = profile["adx_threshold"]
            ema_fast: int = profile["ema_fast"]
            ema_slow: int = profile["ema_slow"]
        else:
            trend_period = self.trend_period
            adx_threshold = self.adx_threshold
            ema_fast = self.ema_fast
            ema_slow = self.ema_slow

        need = max(ema_slow, trend_period) + 1
        if any(c not in data.columns for c in ("close", "high", "low")) or len(data) < need:
            return None

        close = data["close"]
        ema_fast_val = close.ewm(span=ema_fast, adjust=False).mean()
        ema_slow_val = close.ewm(span=ema_slow, adjust=False).mean()
        atr = compute_atr(data["high"], data["low"], close, trend_period)

        last_close = float(close.iloc[-1])
        last_fast = float(ema_fast_val.iloc[-1])
        last_slow = float(ema_slow_val.iloc[-1])
        atr_pct = (float(atr.iloc[-1]) / last_close * 100) if last_close > 0 else 0.0

        metadata = {
            "ema_fast": round(last_fast, 2),
            "ema_slow": round(last_slow, 2),
            "atr_pct": round(atr_pct, 2),
            "trend_period": trend_period,
        }

        if atr_pct > adx_threshold:
            if last_fast > last_slow:
                return {"action": "BUY", "price": last_close, "metadata": metadata}
            if last_fast < last_slow:
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
                "crypto_trend_period": crypto["trend_period"],
                "crypto_adx_threshold": crypto["adx_threshold"],
                "crypto_ema_fast": crypto["ema_fast"],
                "crypto_ema_slow": crypto["ema_slow"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_trend_period": stocks["trend_period"],
                "stocks_adx_threshold": stocks["adx_threshold"],
                "stocks_ema_fast": stocks["ema_fast"],
                "stocks_ema_slow": stocks["ema_slow"],
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
        if self.trend_period <= 0:
            logger.error("trend_period must be > 0")
            return False
        if self.adx_threshold <= 0:
            logger.error("adx_threshold must be > 0")
            return False
        if self.ema_fast <= 0 or self.ema_slow <= 0:
            logger.error("ema_fast and ema_slow must be > 0")
            return False
        if self.ema_fast >= self.ema_slow:
            logger.error("ema_fast must be less than ema_slow")
            return False
        return True
