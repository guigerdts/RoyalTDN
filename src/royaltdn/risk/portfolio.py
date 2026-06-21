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
    broker: str = "alpaca"   # broker name (FASE 17 multi-broker)


class PortfolioPositionManager:
    """Manages multiple positions across symbols.

    Uses a composite key ``f"{broker}:{symbol}"`` internally so that the
    same symbol can be traded on different brokers without collision.
    """

    def __init__(self) -> None:
        self._positions: Dict[str, Position] = {}

    # ── Key helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _make_key(symbol: str, broker: str) -> str:
        """Build the composite internal key."""
        return f"{broker}:{symbol}"

    @staticmethod
    def _symbol_from_key(key: str) -> str:
        """Extract the symbol portion from a composite key."""
        return key.split(":", 1)[-1]

    @staticmethod
    def _broker_from_key(key: str) -> str:
        """Extract the broker portion from a composite key."""
        return key.split(":", 1)[0]

    # ── Core operations ─────────────────────────────────────────────────

    def open_position(self, symbol: str, qty: float, entry_price: float,
                      strategy: str = "scanner", side: str = "long",
                      broker: str = "alpaca") -> Position:
        """Open a new position. Raises ValueError if position exists.

        Args:
            symbol: Trading symbol (e.g. "SPY", "BTC/USD").
            qty: Number of shares / units.
            entry_price: Entry price per share.
            strategy: Strategy name (default "scanner").
            side: "long" or "short" (default "long").
            broker: Broker name (default "alpaca").
        """
        key = self._make_key(symbol, broker)
        if key in self._positions:
            raise ValueError(f"Position already exists for {broker}:{symbol}")
        pos = Position(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            strategy=strategy,
            opened_at=datetime.utcnow(),
            broker=broker,
        )
        self._positions[key] = pos
        return pos

    def close_position(self, symbol: str, broker: Optional[str] = None) -> Optional[Position]:
        """Close and remove a position.

        Args:
            symbol: Symbol to close.
            broker: Broker name. If provided, uses composite key lookup.
                    If None, searches all keys for matching symbol.

        Returns:
            The removed Position, or None if not found.
        """
        if broker:
            return self._positions.pop(self._make_key(symbol, broker), None)
        # Fallback: search all keys for the symbol
        for key, pos in list(self._positions.items()):
            if self._symbol_from_key(key) == symbol:
                return self._positions.pop(key, None)
        return None

    def get_position(self, symbol: str, broker: Optional[str] = None) -> Optional[Position]:
        """Get position for a symbol.

        Args:
            symbol: Symbol to look up.
            broker: Broker name. If provided, uses composite key.
                    If None, searches all keys.

        Returns:
            Position or None.
        """
        if broker:
            return self._positions.get(self._make_key(symbol, broker))
        for key, pos in self._positions.items():
            if self._symbol_from_key(key) == symbol:
                return pos
        return None

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all open positions keyed by composite key (``broker:symbol``)."""
        return dict(self._positions)

    def position_count(self) -> int:
        """Number of open positions."""
        return len(self._positions)

    def has_position(self, symbol: str, broker: Optional[str] = None) -> bool:
        """Check if a position exists for the given symbol.

        Args:
            symbol: Symbol to check.
            broker: Broker name. If provided, checks exact composite key.
                    If None, searches all positions.

        Returns:
            True if a matching position exists.
        """
        if broker:
            return self._make_key(symbol, broker) in self._positions
        return any(self._symbol_from_key(k) == symbol for k in self._positions)

    # ── Multi-broker helpers ────────────────────────────────────────────

    def get_positions_by_broker(self, broker_name: str) -> Dict[str, Position]:
        """Return all positions for a specific broker.

        Args:
            broker_name: Broker name (e.g. "alpaca", "binance").

        Returns:
            Dict of {symbol: Position} for the given broker.
        """
        result = {}
        for key, pos in self._positions.items():
            if self._broker_from_key(key) == broker_name:
                result[pos.symbol] = pos
        return result

    def get_symbol_exposure(self, symbol: str, account_equity: float,
                            broker: Optional[str] = None) -> float:
        """Return exposure fraction (0.0 to 1.0) for a specific symbol.

        Formula: (qty * entry_price) / account_equity.

        Args:
            symbol: Symbol to check exposure for.
            account_equity: Current account equity.
            broker: Optional broker filter. If provided, checks only
                    positions on that broker.

        Returns:
            float: Exposure as fraction of equity. 0.0 if position not found
            or equity is 0.
        """
        pos = self.get_position(symbol, broker=broker)
        if not pos or account_equity <= 0:
            return 0.0
        return (pos.qty * pos.entry_price) / account_equity

    def get_total_exposure(self, account_equity: float) -> float:
        """Return total portfolio exposure as fraction of equity.

        Formula: sum(qty * entry_price for all positions) / account_equity.

        Args:
            account_equity: Total account equity (aggregated across brokers).

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
