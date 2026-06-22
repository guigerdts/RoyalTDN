"""RoyalTDN — ScalpingMomentumStrategy: momentum de corto plazo para scalping

Entra cuando el retorno de N velas supera un umbral mínimo,
aprovechando impulsos direccionales de alta frecuencia.
Indicadores calculados con pandas (sin dependencias externas).
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


class ScalpingMomentumStrategy(BaseStrategy):
    """Momentum de corto plazo para scalping.

    Calcula el retorno porcentual sobre momentum_period velas.
    Si supera min_momentum_pct → BUY (impulso alcista).
    Si es menor a -min_momentum_pct → SELL (impulso bajista).
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "momentum_period": 5, "min_momentum_pct": 1.0, "timeframe": "1min",
        },
        "stocks": {
            "momentum_period": 10, "min_momentum_pct": 0.5, "timeframe": "3min",
        },
    }

    def __init__(
        self,
        momentum_period: int = 5,
        min_momentum_pct: float = 1.0,
        timeframe: str = "1min",
        category: str = "scalping",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.momentum_period = momentum_period
        self.min_momentum_pct = min_momentum_pct

    @property
    def name(self) -> str:
        return "scalping_momentum"

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            momentum_period: int = profile["momentum_period"]
            min_momentum_pct: float = profile["min_momentum_pct"]
        else:
            momentum_period = self.momentum_period
            min_momentum_pct = self.min_momentum_pct

        if "close" not in data.columns or len(data) < momentum_period + 1:
            return {
                "momentum_return": None,
                "close": None,
                "momentum_period": momentum_period,
                "min_momentum_pct": min_momentum_pct,
            }

        close = data["close"]
        pct_change = (float(close.iloc[-1]) / float(close.iloc[-momentum_period]) - 1) * 100
        last_close = float(close.iloc[-1])

        return {
            "momentum_return": pct_change,
            "close": last_close,
            "momentum_period": momentum_period,
            "min_momentum_pct": min_momentum_pct,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ind = self._compute_indicators(data, symbol)
        pct_change = ind.get("momentum_return")
        last_close = ind.get("close")
        momentum_period = ind["momentum_period"]
        min_momentum_pct = ind["min_momentum_pct"]

        if pct_change is None or last_close is None:
            return None

        metadata = {
            "pct_change": round(pct_change, 2),
            "momentum_period": momentum_period,
            "min_momentum_pct": min_momentum_pct,
        }

        if pct_change > min_momentum_pct:
            return {"action": "BUY", "price": last_close, "metadata": metadata}
        if pct_change < -min_momentum_pct:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        mv = ind.get("momentum_return")
        min_pct = ind.get("min_momentum_pct")
        close_val = ind.get("close")

        conditions = []
        if mv is not None and min_pct is not None:
            conditions.append({
                "name": "Momentum > +threshold",
                "met": mv > min_pct,
                "value": round(mv, 2),
                "threshold": float(min_pct),
                "gap_pct": round(_calc_gap(mv, float(min_pct), "above"), 2),
                "direction": "above",
            })
            conditions.append({
                "name": "Momentum < -threshold",
                "met": mv < -min_pct,
                "value": round(mv, 2),
                "threshold": float(-min_pct),
                "gap_pct": round(_calc_gap(mv, float(-min_pct), "below"), 2),
                "direction": "below",
            })

        inds = {}
        if mv is not None:
            inds["momentum_return"] = round(mv, 2)
        if close_val is not None:
            inds["close"] = round(close_val, 2)

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
                "crypto_momentum_period": crypto["momentum_period"],
                "crypto_min_momentum_pct": crypto["min_momentum_pct"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_momentum_period": stocks["momentum_period"],
                "stocks_min_momentum_pct": stocks["min_momentum_pct"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.momentum_period <= 0:
            logger.error("momentum_period debe ser > 0")
            return False
        if self.min_momentum_pct <= 0:
            logger.error("min_momentum_pct debe ser > 0")
            return False
        return True
