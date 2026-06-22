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
    Additional rules (position sizing, volatility checks) can be
    added by subclassing or composing.
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

        Args:
            signal: Signal dict with ``action``, ``symbol``, ``price``,
                ``qty``. May be None.

        Returns:
            The approved signal dict, or None if rejected.
        """
        if signal is None:
            return None

        action = signal.get("action", "")

        if action == "BUY":
            # Position limit check
            current_positions = len(self.portfolio.positions)
            if current_positions >= self.max_positions:
                logger.info(
                    "RISK: Max positions alcanzado ({}), senal {} rechazada",
                    self.max_positions,
                    signal.get("symbol"),
                )
                return None

            # Drawdown check
            drawdown = self.portfolio.get_drawdown()
            if drawdown >= self.max_drawdown:
                logger.info(
                    "RISK: Drawdown maximo alcanzado ({:.2%}), senal {} rechazada",
                    drawdown,
                    signal.get("symbol"),
                )
                return None

        return signal
