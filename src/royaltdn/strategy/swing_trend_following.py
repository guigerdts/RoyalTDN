"""RoyalTDN — SwingTrendFollowingStrategy: trend following via EMA crossover + ATR%

Daily trend following using fast/slow EMA crossover with ATR-based trend
strength filter for crypto (1d) and stocks (1d).
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger
from royaltdn.strategy.base import BaseStrategy, _calc_gap



class SwingTrendFollowingStrategy(BaseStrategy):
    """Swing trend following with EMA crossover and ATR% trend strength.

    BUY:  EMA_fast > EMA_slow AND ATR% > trend_strength/100.
    SELL: EMA_fast < EMA_slow AND ATR% > trend_strength/100.

    Attributes:
        fast_ema: Fast EMA period for crossover.
        slow_ema: Slow EMA period for crossover.
        trend_strength: Minimum ATR%% to confirm trend (ATR%% > trend_strength/100).
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "fast_ema": 7, "slow_ema": 25,
            "trend_strength": 25, "timeframe": "1d",
        },
        "stocks": {
            "fast_ema": 10, "slow_ema": 30,
            "trend_strength": 20, "timeframe": "1d",
        },
    }

    def __init__(
        self,
        fast_ema: int = 10,
        slow_ema: int = 30,
        trend_strength: float = 20.0,
        timeframe: str = "1d",
        category: str = "swing",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.trend_strength = trend_strength

    @property
    def name(self) -> str:
        return "swing_trend_following"

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            fast_ema: int = profile["fast_ema"]
            slow_ema: int = profile["slow_ema"]
            trend_strength: float = profile["trend_strength"]
        else:
            fast_ema = self.fast_ema
            slow_ema = self.slow_ema
            trend_strength = self.trend_strength

        need = max(slow_ema, 14) + 1
        if any(c not in data.columns for c in ("close", "high", "low")) or len(data) < need:
            return None

                # Delegar a _compute_indicators
        ind = self._compute_indicators(data, symbol)
        last_fast = ind.get("ema_fast")
        last_slow = ind.get("ema_slow")
        atr_pct = ind.get("atr_pct")
        last_close = ind.get("close")

        if any(v is None for v in [last_fast, last_slow, atr_pct, last_close]):
            return None

        metadata = {
            "ema_fast": round(last_fast, 2),
            "ema_slow": round(last_slow, 2),
            "atr_pct": round(atr_pct, 2),
            "trend_strength": ind.get("trend_strength", trend_strength),
        }

        if atr_pct > (ind.get("trend_strength", trend_strength) / 100.0):
            if last_fast > last_slow:
                return {"action": "BUY", "price": last_close, "metadata": metadata}
            if last_fast < last_slow:
                return {"action": "SELL", "price": last_close, "metadata": metadata}

        return None

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula EMA fast/slow, ATR% y close.

        Args:
            data: DataFrame con columnas ``close``, ``high``, ``low``.
            symbol: Opcional para resolución de perfil.

        Returns:
            Dict con ema_fast, ema_slow, atr_pct, close, etc.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            fast_ema: int = profile["fast_ema"]
            slow_ema: int = profile["slow_ema"]
            trend_strength: float = profile["trend_strength"]
        else:
            fast_ema = self.fast_ema
            slow_ema = self.slow_ema
            trend_strength = self.trend_strength

        need = max(slow_ema, 14) + 1
        if any(c not in data.columns for c in ("close", "high", "low")) or len(data) < need:
            return {"ema_fast": None, "ema_slow": None, "atr_pct": None, "close": None,
                    "trend_strength": trend_strength}

        from royaltdn.strategy.momentum_atr import compute_atr

        close = data["close"]
        high = data["high"]
        low = data["low"]

        ema_fast_val = close.ewm(span=fast_ema, adjust=False).mean()
        ema_slow_val = close.ewm(span=slow_ema, adjust=False).mean()
        atr = compute_atr(high, low, close, period=14)

        last_close = float(close.iloc[-1])
        last_fast = float(ema_fast_val.iloc[-1])
        last_slow = float(ema_slow_val.iloc[-1])
        atr_pct = (float(atr.iloc[-1]) / last_close * 100) if last_close > 0 else 0.0

        return {
            "ema_fast": last_fast,
            "ema_slow": last_slow,
            "atr_pct": atr_pct,
            "close": last_close,
            "trend_strength": trend_strength,
        }

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explica las condiciones de tendencia (EMA crossover + ATR%).

        Returns:
            Dict con indicadores, condiciones y señal.
        """
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        conditions = []
        inds = {}

        ema_fast = ind.get("ema_fast")
        ema_slow = ind.get("ema_slow")
        atr_pct = ind.get("atr_pct")
        trend_strength = ind.get("trend_strength")

        if ema_fast is not None and ema_slow is not None:
            inds["ema_fast"] = round(ema_fast, 2)
            inds["ema_slow"] = round(ema_slow, 2)
            ema_diff = ema_fast - ema_slow
            inds["ema_diff"] = round(ema_diff, 2)

            conditions.append({
                "name": "EMA Fast > EMA Slow",
                "met": ema_fast > ema_slow,
                "value": round(ema_fast, 2),
                "threshold": round(ema_slow, 2),
                "gap_pct": round(_calc_gap(ema_fast, ema_slow, "above"), 2),
                "direction": "above",
            })

        if atr_pct is not None:
            inds["atr_pct"] = round(atr_pct, 2)
            atr_threshold = trend_strength / 100.0 if trend_strength else 0.0
            conditions.append({
                "name": "ATR % confirms trend",
                "met": atr_pct > atr_threshold,
                "value": round(atr_pct, 2),
                "threshold": round(atr_threshold, 4),
                "gap_pct": round(_calc_gap(atr_pct, atr_threshold, "above"), 2),
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
                "crypto_fast_ema": crypto["fast_ema"],
                "crypto_slow_ema": crypto["slow_ema"],
                "crypto_trend_strength": crypto["trend_strength"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_fast_ema": stocks["fast_ema"],
                "stocks_slow_ema": stocks["slow_ema"],
                "stocks_trend_strength": stocks["trend_strength"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.fast_ema <= 0:
            logger.error("fast_ema must be > 0")
            return False
        if self.slow_ema <= 0:
            logger.error("slow_ema must be > 0")
            return False
        if self.fast_ema >= self.slow_ema:
            logger.error("fast_ema must be less than slow_ema")
            return False
        if self.trend_strength <= 0:
            logger.error("trend_strength must be > 0")
            return False
        return True
