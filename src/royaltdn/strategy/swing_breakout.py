"""RoyalTDN — SwingBreakoutStrategy: range breakout with volume confirmation

Detects breakouts above resistance or below support with volume
confirmation on daily timeframe for both crypto and stocks.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


class SwingBreakoutStrategy(BaseStrategy):
    """Swing breakout with volume confirmation.

    BUY:  close > max(high[-period:]) AND volume > SMA(volume).
    SELL: close < min(low[-period:]) AND volume > SMA(volume).

    Attributes:
        breakout_period: Lookback period for resistance/support levels.
        volume_confirm: Whether to require volume confirmation.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "breakout_period": 20, "volume_confirm": True, "timeframe": "1d",
        },
        "stocks": {
            "breakout_period": 30, "volume_confirm": True, "timeframe": "1d",
        },
    }

    def __init__(
        self,
        breakout_period: int = 30,
        volume_confirm: bool = True,
        timeframe: str = "1d",
        category: str = "swing",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.breakout_period = breakout_period
        self.volume_confirm = volume_confirm

    @property
    def name(self) -> str:
        return "swing_breakout"

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula indicadores de breakout.

        Args:
            data: DataFrame con columnas ``close``, ``high``, ``low``, ``volume``.
            symbol: Opcional para resolución de perfil.

        Returns:
            Dict con close, recent_high, recent_low, volume_ratio, etc.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            breakout_period: int = profile["breakout_period"]
            volume_confirm: bool = profile["volume_confirm"]
        else:
            breakout_period = self.breakout_period
            volume_confirm = self.volume_confirm

        required = ["close", "high", "low", "volume"]
        if any(c not in data.columns for c in required) or len(data) < breakout_period + 1:
            return {"close": None, "recent_high": None, "recent_low": None,
                    "volume_ratio": None, "volume_sma": None, "volume_ok": False,
                    "breakout_period": breakout_period, "volume_confirm": volume_confirm}

        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]

        last_close = float(close.iloc[-1])
        last_volume = float(volume.iloc[-1])
        recent_high = float(high.iloc[-breakout_period:].max())
        recent_low = float(low.iloc[-breakout_period:].min())
        volume_sma = float(volume.rolling(window=breakout_period).mean().iloc[-1])
        volume_ratio = round(last_volume / volume_sma, 2) if volume_sma > 0 else 0.0
        volume_ok = last_volume > volume_sma if volume_confirm else True

        return {
            "close": last_close,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "volume_ratio": volume_ratio,
            "volume_sma": volume_sma,
            "volume_ok": volume_ok,
            "breakout_period": breakout_period,
            "volume_confirm": volume_confirm,
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
        volume_ok = ind.get("volume_ok", True)
        volume_confirm = ind.get("volume_confirm", self.volume_confirm)

        if last_close is None or recent_high is None or recent_low is None:
            return None

        metadata = {
            "breakout_high": recent_high,
            "breakout_low": recent_low,
            "volume_ratio": ind.get("volume_ratio", 0.0),
            "breakout_period": ind.get("breakout_period", self.breakout_period),
            "volume_confirm": volume_confirm,
        }

        if volume_ok and last_close > recent_high:
            return {"action": "BUY", "price": last_close, "metadata": metadata}
        if volume_ok and last_close < recent_low:
            return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explica las condiciones de breakout.

        Returns:
            Dict con indicadores, condiciones y señal.
        """
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        conditions = []
        inds = {}

        last_close = ind.get("close")
        recent_high = ind.get("recent_high")
        recent_low = ind.get("recent_low")
        volume_ratio = ind.get("volume_ratio")
        volume_ok = ind.get("volume_ok", True)

        if last_close is not None:
            inds["close"] = round(last_close, 2)

        if recent_high is not None:
            inds["resistance"] = round(recent_high, 2)
            conditions.append({
                "name": "Breakout above resistance",
                "met": last_close is not None and last_close > recent_high,
                "value": round(last_close, 2) if last_close is not None else 0.0,
                "threshold": round(recent_high, 2),
                "gap_pct": round(_calc_gap(last_close if last_close is not None else 0.0, recent_high, "above"), 2),
                "direction": "above",
            })

        if recent_low is not None:
            inds["support"] = round(recent_low, 2)
            conditions.append({
                "name": "Breakout below support",
                "met": last_close is not None and last_close < recent_low,
                "value": round(last_close, 2) if last_close is not None else 0.0,
                "threshold": round(recent_low, 2),
                "gap_pct": round(_calc_gap(last_close if last_close is not None else 0.0, recent_low, "below"), 2),
                "direction": "below",
            })

        if volume_ratio is not None:
            inds["volume_ratio"] = volume_ratio
            conditions.append({
                "name": "Volume confirmation",
                "met": volume_ok,
                "value": volume_ratio,
                "threshold": 1.0,
                "gap_pct": round(_calc_gap(volume_ratio, 1.0, "above"), 2),
                "direction": "above",
            })

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
                "crypto_breakout_period": crypto["breakout_period"],
                "crypto_volume_confirm": crypto["volume_confirm"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_breakout_period": stocks["breakout_period"],
                "stocks_volume_confirm": stocks["volume_confirm"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.breakout_period <= 1:
            logger.error("breakout_period must be > 1")
            return False
        return True
