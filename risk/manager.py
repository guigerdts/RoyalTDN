"""Risk manager for the CellMesh architecture.

Evaluates trading signals against portfolio constraints and market
conditions before allowing execution.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger


class RiskManager:
    """Trade approval gate.

    Enforces:
    - Maximum number of concurrent positions.
    - Maximum drawdown threshold.
    - Calculates position size from capital + sizing fraction.
    """

    def __init__(
        self,
        portfolio: Any,
        max_positions: int = 5,
        max_drawdown: float = 0.03,
        config_path: str | Path | None = None,
    ) -> None:
        """Initialise the risk manager.

        Args:
            portfolio: Portfolio instance for state queries.
            max_positions: Maximum number of concurrent long positions.
            max_drawdown: Maximum allowed drawdown fraction (0.03 = 3%).
            config_path: Path to ``config.yaml``. When set, ``max_positions``
                is re-read from the file periodically so that live changes
                take effect without restarting the bot.
        """
        self.portfolio = portfolio
        self.max_positions = max_positions
        self.max_drawdown = max_drawdown
        self._config_path: Path | None = Path(config_path) if config_path else None
        self._last_config_reload: float = 0.0
        self._config_reload_interval: float = 60.0  # seconds

    def _reload_config_if_needed(self) -> None:
        """Re-read ``max_positions`` from ``config.yaml`` if enough time has
        passed since the last read."""
        if self._config_path is None:
            return
        now = time.monotonic()
        if now - self._last_config_reload < self._config_reload_interval:
            return
        self._last_config_reload = now
        try:
            import yaml
            with open(self._config_path) as f:
                cfg = yaml.safe_load(f)
            cfg_max = cfg.get("max_positions")
            if cfg_max is not None and isinstance(cfg_max, (int, float)):
                old = self.max_positions
                self.max_positions = int(cfg_max)
                if old != self.max_positions:
                    logger.info(
                        "RiskManager: max_positions actualizado {} -> {} (desde config.yaml)",
                        old, self.max_positions,
                    )
        except Exception as exc:
            logger.warning("RiskManager: no se pudo releer config.yaml: {}", exc)

    def approve(self, signal: dict[str, Any] | None) -> dict[str, Any] | None:
        """Approve or reject a trading signal.

        For BUY signals: checks position limit, drawdown,
        then calculates actual share qty = (capital * sizing) / price.

        Args:
            signal: Signal dict with ``action``, ``symbol``, ``price``,
                ``sizing`` (fraction of capital). May be None.

        Returns:
            The approved signal dict with ``qty`` added, or None if rejected.
        """
        if signal is None:
            return None

        # Re-read max_positions from config.yaml periodically
        self._reload_config_if_needed()

        action = signal.get("action", "")
        symbol = signal.get("symbol", "")
        price = float(signal.get("price", 0))
        sizing = float(signal.get("sizing", 0.01))

        if action == "BUY":
            # Duplicate position check
            if symbol in self.portfolio.positions:
                logger.info(
                    "RISK: {} ya en posicion — senal rechazada", symbol,
                )
                return None

            # Position limit check
            current_positions = len(self.portfolio.positions)
            logger.info(
                "RiskManager: checking signal — positions={}/{}",
                current_positions, self.max_positions,
            )
            if current_positions >= self.max_positions:
                logger.info(
                    "RISK: Max positions ({}) alcanzado — {} rechazada",
                    self.max_positions, symbol,
                )
                return None

            # Drawdown check
            drawdown = self.portfolio.get_drawdown()
            if drawdown >= self.max_drawdown:
                logger.info(
                    "RISK: Drawdown maximo ({:.2%}) — {} rechazada",
                    drawdown, symbol,
                )
                return None

            # Calculate qty from capital * sizing / price (Bug 3)
            capital = self.portfolio.capital
            if capital <= 0 or price <= 0:
                logger.info("RISK: Capital o precio invalido — {} rechazada", symbol)
                return None

            raw_qty = (capital * sizing) / price
            # Minimum trade: 0.1% of capital worth of asset (prevents dust)
            min_qty = (capital * 0.001) / price if price > 0 else 0.0
            qty = max(min_qty, raw_qty)
            signal["qty"] = qty

            logger.info(
                "RISK: {} {} aprobada — qty={:.4f} (capital=${:.2f}, sizing={:.2%}, price=${:.2f})",
                action, symbol, qty, capital, sizing, price,
            )

        elif action == "SELL":
            # SELL always passes (any open position can be closed)
            qty = self.portfolio.positions.get(symbol, 0.0)
            if qty <= 0:
                logger.info("RISK: {} no tiene posicion para vender — rechazada", symbol)
                return None
            signal["qty"] = qty

        return signal
