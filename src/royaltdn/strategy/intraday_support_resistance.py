"""RoyalTDN — IntradaySupportResistanceStrategy: support and resistance

Identifies S/R zones from recent highs/lows and generates signals
when price bounces off them.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


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

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            sr_period: int = profile["sr_period"]
            bounce_pct: float = profile["bounce_pct"]
        else:
            sr_period = self.sr_period
            bounce_pct = self.bounce_pct

        if any(c not in data.columns for c in ("close", "high", "low")) or len(data) < sr_period + 2:
            return {"support": None, "resistance": None, "close": None, "prev_close": None,
                    "zone_width": None, "sr_period": sr_period, "bounce_pct": bounce_pct}

        close = data["close"]
        high = data["high"]
        low = data["low"]

        support = float(low.iloc[-sr_period:-1].min())
        resistance = float(high.iloc[-sr_period:-1].max())
        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        zone_width = (resistance - support) * bounce_pct

        return {
            "support": support, "resistance": resistance,
            "close": last_close, "prev_close": prev_close,
            "zone_width": zone_width,
            "sr_period": sr_period, "bounce_pct": bounce_pct,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate support/resistance bounce signal."""
        ind = self._compute_indicators(data, symbol)
        support = ind.get("support")
        resistance = ind.get("resistance")
        last_close = ind.get("close")
        prev_close = ind.get("prev_close")
        if any(v is None for v in (support, resistance, last_close, prev_close)):
            return None

        zone_width = ind["zone_width"]
        bounce_pct = ind["bounce_pct"]
        near_support = abs(last_close - support) <= max(zone_width, support * bounce_pct)
        near_resistance = abs(last_close - resistance) <= max(zone_width, resistance * bounce_pct)

        metadata = {
            "support": round(support, 2), "resistance": round(resistance, 2),
            "zone_width": round(zone_width, 4), "sr_period": ind["sr_period"],
        }

        if near_support and last_close > prev_close:
            return {"action": "BUY", "price": last_close, "metadata": metadata}
        if near_resistance and last_close < prev_close:
            return {"action": "SELL", "price": last_close, "metadata": metadata}
        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        s = ind.get("support")
        r = ind.get("resistance")
        c = ind.get("close")
        pc = ind.get("prev_close")
        zw = ind.get("zone_width")
        bp = ind.get("bounce_pct")

        conditions = []
        if s is not None and c is not None and zw is not None and bp is not None:
            max_dist = max(zw, s * bp)
            dist = abs(c - s)
            conditions.append({
                "name": "Price near support",
                "met": dist <= max_dist, "value": round(dist, 4),
                "threshold": round(max_dist, 4),
                "gap_pct": round(_calc_gap(dist, max_dist, "below"), 2),
                "direction": "below",
            })
        if r is not None and c is not None and zw is not None and bp is not None:
            max_dist = max(zw, r * bp)
            dist = abs(c - r)
            conditions.append({
                "name": "Price near resistance",
                "met": dist <= max_dist, "value": round(dist, 4),
                "threshold": round(max_dist, 4),
                "gap_pct": round(_calc_gap(dist, max_dist, "below"), 2),
                "direction": "below",
            })
        if c is not None and pc is not None:
            conditions.append({
                "name": "Bullish candle",
                "met": c > pc, "value": round(c, 2),
                "threshold": round(pc, 2),
                "gap_pct": round(_calc_gap(c, pc, "above"), 2),
                "direction": "above",
            })
            conditions.append({
                "name": "Bearish candle",
                "met": c < pc, "value": round(c, 2),
                "threshold": round(pc, 2),
                "gap_pct": round(_calc_gap(c, pc, "below"), 2),
                "direction": "below",
            })

        inds = {}
        if s is not None:
            inds["support"] = round(s, 2)
        if r is not None:
            inds["resistance"] = round(r, 2)
        if c is not None:
            inds["close"] = round(c, 2)

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
