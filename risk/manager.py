"""Risk manager for the CellMesh architecture.

Evaluates trading signals against portfolio constraints and market
conditions before allowing execution.
"""

from __future__ import annotations

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
    ) -> None:
        """Initialise the risk manager.

        Args:
            portfolio: Portfolio instance for state queries.
            max_positions: Maximum number of concurrent long positions.
            max_drawdown: Maximum allowed drawdown fraction (0.03 = 3%).
        """
        self.portfolio = portfolio
        self.max_positions = max_positions
        self.max_drawdown = max_drawdown

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
