"""
RoyalTDN — MomentumATRStrategy: momentum con filtro de volatilidad

Fase 5.4 — Estrategia 2

Entra cuando el retorno de N días es positivo y la volatilidad (ATR%)
está controlada. Sale cuando el momentum de corto plazo se vuelve negativo.

Indicadores calculados con pandas (sin dependencias externas).
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range (ATR).

    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = EMA(TR, period) con Wilder smoothing.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder smoothing: EMA con alpha = 1/period
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


class MomentumATRStrategy(BaseStrategy):
    """Momentum de N días con filtro de volatilidad (ATR%).

    Compra cuando el retorno de momentum_period días es positivo y
    el ATR como porcentaje del precio está por debajo de atr_max_pct.
    Vende cuando el retorno de exit_period días se vuelve negativo.
    """

    # Perfiles de parámetros duales crypto / stocks
    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "momentum_period": 15, "atr_period": 14,
            "atr_max_pct": 4.0, "exit_period": 3, "timeframe": "1d",
        },
        "stocks": {
            "momentum_period": 20, "atr_period": 20,
            "atr_max_pct": 2.0, "exit_period": 5, "timeframe": "1d",
        },
    }

    def __init__(
        self,
        momentum_period: int = 20,
        atr_period: int = 20,
        atr_max_pct: float = 2.0,
        exit_momentum_negative: bool = True,
        exit_period: int = 5,
        timeframe: str = "1d",
        category: str = "swing",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.momentum_period = momentum_period
        self.atr_period = atr_period
        self.atr_max_pct = atr_max_pct
        self.exit_momentum_negative = exit_momentum_negative
        self.exit_period = exit_period

    # ── Propiedades ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "momentum_atr"

    # ── _compute_indicators ─────────────────────────────────────────────

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula momentum return, ATR y perfil de parámetros.

        Acepta ``symbol`` para resolución de perfil (crypto vs stocks).

        Args:
            data: DataFrame con columnas ``close`` (y opcional ``high``, ``low``).
            symbol: Opcional para resolución de perfil.

        Returns:
            Dict con momentum_return, last_atr, atr_pct, close y parámetros.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile_key = "crypto" if is_crypto_symbol(symbol) else "stocks"
            profile = self._PROFILES[profile_key]
            momentum_period: int = profile["momentum_period"]
            atr_period: int = profile["atr_period"]
            atr_max_pct: float = profile["atr_max_pct"]
            exit_period: int = profile["exit_period"]
        else:
            momentum_period = self.momentum_period
            atr_period = self.atr_period
            atr_max_pct = self.atr_max_pct
            exit_period = self.exit_period

        if "close" not in data.columns:
            return {"momentum_return": None, "last_atr": None, "atr_pct": None,
                    "close": None, "momentum_period": momentum_period,
                    "atr_period": atr_period, "atr_max_pct": atr_max_pct,
                    "exit_period": exit_period}

        close = data["close"]
        need = max(momentum_period, atr_period) + 1
        if len(close) < need:
            return {"momentum_return": None, "last_atr": None, "atr_pct": None,
                    "close": None, "momentum_period": momentum_period,
                    "atr_period": atr_period, "atr_max_pct": atr_max_pct,
                    "exit_period": exit_period}

        momentum_return = float((close.iloc[-1] / close.iloc[-momentum_period]) - 1)

        has_ohlc = all(c in data.columns for c in ("high", "low"))
        if has_ohlc:
            atr = compute_atr(data["high"], data["low"], close, atr_period)
        else:
            atr = close.diff().abs().rolling(atr_period).mean()

        last_atr = float(atr.iloc[-1])
        last_close = float(close.iloc[-1])
        atr_pct = (last_atr / last_close) * 100 if last_close > 0 else 0.0

        # Short-term return for exit signal
        short_return = None
        if len(close) > exit_period:
            short_return = float((close.iloc[-1] / close.iloc[-exit_period]) - 1)

        return {
            "momentum_return": round(momentum_return * 100, 2),
            "last_atr": round(last_atr, 2),
            "atr_pct": round(atr_pct, 2),
            "close": last_close,
            "short_return": round(short_return * 100, 2) if short_return is not None else None,
            "momentum_period": momentum_period,
            "atr_period": atr_period,
            "atr_max_pct": atr_max_pct,
            "exit_period": exit_period,
        }

    # ── BaseStrategy ────────────────────────────────────────────────────

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Genera señal de momentum con filtro de volatilidad.

        Args:
            data: DataFrame con columnas ``open``, ``high``, ``low``,
                  ``close`` (obligatorio close).
            symbol: Opcional. Si es crypto usa perfil crypto.

        Returns:
            Dict con action, price y metadata, o None.
        """
        # Resolver perfil a variables locales — no mutar self.*
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile_key = "crypto" if is_crypto_symbol(symbol) else "stocks"
            profile = self._PROFILES[profile_key]
            atr_max_pct: float = profile["atr_max_pct"]
            exit_period: int = profile["exit_period"]
        else:
            atr_max_pct = self.atr_max_pct
            exit_period = self.exit_period

        # Delegar a _compute_indicators (valida datos internamente)
        ind = self._compute_indicators(data, symbol)
        momentum_return = ind.get("momentum_return")
        atr_pct = ind.get("atr_pct")
        last_close = ind.get("close")
        short_return = ind.get("short_return")

        if momentum_return is None or atr_pct is None or last_close is None:
            return None

        metadata = {
            "momentum_return": momentum_return,
            "atr_pct": atr_pct,
            "atr": ind.get("last_atr", 0),
        }

        # SEÑAL BUY: momentum positivo + volatilidad controlada
        if momentum_return > 0 and atr_pct < atr_max_pct:
            return {
                "action": "BUY",
                "price": last_close,
                "metadata": metadata,
            }

        # SEÑAL SELL: momentum de corto plazo negativo
        if self.exit_momentum_negative and short_return is not None and short_return < 0:
            return {
                "action": "SELL",
                "price": last_close,
                "metadata": metadata,
            }

        return None

    def explain(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explica las condiciones de momentum y volatilidad.

        Returns:
            Dict con indicadores, condiciones y señal.
        """
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        atr_max_pct = ind.get("atr_max_pct", self.atr_max_pct)
        momentum_return = ind.get("momentum_return")
        atr_pct = ind.get("atr_pct")
        short_return = ind.get("short_return")

        conditions = []

        if momentum_return is not None:
            conditions.append({
                "name": "Momentum Positive",
                "met": momentum_return > 0,
                "value": momentum_return,
                "threshold": 0.0,
                "gap_pct": round(_calc_gap(momentum_return / 100, 0.0, "above"), 2)
                    if momentum_return <= 0 else 0.0,
                "direction": "above",
            })

        if atr_pct is not None:
            conditions.append({
                "name": "ATR % below max",
                "met": atr_pct < atr_max_pct,
                "value": atr_pct,
                "threshold": atr_max_pct,
                "gap_pct": round(_calc_gap(atr_pct, atr_max_pct, "below"), 2),
                "direction": "below",
            })

        if short_return is not None:
            conditions.append({
                "name": "Short-term Negative",
                "met": short_return < 0,
                "value": short_return,
                "threshold": 0.0,
                "gap_pct": round(_calc_gap(short_return / 100, 0.0, "below"), 2)
                    if short_return >= 0 else 0.0,
                "direction": "below",
            })

        inds = {}
        if momentum_return is not None:
            inds["momentum_return"] = momentum_return
        if atr_pct is not None:
            inds["atr_pct"] = atr_pct
        if short_return is not None:
            inds["short_return"] = short_return

        return {
            "indicators": inds,
            "conditions": conditions,
            "signal": signal,
        }

    def get_parameters(
        self,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retorna los parámetros actuales.

        Args:
            symbol: Opcional. Si es ``None`` retorna ambos perfiles
                    con prefijos ``crypto_*`` y ``stocks_*``.
                    Si es crypto retorna el perfil crypto.
                    En cualquier otro caso retorna el perfil stocks.
        """
        if symbol is None:
            crypto = self._PROFILES["crypto"]
            stocks = self._PROFILES["stocks"]
            return {
                "crypto_momentum_period": crypto["momentum_period"],
                "crypto_atr_period": crypto["atr_period"],
                "crypto_atr_max_pct": crypto["atr_max_pct"],
                "crypto_exit_period": crypto["exit_period"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_momentum_period": stocks["momentum_period"],
                "stocks_atr_period": stocks["atr_period"],
                "stocks_atr_max_pct": stocks["atr_max_pct"],
                "stocks_exit_period": stocks["exit_period"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        """Valida parámetros."""
        if self.momentum_period <= 0:
            logger.error("momentum_period debe ser > 0")
            return False
        if self.atr_period <= 0:
            logger.error("atr_period debe ser > 0")
            return False
        if self.atr_max_pct <= 0:
            logger.error("atr_max_pct debe ser > 0")
            return False
        if self.exit_period <= 0:
            logger.error("exit_period debe ser > 0")
            return False
        return True
