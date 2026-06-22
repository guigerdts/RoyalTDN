"""Cell registry for the CellMesh architecture.

Maintains a central registry of all active cells, allowing lookup
by identifier and by trading symbol.
"""

from __future__ import annotations

from typing import Any


class CellRegistry:
    """Registry of active autonomous cells.

    Provides registration, unregistration, and query methods
    for all cells currently alive in the mesh.
    """

    def __init__(self) -> None:
        """Initialise an empty cell registry."""
        self._cells: list[dict[str, Any]] = []

    def register(self, cell: dict[str, Any]) -> None:
        """Register a cell in the registry.

        Args:
            cell: Cell descriptor dict. Must contain at least an ``id`` key.
        """
        self._cells.append(cell)

    def unregister(self, cell_id: str) -> None:
        """Remove a cell from the registry by its identifier.

        Args:
            cell_id: The unique identifier of the cell to remove.
        """
        self._cells = [c for c in self._cells if c.get("id") != cell_id]

    def get_all(self) -> list[dict[str, Any]]:
        """Return a shallow copy of all registered cells.

        Returns:
            List of all cell descriptor dicts.
        """
        return list(self._cells)

    def get_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        """Return cells that match the given trading symbol.

        Args:
            symbol: The trading pair symbol to filter by (e.g. 'BTC/USD').

        Returns:
            List of matching cell descriptor dicts.
        """
        return [c for c in self._cells if c.get("symbol") == symbol]
