"""RoyalTDN — IntradayMACDDivergenceStrategy: MACD-price divergence

Detects divergences between price and MACD to anticipate
intraday trend reversals.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy


class IntradayMACDDivergenceStrategy(BaseStrategy):
    """Classic MACD divergence for intraday trading.

    BUY: price lower low, MACD higher low (bullish divergence).
    SELL: price higher high, MACD lower high (bearish divergence).

    Attributes:
        fast_period: Fast EMA period for MACD line.
        slow_period: Slow EMA period for MACD line.
        signal_period: Signal line EMA period.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "fast_period": 12, "slow_period": 26, "signal_period": 9, "timeframe": "15min",
        },
        "stocks": {
            "fast_period": 12, "slow_period": 26, "signal_period": 9, "timeframe": "1H",
        },
    }

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        timeframe: str = "1H",
        category: str = "intraday",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    @property
    def name(self) -> str:
        return "intraday_macd_divergence"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate MACD divergence signal.

        Args:
            data: OHLCV DataFrame with close column.
            symbol: Optional ticker, resolves crypto/stocks profile.

        Returns:
            Dict with action, price, metadata or None.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            fast_period: int = profile["fast_period"]
            slow_period: int = profile["slow_period"]
            signal_period: int = profile["signal_period"]
        else:
            fast_period = self.fast_period
            slow_period = self.slow_period
            signal_period = self.signal_period

        if "close" not in data.columns or len(data) < slow_period * 2 + signal_period:
            return None

        close = data["close"]
        ema_fast = close.ewm(span=fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow

        half = len(close) // 2
        first_half = close.iloc[:half]
        second_half = close.iloc[half:]
        macd_first = macd.iloc[:half]
        macd_second = macd.iloc[half:]

        price_low1, price_low2 = float(first_half.min()), float(second_half.min())
        price_high1, price_high2 = float(first_half.max()), float(second_half.max())
        macd_low1, macd_low2 = float(macd_first.min()), float(macd_second.min())
        macd_high1, macd_high2 = float(macd_first.max()), float(macd_second.max())

        last_close = float(close.iloc[-1])
        last_macd = float(macd.iloc[-1])
        last_signal = float(macd.ewm(span=signal_period, adjust=False).mean().iloc[-1])

        metadata = {
            "macd": round(last_macd, 2),
            "signal": round(last_signal, 2),
            "fast_period": fast_period,
            "slow_period": slow_period,
        }

        # Bullish divergence: price lower low, MACD higher low
        if price_low2 < price_low1 and macd_low2 > macd_low1:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        # Bearish divergence: price higher high, MACD lower high
        if price_high2 > price_high1 and macd_high2 < macd_high1:
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
                "crypto_fast_period": crypto["fast_period"],
                "crypto_slow_period": crypto["slow_period"],
                "crypto_signal_period": crypto["signal_period"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_fast_period": stocks["fast_period"],
                "stocks_slow_period": stocks["slow_period"],
                "stocks_signal_period": stocks["signal_period"],
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
        if self.fast_period <= 0 or self.slow_period <= 0 or self.signal_period <= 0:
            logger.error("fast/slow/signal_period must be > 0")
            return False
        if self.fast_period >= self.slow_period:
            logger.error("fast_period must be less than slow_period")
            return False
        return True
