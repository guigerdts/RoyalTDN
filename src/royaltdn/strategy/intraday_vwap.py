"""RoyalTDN — IntradayVWAPStrategy: mean reversion with VWAP bands

VWAP proxy using SMA(close) with standard deviation bands.
Detects intraday overbought/oversold conditions.
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


class IntradayVWAPStrategy(BaseStrategy):
    """Mean reversion using standard deviation VWAP proxy.

    BUY: close < VWAP - std * multiplier (oversold).
    SELL: close > VWAP + std * multiplier (overbought).

    Attributes:
        vwap_multiplier: Std dev multiplier for band width.
        vwap_period: Rolling window for VWAP proxy and std dev.
    """

    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "vwap_multiplier": 2.0, "vwap_period": 14, "timeframe": "15min",
        },
        "stocks": {
            "vwap_multiplier": 1.5, "vwap_period": 20, "timeframe": "1H",
        },
    }

    def __init__(
        self,
        vwap_multiplier: float = 1.5,
        vwap_period: int = 20,
        timeframe: str = "1H",
        category: str = "intraday",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.vwap_multiplier = vwap_multiplier
        self.vwap_period = vwap_period

    @property
    def name(self) -> str:
        return "intraday_vwap"

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile = self._PROFILES["crypto" if is_crypto_symbol(symbol) else "stocks"]
            vwap_multiplier: float = profile["vwap_multiplier"]
            vwap_period: int = profile["vwap_period"]
        else:
            vwap_multiplier = self.vwap_multiplier
            vwap_period = self.vwap_period

        if "close" not in data.columns or len(data) < vwap_period + 1:
            return {"vwap": None, "std": None, "lower_band": None, "upper_band": None,
                    "close": None, "vwap_period": vwap_period, "vwap_multiplier": vwap_multiplier}

        close = data["close"]
        vwap = close.rolling(vwap_period).mean()
        std = close.rolling(vwap_period).std()
        last_close = float(close.iloc[-1])
        last_vwap = float(vwap.iloc[-1])
        last_std = float(std.iloc[-1])

        if last_std == 0 or last_vwap == 0:
            return {"vwap": None, "std": None, "lower_band": None, "upper_band": None,
                    "close": None, "vwap_period": vwap_period, "vwap_multiplier": vwap_multiplier}

        return {
            "vwap": last_vwap, "std": last_std, "close": last_close,
            "lower_band": last_vwap - last_std * vwap_multiplier,
            "upper_band": last_vwap + last_std * vwap_multiplier,
            "vwap_period": vwap_period, "vwap_multiplier": vwap_multiplier,
        }

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate VWAP reversion signal."""
        ind = self._compute_indicators(data, symbol)
        vwap = ind.get("vwap")
        std = ind.get("std")
        lower_band = ind.get("lower_band")
        upper_band = ind.get("upper_band")
        last_close = ind.get("close")
        if vwap is None or std is None or last_close is None:
            return None

        metadata = {
            "vwap": round(vwap, 2), "std": round(std, 2),
            "lower_band": round(lower_band, 2), "upper_band": round(upper_band, 2),
            "vwap_period": ind["vwap_period"],
        }

        if last_close < lower_band:
            return {"action": "BUY", "price": last_close, "metadata": metadata}
        if last_close > upper_band:
            return {"action": "SELL", "price": last_close, "metadata": metadata}
        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        lb = ind.get("lower_band")
        ub = ind.get("upper_band")
        c = ind.get("close")
        vw = ind.get("vwap")

        conditions = []
        if c is not None and lb is not None:
            conditions.append({
                "name": "Close below lower band",
                "met": c < lb, "value": round(c, 2),
                "threshold": round(lb, 2),
                "gap_pct": round(_calc_gap(c, lb, "below"), 2),
                "direction": "below",
            })
        if c is not None and ub is not None:
            conditions.append({
                "name": "Close above upper band",
                "met": c > ub, "value": round(c, 2),
                "threshold": round(ub, 2),
                "gap_pct": round(_calc_gap(c, ub, "above"), 2),
                "direction": "above",
            })

        inds = {}
        if vw is not None:
            inds["vwap"] = round(vw, 2)
        if c is not None:
            inds["close"] = round(c, 2)
        if lb is not None:
            inds["lower_band"] = round(lb, 2)
        if ub is not None:
            inds["upper_band"] = round(ub, 2)

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
                "crypto_vwap_multiplier": crypto["vwap_multiplier"],
                "crypto_vwap_period": crypto["vwap_period"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_vwap_multiplier": stocks["vwap_multiplier"],
                "stocks_vwap_period": stocks["vwap_period"],
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
        if self.vwap_multiplier <= 0:
            logger.error("vwap_multiplier must be > 0")
            return False
        if self.vwap_period <= 0:
            logger.error("vwap_period must be > 0")
            return False
        return True
