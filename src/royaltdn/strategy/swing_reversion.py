"""RoyalTDN — SwingReversionStrategy: mean reversion via z-score

Detects overbought/oversold conditions using z-score of closing price
relative to SMA, with lookback period configurable per profile.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


class SwingReversionStrategy(BaseStrategy):
    """Mean reversion via z-score for swing trading.

    z-score = (close - SMA) / STD over lookback_period.

    SELL when z-score > +threshold (overbought).
    BUY  when z-score < -threshold (oversold).

    Attributes:
        lookback_period: Period for SMA and STD calculation.
        z_score_threshold: Z-score threshold to trigger signal.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "lookback_period": 20, "z_score_threshold": 2.0, "timeframe": "1d",
        },
        "stocks": {
            "lookback_period": 30, "z_score_threshold": 1.5, "timeframe": "1d",
        },
    }

    def __init__(
        self,
        lookback_period: int = 30,
        z_score_threshold: float = 1.5,
        timeframe: str = "1d",
        category: str = "swing",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.lookback_period = lookback_period
        self.z_score_threshold = z_score_threshold

    @property
    def name(self) -> str:
        return "swing_reversion"

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula z-score, SMA, STD y precio de cierre.

        Args:
            data: DataFrame con columna ``close``.
            symbol: Opcional para resolución de perfil.

        Returns:
            Dict con z_score, sma, std, close, etc.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            lookback_period: int = profile["lookback_period"]
            z_score_threshold: float = profile["z_score_threshold"]
        else:
            lookback_period = self.lookback_period
            z_score_threshold = self.z_score_threshold

        if "close" not in data.columns or len(data) < lookback_period + 1:
            return {
                "z_score": None, "sma": None, "std": None, "close": None,
                "z_score_threshold": z_score_threshold,
                "lookback_period": lookback_period,
            }

        close = data["close"]
        sma = close.rolling(window=lookback_period).mean()
        std = close.rolling(window=lookback_period).std(ddof=0)

        last_close = float(close.iloc[-1])
        last_sma = float(sma.iloc[-1])
        last_std = float(std.iloc[-1])

        if last_std == 0:
            return {
                "z_score": None, "sma": last_sma, "std": last_std, "close": last_close,
                "z_score_threshold": z_score_threshold,
                "lookback_period": lookback_period,
            }

        z_score = (last_close - last_sma) / last_std

        return {
            "z_score": round(z_score, 4),
            "sma": round(last_sma, 2),
            "std": round(last_std, 2),
            "close": last_close,
            "z_score_threshold": z_score_threshold,
            "lookback_period": lookback_period,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ind = self._compute_indicators(data, symbol)

        z_score = ind.get("z_score")
        z_score_threshold = ind.get("z_score_threshold", self.z_score_threshold)
        last_close = ind.get("close")
        last_sma = ind.get("sma")
        last_std = ind.get("std")
        lookback_period = ind.get("lookback_period", self.lookback_period)

        if z_score is None or last_close is None:
            return None

        metadata = {
            "z_score": round(z_score, 4),
            "sma": round(last_sma, 2),
            "std": round(last_std, 2),
            "lookback_period": lookback_period,
        }

        if z_score > z_score_threshold:
            return {"action": "SELL", "price": last_close, "metadata": metadata}
        if z_score < -z_score_threshold:
            return {"action": "BUY", "price": last_close, "metadata": metadata}

        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explica las condiciones de mean reversion (z-score).

        Returns:
            Dict con indicadores, condiciones y señal.
        """
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        conditions = []
        inds = {}

        z_score = ind.get("z_score")
        z_score_threshold = ind.get("z_score_threshold", self.z_score_threshold)
        last_sma = ind.get("sma")
        last_std = ind.get("std")
        last_close = ind.get("close")

        if z_score is not None:
            inds["z_score"] = z_score
            inds["z_score_threshold"] = z_score_threshold

            # Oversold — z_score below -threshold
            conditions.append({
                "name": "Z-Score Oversold (BUY)",
                "met": z_score < -z_score_threshold,
                "value": z_score,
                "threshold": round(-z_score_threshold, 2),
                "gap_pct": round(_calc_gap(z_score, -z_score_threshold, "below"), 2),
                "direction": "below",
            })

            # Overbought — z_score above +threshold
            conditions.append({
                "name": "Z-Score Overbought (SELL)",
                "met": z_score > z_score_threshold,
                "value": z_score,
                "threshold": round(z_score_threshold, 2),
                "gap_pct": round(_calc_gap(z_score, z_score_threshold, "above"), 2),
                "direction": "above",
            })

        if last_sma is not None:
            inds["sma"] = round(last_sma, 2)

        if last_std is not None:
            inds["std"] = round(last_std, 2)

        if last_close is not None:
            inds["close"] = round(last_close, 2)

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
                "crypto_lookback_period": crypto["lookback_period"],
                "crypto_z_score_threshold": crypto["z_score_threshold"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_lookback_period": stocks["lookback_period"],
                "stocks_z_score_threshold": stocks["z_score_threshold"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        if self.lookback_period <= 1:
            logger.error("lookback_period must be > 1")
            return False
        if self.z_score_threshold <= 0:
            logger.error("z_score_threshold must be > 0")
            return False
        return True
