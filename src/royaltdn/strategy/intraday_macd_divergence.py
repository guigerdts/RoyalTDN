"""RoyalTDN — IntradayMACDDivergenceStrategy: MACD-price divergence

Detects divergences between price and MACD to anticipate
intraday trend reversals.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


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

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
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
            return {"price_low1": None, "price_low2": None,
                    "price_high1": None, "price_high2": None,
                    "macd_low1": None, "macd_low2": None,
                    "macd_high1": None, "macd_high2": None,
                    "close": None, "macd": None, "signal": None,
                    "fast_period": fast_period, "slow_period": slow_period,
                    "signal_period": signal_period}

        close = data["close"]
        ema_fast = close.ewm(span=fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow

        half = len(close) // 2
        first_half = close.iloc[:half]
        second_half = close.iloc[half:]
        macd_first = macd.iloc[:half]
        macd_second = macd.iloc[half:]

        price_low1 = float(first_half.min())
        price_low2 = float(second_half.min())
        price_high1 = float(first_half.max())
        price_high2 = float(second_half.max())
        macd_low1 = float(macd_first.min())
        macd_low2 = float(macd_second.min())
        macd_high1 = float(macd_first.max())
        macd_high2 = float(macd_second.max())

        last_close = float(close.iloc[-1])
        last_macd = float(macd.iloc[-1])
        last_signal = float(macd.ewm(span=signal_period, adjust=False).mean().iloc[-1])

        return {
            "price_low1": price_low1, "price_low2": price_low2,
            "price_high1": price_high1, "price_high2": price_high2,
            "macd_low1": macd_low1, "macd_low2": macd_low2,
            "macd_high1": macd_high1, "macd_high2": macd_high2,
            "close": last_close, "macd": last_macd, "signal": last_signal,
            "fast_period": fast_period, "slow_period": slow_period,
            "signal_period": signal_period,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate MACD divergence signal."""
        ind = self._compute_indicators(data, symbol)
        pl1 = ind.get("price_low1")
        pl2 = ind.get("price_low2")
        ph1 = ind.get("price_high1")
        ph2 = ind.get("price_high2")
        ml1 = ind.get("macd_low1")
        ml2 = ind.get("macd_low2")
        mh1 = ind.get("macd_high1")
        mh2 = ind.get("macd_high2")
        last_close = ind.get("close")
        if any(v is None for v in (pl1, pl2, ph1, ph2, ml1, ml2, mh1, mh2, last_close)):
            return None

        metadata = {
            "macd": round(ind["macd"], 2), "signal": round(ind["signal"], 2),
            "fast_period": ind["fast_period"], "slow_period": ind["slow_period"],
        }

        if pl2 < pl1 and ml2 > ml1:
            return {"action": "BUY", "price": last_close, "metadata": metadata}
        if ph2 > ph1 and mh2 < mh1:
            return {"action": "SELL", "price": last_close, "metadata": metadata}
        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        pl1 = ind.get("price_low1")
        pl2 = ind.get("price_low2")
        ph1 = ind.get("price_high1")
        ph2 = ind.get("price_high2")
        ml1 = ind.get("macd_low1")
        ml2 = ind.get("macd_low2")
        mh1 = ind.get("macd_high1")
        mh2 = ind.get("macd_high2")

        conditions = []
        if pl1 is not None and pl2 is not None:
            conditions.append({
                "name": "Price lower low",
                "met": pl2 < pl1, "value": round(pl2, 2),
                "threshold": round(pl1, 2),
                "gap_pct": round(_calc_gap(pl2, pl1, "below"), 2),
                "direction": "below",
            })
        if ml1 is not None and ml2 is not None:
            conditions.append({
                "name": "MACD higher low",
                "met": ml2 > ml1, "value": round(ml2, 2),
                "threshold": round(ml1, 2),
                "gap_pct": round(_calc_gap(ml2, ml1, "above"), 2),
                "direction": "above",
            })
        if ph1 is not None and ph2 is not None:
            conditions.append({
                "name": "Price higher high",
                "met": ph2 > ph1, "value": round(ph2, 2),
                "threshold": round(ph1, 2),
                "gap_pct": round(_calc_gap(ph2, ph1, "above"), 2),
                "direction": "above",
            })
        if mh1 is not None and mh2 is not None:
            conditions.append({
                "name": "MACD lower high",
                "met": mh2 < mh1, "value": round(mh2, 2),
                "threshold": round(mh1, 2),
                "gap_pct": round(_calc_gap(mh2, mh1, "below"), 2),
                "direction": "below",
            })

        inds = {}
        c = ind.get("close")
        if c is not None:
            inds["close"] = round(c, 2)
        m = ind.get("macd")
        if m is not None:
            inds["macd"] = round(m, 2)

        return {"indicators": inds, "conditions": conditions, "signal": signal}

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
