"""RoyalTDN — ScalpingSpreadStrategy: expansión de rango para scalping

Detecta expansiones de volatilidad midiendo el rango (high-low) actual
contra su media móvil. Cuando el rango supera N veces el promedio,
se considera una expansión y se genera señal en la dirección del precio.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


class ScalpingSpreadStrategy(BaseStrategy):
    """Volatilidad por expansión de rango (high-low).

    BUY/SELL cuando el rango actual supera SMA(rango) * threshold,
    indicando una expansión de volatilidad.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "spread_period": 10, "spread_threshold": 2.0, "timeframe": "1min",
        },
        "stocks": {
            "spread_period": 20, "spread_threshold": 1.5, "timeframe": "5min",
        },
    }

    def __init__(
        self,
        spread_period: int = 20,
        spread_threshold: float = 1.5,
        timeframe: str = "5min",
        category: str = "scalping",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.spread_period = spread_period
        self.spread_threshold = spread_threshold

    @property
    def name(self) -> str:
        return "scalping_spread"

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            spread_period: int = profile["spread_period"]
            spread_threshold: float = profile["spread_threshold"]
        else:
            spread_period = self.spread_period
            spread_threshold = self.spread_threshold

        required = ["close", "high", "low"]
        if any(c not in data.columns for c in required) or len(data) < spread_period + 1:
            return {
                "range": None, "avg_range": None, "range_ratio": None,
                "close": None, "open": None,
                "spread_period": spread_period, "spread_threshold": spread_threshold,
            }

        close = data["close"]
        high = data["high"]
        low = data["low"]

        price_range = high - low
        avg_range = price_range.rolling(spread_period).mean()

        last_range = float(price_range.iloc[-1])
        last_avg = float(avg_range.iloc[-1])
        last_close = float(close.iloc[-1])
        last_open = float(data["open"].iloc[-1]) if "open" in data.columns else last_close

        range_ratio = last_range / last_avg if last_avg > 0 else 0.0

        return {
            "range": last_range,
            "avg_range": last_avg,
            "range_ratio": range_ratio,
            "close": last_close,
            "open": last_open,
            "spread_period": spread_period,
            "spread_threshold": spread_threshold,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ind = self._compute_indicators(data, symbol)
        last_range = ind.get("range")
        last_avg = ind.get("avg_range")
        range_ratio = ind.get("range_ratio")
        last_close = ind.get("close")
        last_open = ind.get("open")
        spread_period = ind["spread_period"]
        spread_threshold = ind["spread_threshold"]

        if last_range is None or last_close is None:
            return None
        if last_avg <= 0:
            return None

        metadata = {
            "range": round(last_range, 2),
            "avg_range": round(last_avg, 2),
            "range_ratio": round(range_ratio, 2),
            "spread_period": spread_period,
        }

        if range_ratio > spread_threshold:
            if last_close > last_open:
                return {"action": "BUY", "price": last_close, "metadata": metadata}
            if last_close < last_open:
                return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        range_ratio = ind.get("range_ratio")
        spread_th = ind.get("spread_threshold")
        close_val = ind.get("close")
        open_val = ind.get("open")

        conditions = []
        if range_ratio is not None and spread_th is not None:
            conditions.append({
                "name": "Range Ratio > Threshold",
                "met": range_ratio > spread_th,
                "value": round(range_ratio, 2),
                "threshold": float(spread_th),
                "gap_pct": round(_calc_gap(range_ratio, float(spread_th), "above"), 2),
                "direction": "above",
            })
        if None not in (close_val, open_val):
            conditions.append({
                "name": "Close > Open",
                "met": close_val > open_val,
                "value": round(close_val, 2),
                "threshold": round(open_val, 2),
                "gap_pct": round(_calc_gap(close_val, open_val, "above"), 2),
                "direction": "above",
            })
            conditions.append({
                "name": "Close < Open",
                "met": close_val < open_val,
                "value": round(close_val, 2),
                "threshold": round(open_val, 2),
                "gap_pct": round(_calc_gap(close_val, open_val, "below"), 2),
                "direction": "below",
            })

        inds = {}
        if range_ratio is not None:
            inds["range_ratio"] = round(range_ratio, 2)
        if close_val is not None:
            inds["close"] = round(close_val, 2)
        if open_val is not None:
            inds["open"] = round(open_val, 2)

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
                "crypto_spread_period": crypto["spread_period"],
                "crypto_spread_threshold": crypto["spread_threshold"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_spread_period": stocks["spread_period"],
                "stocks_spread_threshold": stocks["spread_threshold"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.spread_period <= 0:
            logger.error("spread_period debe ser > 0")
            return False
        if self.spread_threshold <= 0:
            logger.error("spread_threshold debe ser > 0")
            return False
        return True
