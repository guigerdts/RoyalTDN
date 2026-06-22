"""RoyalTDN — IntradayVolumeBreakoutStrategy: breakout with volume filter

Detects range breakouts accompanied by significant volume increase
relative to its moving average.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


class IntradayVolumeBreakoutStrategy(BaseStrategy):
    """Breakout detection with volume surge filter.

    BUY: volume > SMA(volume)*surge AND close > max(high[-period:]).
    SELL: volume > SMA(volume)*surge AND close < min(low[-period:]).

    Attributes:
        volume_surge_pct: Multiplier over SMA(volume) to confirm surge.
        breakout_period: Lookback window for range high/low.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "volume_surge_pct": 2.0, "breakout_period": 10, "timeframe": "15min",
        },
        "stocks": {
            "volume_surge_pct": 1.5, "breakout_period": 20, "timeframe": "1H",
        },
    }

    def __init__(
        self,
        volume_surge_pct: float = 1.5,
        breakout_period: int = 20,
        timeframe: str = "1H",
        category: str = "intraday",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.volume_surge_pct = volume_surge_pct
        self.breakout_period = breakout_period

    @property
    def name(self) -> str:
        return "intraday_volume_breakout"

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            volume_surge_pct: float = profile["volume_surge_pct"]
            breakout_period: int = profile["breakout_period"]
        else:
            volume_surge_pct = self.volume_surge_pct
            breakout_period = self.breakout_period

        required = ["close", "high", "low", "volume"]
        if any(c not in data.columns for c in required) or len(data) < breakout_period + 1:
            return {"volume_ratio": None, "avg_volume": None, "close": None,
                    "range_high": None, "range_low": None,
                    "breakout_period": breakout_period, "volume_surge_pct": volume_surge_pct}

        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]

        avg_volume = float(volume.rolling(breakout_period).mean().iloc[-1])
        if avg_volume <= 0:
            return {"volume_ratio": None, "avg_volume": None, "close": None,
                    "range_high": None, "range_low": None,
                    "breakout_period": breakout_period, "volume_surge_pct": volume_surge_pct}

        last_volume = float(volume.iloc[-1])
        volume_ratio = last_volume / avg_volume
        last_close = float(close.iloc[-1])
        range_high = float(high.iloc[-breakout_period:].max())
        range_low = float(low.iloc[-breakout_period:].min())

        return {
            "volume_ratio": volume_ratio, "avg_volume": avg_volume,
            "close": last_close, "range_high": range_high, "range_low": range_low,
            "breakout_period": breakout_period, "volume_surge_pct": volume_surge_pct,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate volume breakout signal."""
        ind = self._compute_indicators(data, symbol)
        volume_ratio = ind.get("volume_ratio")
        last_close = ind.get("close")
        range_high = ind.get("range_high")
        range_low = ind.get("range_low")
        if volume_ratio is None or last_close is None:
            return None

        metadata = {
            "volume_ratio": round(volume_ratio, 2),
            "avg_volume": round(ind["avg_volume"], 0),
            "range_high": range_high, "range_low": range_low,
            "breakout_period": ind["breakout_period"],
        }

        surge = ind["volume_surge_pct"]
        if volume_ratio > surge:
            if last_close > range_high:
                return {"action": "BUY", "price": last_close, "metadata": metadata}
            if last_close < range_low:
                return {"action": "SELL", "price": last_close, "metadata": metadata}
        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        vr = ind.get("volume_ratio")
        surge = ind.get("volume_surge_pct")
        rh = ind.get("range_high")
        rl = ind.get("range_low")
        c = ind.get("close")

        conditions = []
        if vr is not None and surge is not None:
            conditions.append({
                "name": "Volume surge",
                "met": vr > surge, "value": round(vr, 2),
                "threshold": float(surge),
                "gap_pct": round(_calc_gap(vr, float(surge), "above"), 2),
                "direction": "above",
            })
        if c is not None and rh is not None:
            conditions.append({
                "name": "Price > range high",
                "met": c > rh, "value": round(c, 2),
                "threshold": round(rh, 2),
                "gap_pct": round(_calc_gap(c, rh, "above"), 2),
                "direction": "above",
            })
        if c is not None and rl is not None:
            conditions.append({
                "name": "Price < range low",
                "met": c < rl, "value": round(c, 2),
                "threshold": round(rl, 2),
                "gap_pct": round(_calc_gap(c, rl, "below"), 2),
                "direction": "below",
            })

        inds = {}
        if vr is not None:
            inds["volume_ratio"] = round(vr, 2)
        if c is not None:
            inds["close"] = round(c, 2)
        if rh is not None:
            inds["range_high"] = round(rh, 2)
        if rl is not None:
            inds["range_low"] = round(rl, 2)

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
                "crypto_volume_surge_pct": crypto["volume_surge_pct"],
                "crypto_breakout_period": crypto["breakout_period"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_volume_surge_pct": stocks["volume_surge_pct"],
                "stocks_breakout_period": stocks["breakout_period"],
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
        if self.volume_surge_pct <= 0:
            logger.error("volume_surge_pct must be > 0")
            return False
        if self.breakout_period <= 0:
            logger.error("breakout_period must be > 0")
            return False
        return True
