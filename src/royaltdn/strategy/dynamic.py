"""DynamicStrategy — strategy defined at runtime from a JSON config.

Evaluates indicator-based rule trees on OHLCV data and generates
BUY/SELL signals.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.indicators import (
    ADX, ATR, BollingerBands, EMA, Ichimoku, MACD, OBV, ParabolicSAR,
    RSI, SMA, SmartMoneyFlowCloud, Stochastic, SuperTrend, VWAP,
    Volume, ZScore,
)
from royaltdn.strategy.rule_engine import evaluate
from royaltdn.strategy.schema import validate_config

# Mapping for dynamic indicator dispatch
INDICATOR_FUNCS = {
    "SMA": SMA,
    "EMA": EMA,
    "RSI": RSI,
    "MACD": MACD,
    "BollingerBands": BollingerBands,
    "ATR": ATR,
    "Volume": Volume,
    "Ichimoku": Ichimoku,
    "SuperTrend": SuperTrend,
    "VWAP": VWAP,
    "ZScore": ZScore,
    "ADX": ADX,
    "OBV": OBV,
    "Stochastic": Stochastic,
    "ParabolicSAR": ParabolicSAR,
    "SmartMoneyFlowCloud": SmartMoneyFlowCloud,
}


class DynamicStrategy(BaseStrategy):
    """A strategy built from a JSON config with indicators and rule trees.

    Attributes:
        config: The raw JSON config dict.
        name: Strategy name from config.
        symbols: List of trading symbols.
        timeframe: Resolution from config.
    """

    def __init__(self, config: dict):
        super().__init__(timeframe=config.get("timeframe", "1D"))
        self.config = config
        self._name: str = config.get("name", "unnamed")
        self.symbols: list[str] = config.get("symbols", [])
        self._entry_rules: dict = config.get("entry_rules", {})
        self._exit_rules: dict = config.get("exit_rules", {})
        self._indicators_config: list[dict] = config.get("indicators", [])
        self._risk: dict = config.get("risk_management", {})

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    # ── Constructors ────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: str) -> "DynamicStrategy":
        """Load a strategy from a JSON file.

        Args:
            path: Path to the JSON config file.

        Returns:
            A new DynamicStrategy instance.
        """
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return cls(config)

    # ── Signal generation ───────────────────────────────────────────────

    def generate_signal(self, data: pd.DataFrame) -> Optional[dict[str, Any]]:
        """Evaluate rules on data and return a signal dict or None.

        Args:
            data: OHLCV DataFrame with at least open/high/low/close/volume.

        Returns:
            Dict with action/price/symbol/timestamp/strategy/risk,
            or None if no signal matches.
        """
        if data.empty or len(data) < 2:
            return None

        # 1. Compute all configured indicators
        indicators: dict[str, Any] = {}
        for ind_cfg in self._indicators_config:
            name = ind_cfg["name"]
            params = ind_cfg.get("params", {})
            func = INDICATOR_FUNCS.get(name)
            if func is None:
                continue
            try:
                result = func(data, **params)
                if result is not None:
                    indicators[name] = result
            except Exception:
                # Silently skip failed indicator computation
                continue

        # 2. Add raw price data as pseudo-indicators for reference
        #    (needed by some operators like inside_band that access data)
        price = data["close"]

        # 3. Evaluate entry rules
        if self._entry_rules.get("conditions"):
            try:
                entry_hit = evaluate(self._entry_rules, indicators, data)
            except Exception:
                entry_hit = False
        else:
            entry_hit = False

        if entry_hit:
            now = datetime.now(timezone.utc).isoformat()
            return {
                "action": "BUY",
                "symbol": self.symbols[0] if self.symbols else "UNKNOWN",
                "price": float(price.iloc[-1]),
                "timestamp": now,
                "strategy": self._name,
                "risk": self._risk,
            }

        # 4. Evaluate exit rules
        if self._exit_rules.get("conditions"):
            try:
                exit_hit = evaluate(self._exit_rules, indicators, data)
            except Exception:
                exit_hit = False
        else:
            exit_hit = False

        if exit_hit:
            now = datetime.now(timezone.utc).isoformat()
            return {
                "action": "SELL",
                "symbol": self.symbols[0] if self.symbols else "UNKNOWN",
                "price": float(price.iloc[-1]),
                "timestamp": now,
                "strategy": self._name,
                "risk": self._risk,
            }

        return None

    def get_parameters(self) -> dict[str, Any]:
        """Return the full config as parameters."""
        return dict(self.config)

    def validate(self) -> bool:
        """Validate the config against the schema."""
        ok, _ = validate_config(self.config)
        return ok
