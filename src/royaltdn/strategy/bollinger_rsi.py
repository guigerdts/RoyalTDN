"""
RoyalTDN — BollingerRSIStrategy: mean reversion intradía

Fase 5.3 — Estrategia 1

Entra cuando el precio toca la banda inferior de Bollinger y el RSI
está sobrevendido. Sale cuando alcanza la banda media, RSI sobrecomprado,
o tras un máximo de barras en hold.

Indicadores calculados con pandas (sin dependencias externas).
"""

from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from royaltdn.strategy.base import BaseStrategy, _calc_gap


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    """Media simple móvil."""
    return series.rolling(window=window).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI) — Wilder smoothing.

    Fórmula:
      RSI = 100 - (100 / (1 + RS))
      RS = avg_gain / avg_loss

    Usa Wilder smoothing (EMA con alpha = 1/period).
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = delta.clip(upper=0).abs()

    # Wilder smoothed RSI: ewm(alpha=1/period, adjust=False)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    return rsi


class BollingerRSIStrategy(BaseStrategy):
    """Mean reversion con Bollinger Bands + RSI.

    Compra cuando precio toca banda inferior y RSI < umbral sobreventa.
    Vende cuando precio toca banda media o RSI > umbral sobrecompra,
    o tras max_bars_hold barras.
    """

    # Perfiles de parámetros duales crypto / stocks
    _PROFILES: Dict[str, Dict[str, Any]] = {
        "crypto": {
            "bb_period": 15, "bb_std": 2.5,
            "rsi_period": 10, "rsi_oversold": 25, "rsi_overbought": 75,
            "max_bars_hold": 20, "timeframe": "5min",
        },
        "stocks": {
            "bb_period": 20, "bb_std": 2.0,
            "rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70,
            "max_bars_hold": 30, "timeframe": "15min",
        },
    }

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: int = 30,
        rsi_overbought: int = 70,
        exit_bb_middle: bool = True,
        exit_rsi_overbought: bool = True,
        max_bars_hold: int = 30,
        timeframe: str = "5min",
        category: str = "swing",
    ):
        super().__init__(timeframe=timeframe, category=category)
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.exit_bb_middle = exit_bb_middle
        self.exit_rsi_overbought = exit_rsi_overbought
        self.max_bars_hold = max_bars_hold

    # ── Propiedades ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "bollinger_rsi"

    # ── Indicadores ─────────────────────────────────────────────────────

    def _compute_bollinger(
        self,
        close: pd.Series,
        bb_period: Optional[int] = None,
        bb_std: Optional[float] = None,
    ) -> Dict[str, pd.Series]:
        """Calcula Bollinger Bands.

        Args:
            close: Serie de precios de cierre.
            bb_period: Período opcional (default: self.bb_period).
            bb_std: Desviación opcional (default: self.bb_std).

        Returns:
            dict con 'middle', 'upper', 'lower' (pd.Series).
        """
        _bb_period = bb_period if bb_period is not None else self.bb_period
        _bb_std = bb_std if bb_std is not None else self.bb_std
        middle = compute_sma(close, _bb_period)
        std = close.rolling(window=_bb_period, min_periods=_bb_period).std()
        upper = middle + _bb_std * std
        lower = middle - _bb_std * std
        return {"middle": middle, "upper": upper, "lower": lower}

    # ── _compute_indicators ─────────────────────────────────────────────

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula indicadores RSI y Bollinger Bands.

        Args:
            data: DataFrame con columna ``close``.
            symbol: Opcional para resolución de perfil.

        Returns:
            Dict con rsi, bb_upper, bb_middle, bb_lower, bb_position, bb_width.
        """
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile_key = "crypto" if is_crypto_symbol(symbol) else "stocks"
            profile = self._PROFILES[profile_key]
            bb_period: int = profile["bb_period"]
            bb_std: float = profile["bb_std"]
            rsi_period: int = profile["rsi_period"]
        else:
            bb_period = self.bb_period
            bb_std = self.bb_std
            rsi_period = self.rsi_period

        if "close" not in data.columns:
            return {"rsi": None, "bb_upper": None, "bb_middle": None, "bb_lower": None,
                    "bb_position": None, "bb_width": None}

        close = data["close"]
        if len(close) < max(bb_period, rsi_period) + 1:
            return {"rsi": None, "bb_upper": None, "bb_middle": None, "bb_lower": None,
                    "bb_position": None, "bb_width": None}

        bb = self._compute_bollinger(close, bb_period=bb_period, bb_std=bb_std)
        rsi = compute_rsi(close, rsi_period)

        last_close = float(close.iloc[-1])
        last_upper = float(bb["upper"].iloc[-1])
        last_middle = float(bb["middle"].iloc[-1])
        last_lower = float(bb["lower"].iloc[-1])
        last_rsi = float(rsi.iloc[-1])

        # BB position: 0.0 = lower, 0.5 = middle, 1.0 = upper
        bb_range = last_upper - last_lower
        bb_position = (last_close - last_lower) / bb_range if bb_range > 0 else 0.5
        bb_width = ((last_upper - last_lower) / last_middle * 100) if last_middle != 0 else 0.0

        return {
            "rsi": last_rsi,
            "bb_upper": last_upper,
            "bb_middle": last_middle,
            "bb_lower": last_lower,
            "bb_position": round(bb_position, 4),
            "bb_width": round(bb_width, 2),
            "close": last_close,
        }

    # ── BaseStrategy ────────────────────────────────────────────────────

    def generate_signal(
        self,
        data: pd.DataFrame,
        symbol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Genera señal de mean reversion.

        Args:
            data: DataFrame con columna ``close`` (obligatorio).
            symbol: Opcional. Si es crypto usa perfil crypto.

        Returns:
            Dict con action, price y metadata, o None.
        """
        # Resolver perfil a variables locales — no mutar self.*
        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile_key = "crypto" if is_crypto_symbol(symbol) else "stocks"
            profile = self._PROFILES[profile_key]
            bb_period: int = profile["bb_period"]
            bb_std: float = profile["bb_std"]
            rsi_period: int = profile["rsi_period"]
            rsi_oversold: int = profile["rsi_oversold"]
            rsi_overbought: int = profile["rsi_overbought"]
            max_bars_hold: int = profile["max_bars_hold"]
        else:
            bb_period = self.bb_period
            bb_std = self.bb_std
            rsi_period = self.rsi_period
            rsi_oversold = self.rsi_oversold
            rsi_overbought = self.rsi_overbought
            max_bars_hold = self.max_bars_hold

        if "close" not in data.columns:
            logger.warning("generate_signal: faltan columnas (close)")
            return None

        close = data["close"]
        if len(close) < max(bb_period, rsi_period) + 1:
            return None  # datos insuficientes

        # Delegar a _compute_indicators
        ind = self._compute_indicators(data, symbol)
        last_close = ind.get("close")
        last_lower = ind.get("bb_lower")
        last_middle = ind.get("bb_middle")
        last_upper = ind.get("bb_upper")
        last_rsi = ind.get("rsi")

        if any(v is None for v in [last_close, last_lower, last_middle, last_upper, last_rsi]):
            return None

        rsi_oversold_local = rsi_oversold
        rsi_overbought_local = rsi_overbought

        metadata = {
            "bb_lower": round(last_lower, 2),
            "bb_middle": round(last_middle, 2),
            "bb_upper": round(last_upper, 2),
            "rsi": round(last_rsi, 2),
        }

        # SEÑAL BUY: precio en banda inferior + RSI sobrevendido
        if last_close <= last_lower and last_rsi < rsi_oversold_local:
            return {
                "action": "BUY",
                "price": last_close,
                "metadata": metadata,
            }

        # SEÑAL SELL: precio alcanza banda media o RSI sobrecomprado
        sell_signal = False
        if self.exit_bb_middle and last_close >= last_middle:
            sell_signal = True
        if self.exit_rsi_overbought and last_rsi > rsi_overbought_local:
            sell_signal = True

        if sell_signal:
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
        """Explica las condiciones actuales de RSI y Bollinger Bands.

        Returns:
            Dict con indicadores, condiciones y señal.
        """
        ind = self._compute_indicators(data, symbol)
        signal = self.generate_signal(data, symbol)

        if symbol is not None:
            from royaltdn.scanner.universe import is_crypto_symbol

            profile_key = "crypto" if is_crypto_symbol(symbol) else "stocks"
            profile = self._PROFILES[profile_key]
            rsi_oversold = profile["rsi_oversold"]
            rsi_overbought = profile["rsi_overbought"]
        else:
            rsi_oversold = self.rsi_oversold
            rsi_overbought = self.rsi_overbought

        rsi_val = ind.get("rsi")
        bb_upper = ind.get("bb_upper")
        bb_lower = ind.get("bb_lower")
        bb_middle = ind.get("bb_middle")
        close_val = ind.get("close")
        bb_width = ind.get("bb_width")

        conditions = []

        if rsi_val is not None:
            # RSI Oversold condition
            conditions.append({
                "name": "RSI Oversold",
                "met": rsi_val < rsi_oversold,
                "value": round(rsi_val, 2),
                "threshold": float(rsi_oversold),
                "gap_pct": round(_calc_gap(rsi_val, float(rsi_oversold), "below"), 2),
                "direction": "below",
            })
            # RSI Overbought condition
            conditions.append({
                "name": "RSI Overbought",
                "met": rsi_val > rsi_overbought,
                "value": round(rsi_val, 2),
                "threshold": float(rsi_overbought),
                "gap_pct": round(_calc_gap(rsi_val, float(rsi_overbought), "above"), 2),
                "direction": "above",
            })

        if close_val is not None and bb_lower is not None:
            conditions.append({
                "name": "Close at Lower BB",
                "met": close_val <= bb_lower,
                "value": round(close_val, 2),
                "threshold": round(bb_lower, 2),
                "gap_pct": round(_calc_gap(close_val, bb_lower, "below"), 2),
                "direction": "below",
            })

        if close_val is not None and bb_middle is not None:
            conditions.append({
                "name": "Close above Middle BB",
                "met": close_val >= bb_middle,
                "value": round(close_val, 2),
                "threshold": round(bb_middle, 2),
                "gap_pct": round(_calc_gap(close_val, bb_middle, "above"), 2),
                "direction": "above",
            })

        if bb_width is not None:
            conditions.append({
                "name": "BB Width",
                "met": True,
                "value": bb_width,
                "threshold": 0.0,
                "gap_pct": 0.0,
                "direction": "above",
            })

        inds = {}
        if rsi_val is not None:
            inds["rsi"] = round(rsi_val, 2)
        if bb_upper is not None:
            inds["bb_upper"] = round(bb_upper, 2)
        if bb_middle is not None:
            inds["bb_middle"] = round(bb_middle, 2)
        if bb_lower is not None:
            inds["bb_lower"] = round(bb_lower, 2)
        if bb_width is not None:
            inds["bb_width"] = bb_width

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
                "crypto_bb_period": crypto["bb_period"],
                "crypto_bb_std": crypto["bb_std"],
                "crypto_rsi_period": crypto["rsi_period"],
                "crypto_rsi_oversold": crypto["rsi_oversold"],
                "crypto_rsi_overbought": crypto["rsi_overbought"],
                "crypto_max_bars_hold": crypto["max_bars_hold"],
                "crypto_timeframe": crypto["timeframe"],
                "stocks_bb_period": stocks["bb_period"],
                "stocks_bb_std": stocks["bb_std"],
                "stocks_rsi_period": stocks["rsi_period"],
                "stocks_rsi_oversold": stocks["rsi_oversold"],
                "stocks_rsi_overbought": stocks["rsi_overbought"],
                "stocks_max_bars_hold": stocks["max_bars_hold"],
                "stocks_timeframe": stocks["timeframe"],
            }
        from royaltdn.scanner.universe import is_crypto_symbol

        if is_crypto_symbol(symbol):
            return dict(self._PROFILES["crypto"])
        return dict(self._PROFILES["stocks"])

    def validate(self) -> bool:
        """Valida parámetros."""
        if self.bb_period <= 0:
            logger.error("bb_period debe ser > 0")
            return False
        if self.bb_std <= 0:
            logger.error("bb_std debe ser > 0")
            return False
        if self.rsi_period <= 0:
            logger.error("rsi_period debe ser > 0")
            return False
        if not (0 < self.rsi_oversold < self.rsi_overbought < 100):
            logger.error(
                "0 < rsi_oversold({}) < rsi_overbought({}) < 100",
                self.rsi_oversold, self.rsi_overbought,
            )
            return False
        return True
