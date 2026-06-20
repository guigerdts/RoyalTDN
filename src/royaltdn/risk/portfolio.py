"""
RoyalTDN — Portfolio Position Manager (Fase 16)

Multi-symbol position tracking for scanner auto-execution.
Each position is tracked per symbol with exposure calculations.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Position:
    symbol: str
    side: str           # "long" | "short"
    qty: float
    entry_price: float
    strategy: str       # "scanner" | "legacy" | "sma_crossover" | ...
    opened_at: datetime


class PortfolioPositionManager:
    """Manages multiple positions across symbols."""

    def __init__(self) -> None:
        self._positions: Dict[str, Position] = {}

    def open_position(self, symbol: str, qty: float, entry_price: float,
                      strategy: str = "scanner", side: str = "long") -> Position:
        """Open a new position. Raises ValueError if position exists."""
        if symbol in self._positions:
            raise ValueError(f"Position already exists for {symbol}")
        pos = Position(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            strategy=strategy,
            opened_at=datetime.utcnow(),
        )
        self._positions[symbol] = pos
        return pos

    def close_position(self, symbol: str) -> Optional[Position]:
        """Close and remove a position. Returns None if not found."""
        return self._positions.pop(symbol, None)

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all open positions keyed by symbol."""
        return dict(self._positions)

    def position_count(self) -> int:
        """Number of open positions."""
        return len(self._positions)

    def has_position(self, symbol: str) -> bool:
        """Check if a position exists for the given symbol."""
        return symbol in self._positions

    def get_symbol_exposure(self, symbol: str, account_equity: float) -> float:
        """Return exposure fraction (0.0 to 1.0) for a specific symbol.

        Formula: (qty * entry_price) / account_equity.

        Args:
            symbol: Symbol to check exposure for.
            account_equity: Current account equity.

        Returns:
            float: Exposure as fraction of equity. 0.0 if position not found
            or equity is 0.
        """
        pos = self._positions.get(symbol)
        if not pos or account_equity <= 0:
            return 0.0
        return (pos.qty * pos.entry_price) / account_equity

    def get_total_exposure(self, account_equity: float) -> float:
        """Return total portfolio exposure as fraction of equity.

        Formula: sum(qty * entry_price for all positions) / account_equity.

        Args:
            account_equity: Current account equity.

        Returns:
            float: Total exposure as fraction of equity. 0.0 if no positions
            or equity is 0.
        """
        if account_equity <= 0 or not self._positions:
            return 0.0
        total_value = sum(p.qty * p.entry_price for p in self._positions.values())
        return total_value / account_equity

    def close_all_positions(self) -> List[Position]:
        """Close all positions and return the list."""
        closed = list(self._positions.values())
        self._positions.clear()
        return closed
