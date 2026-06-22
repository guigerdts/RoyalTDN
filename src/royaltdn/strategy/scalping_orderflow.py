"""RoyalTDN — ScalpingOrderFlowStrategy: flujo de órdenes por volumen

Detecta desequilibrios de flujo mediante picos de volumen por encima
de un umbral y su relación con el volumen promedio. Proxy simplificado
de order flow sin order book real.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


class ScalpingOrderFlowStrategy(BaseStrategy):
    """Order flow simplificado basado en volumen.

    BUY: volumen > threshold AND ratio volumen > imbalance_ratio
         (presión compradora: volumen alto con precio subiendo).
    SELL: volumen > threshold AND ratio volumen > imbalance_ratio
          (presión vendedora: volumen alto con precio bajando).
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "volume_threshold": 1_000_000, "imbalance_ratio": 2.0, "timeframe": "1min",
        },
        "stocks": {
            "volume_threshold": 500_000, "imbalance_ratio": 1.5, "timeframe": "5min",
        },
    }

    def __init__(
        self,
        volume_threshold: int = 500_000,
        imbalance_ratio: float = 1.5,
        timeframe: str = "5min",
        category: str = "scalping",
        volume_period: int = 20,
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.volume_threshold = volume_threshold
        self.imbalance_ratio = imbalance_ratio
        self.volume_period = volume_period

    @property
    def name(self) -> str:
        return "scalping_orderflow"

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            volume_threshold: int = profile["volume_threshold"]
            imbalance_ratio: float = profile["imbalance_ratio"]
        else:
            volume_threshold = self.volume_threshold
            imbalance_ratio = self.imbalance_ratio

        required = ["close", "volume"]
        if any(c not in data.columns for c in required) or len(data) < self.volume_period + 1:
            return {
                "volume_ratio": None, "last_volume": None, "avg_volume": None,
                "close": None, "prev_close": None,
                "volume_threshold": volume_threshold, "imbalance_ratio": imbalance_ratio,
            }

        close = data["close"]
        volume = data["volume"]

        last_volume = float(volume.iloc[-1])
        avg_volume = float(volume.rolling(self.volume_period).mean().iloc[-1])
        volume_ratio = last_volume / avg_volume if avg_volume > 0 else 0.0
        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) > 1 else last_close

        return {
            "volume_ratio": volume_ratio,
            "last_volume": last_volume,
            "avg_volume": avg_volume,
            "close": last_close,
            "prev_close": prev_close,
            "volume_threshold": volume_threshold,
            "imbalance_ratio": imbalance_ratio,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ind = self._compute_indicators(data, symbol)
        volume_ratio = ind.get("volume_ratio")
        last_volume = ind.get("last_volume")
        avg_volume = ind.get("avg_volume")
        last_close = ind.get("close")
        prev_close = ind.get("prev_close")
        volume_threshold = ind["volume_threshold"]
        imbalance_ratio = ind["imbalance_ratio"]

        if volume_ratio is None or last_close is None:
            return None
        if avg_volume is None or avg_volume <= 0 or last_volume <= volume_threshold:
            return None

        metadata = {
            "volume_ratio": round(volume_ratio, 2),
            "last_volume": int(last_volume) if last_volume is not None else 0,
            "avg_volume": int(avg_volume) if avg_volume is not None else 0,
            "volume_threshold": volume_threshold,
            "imbalance_ratio": imbalance_ratio,
        }

        if volume_ratio > imbalance_ratio and last_close > prev_close:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        if volume_ratio > imbalance_ratio and last_close < prev_close:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        vratio = ind.get("volume_ratio")
        imb = ind.get("imbalance_ratio")
        close_val = ind.get("close")
        prev_close = ind.get("prev_close")

        conditions = []
        if vratio is not None and imb is not None:
            conditions.append({
                "name": "Volume Ratio > Imbalance",
                "met": vratio > imb,
                "value": round(vratio, 2),
                "threshold": float(imb),
                "gap_pct": round(_calc_gap(vratio, float(imb), "above"), 2),
                "direction": "above",
            })
        if None not in (close_val, prev_close):
            conditions.append({
                "name": "Close > Previous Close",
                "met": close_val > prev_close,
                "value": round(close_val, 2),
                "threshold": round(prev_close, 2),
                "gap_pct": round(_calc_gap(close_val, prev_close, "above"), 2),
                "direction": "above",
            })
            conditions.append({
                "name": "Close < Previous Close",
                "met": close_val < prev_close,
                "value": round(close_val, 2),
                "threshold": round(prev_close, 2),
                "gap_pct": round(_calc_gap(close_val, prev_close, "below"), 2),
                "direction": "below",
            })

        inds = {}
        if vratio is not None:
            inds["volume_ratio"] = round(vratio, 2)
        if close_val is not None:
            inds["close"] = round(close_val, 2)
        if prev_close is not None:
            inds["prev_close"] = round(prev_close, 2)

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
                "crypto_volume_threshold": crypto["volume_threshold"],
                "crypto_imbalance_ratio": crypto["imbalance_ratio"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_volume_threshold": stocks["volume_threshold"],
                "stocks_imbalance_ratio": stocks["imbalance_ratio"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.volume_threshold <= 0:
            logger.error("volume_threshold debe ser > 0")
            return False
        if self.imbalance_ratio <= 0:
            logger.error("imbalance_ratio debe ser > 0")
            return False
        if self.volume_period <= 0:
            logger.error("volume_period debe ser > 0")
            return False
        return True
