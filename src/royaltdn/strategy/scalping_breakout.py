"""RoyalTDN — ScalpingBreakoutStrategy: breakout de rango con filtro ATR

Entra cuando el precio rompe el máximo/mínimo de N velas con suficiente
amplitud medida por ATR. Indicadores calculados con pandas.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap
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

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
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
            return {
                "close": None, "recent_high": None, "recent_low": None,
                "atr": None, "price_range": None, "atr_pct": None,
                "period": period, "multiplier": multiplier,
            }

        close = data["close"]
        high = data["high"]
        low = data["low"]

        atr = compute_atr(high, low, close, period)
        last_atr = float(atr.iloc[-1])
        last_close = float(close.iloc[-1])
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])
        price_range = last_high - last_low
        recent_high = float(high.iloc[-period:].max())
        recent_low = float(low.iloc[-period:].min())
        atr_pct = (last_atr / last_close * 100) if last_close != 0 else 0.0

        return {
            "close": last_close,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "atr": last_atr,
            "price_range": price_range,
            "atr_pct": round(atr_pct, 2),
            "period": period,
            "multiplier": multiplier,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ind = self._compute_indicators(data, symbol)
        last_close = ind.get("close")
        recent_high = ind.get("recent_high")
        recent_low = ind.get("recent_low")
        last_atr = ind.get("atr")
        price_range = ind.get("price_range")
        period = ind["period"]
        multiplier = ind["multiplier"]

        if last_close is None or recent_high is None or last_atr is None:
            return None

        metadata = {
            "atr": round(last_atr, 2),
            "price_range": round(price_range, 2),
            "breakout_high": recent_high,
            "breakout_low": recent_low,
            "period": period,
        }

        if last_close > recent_high and price_range > last_atr * multiplier:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        if last_close < recent_low and price_range > last_atr * multiplier:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        close_val = ind.get("close")
        recent_high = ind.get("recent_high")
        recent_low = ind.get("recent_low")
        last_atr = ind.get("atr")
        price_range = ind.get("price_range")
        multiplier = ind.get("multiplier")

        conditions = []
        if None not in (close_val, recent_high):
            conditions.append({
                "name": "Close > Recent High",
                "met": close_val > recent_high,
                "value": round(close_val, 2),
                "threshold": round(recent_high, 2),
                "gap_pct": round(_calc_gap(close_val, recent_high, "above"), 2),
                "direction": "above",
            })
        if None not in (close_val, recent_low):
            conditions.append({
                "name": "Close < Recent Low",
                "met": close_val < recent_low,
                "value": round(close_val, 2),
                "threshold": round(recent_low, 2),
                "gap_pct": round(_calc_gap(close_val, recent_low, "below"), 2),
                "direction": "below",
            })
        if None not in (last_atr, price_range, multiplier):
            threshold_atr = last_atr * multiplier
            conditions.append({
                "name": "Range > ATR x Multiplier",
                "met": price_range > threshold_atr,
                "value": round(price_range, 2),
                "threshold": round(threshold_atr, 2),
                "gap_pct": round(_calc_gap(price_range, threshold_atr, "above"), 2),
                "direction": "above",
            })

        inds = {}
        if close_val is not None:
            inds["close"] = round(close_val, 2)
        if recent_high is not None:
            inds["recent_high"] = round(recent_high, 2)
        if recent_low is not None:
            inds["recent_low"] = round(recent_low, 2)
        if last_atr is not None:
            inds["atr"] = round(last_atr, 2)
        if price_range is not None:
            inds["price_range"] = round(price_range, 2)

        return {
            "indicators": inds,
            "conditions": conditions,
            "signal": signal,
        }

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
