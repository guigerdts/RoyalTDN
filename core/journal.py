"""Structured trading journal for CellMesh.

Persists every trading event (signal, approval, execution, position
changes) to a JSON Lines file for post-hoc analysis and auditability.
Also emits events to the EventBus for real-time dashboard display.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Journal:
    """Structured trading journal.

    Writes a JSON Lines file at *log_path* and optionally emits every
    record to the EventBus for real-time dashboard consumption.

    File is opened in append mode on every write, ensuring atomicity
    even under concurrent access (each line is a complete JSON object).
    """

    def __init__(
        self,
        log_path: str = "logs/trading.log",
        bus: Any = None,
    ) -> None:
        """Initialise the journal.

        Args:
            log_path: Path to the JSON Lines output file.
            bus: Optional EventBus instance for real-time emission.
        """
        self.log_path = log_path
        self.bus = bus
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> str:
        """Return an ISO-8601 UTC timestamp string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _write(self, record: dict[str, Any]) -> None:
        """Atomically append a JSON line to the journal file.

        Uses ``os.fsync`` to guarantee durability (data reaches disk)
        before returning.
        """
        line = json.dumps(record, default=str) + "\n"
        with open(self.log_path, "a") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    async def _emit(self, record: dict[str, Any]) -> None:
        """Best-effort emission to the EventBus."""
        if self.bus is not None:
            try:
                await self.bus.emit(record)
            except Exception:
                pass  # bus emission is best-effort — never break the pipeline

    # ------------------------------------------------------------------
    # Generic log entry
    # ------------------------------------------------------------------

    async def log(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """Write a trading event to the journal and emit to the bus.

        Args:
            event_type: Event category (e.g. ``"signal"``, ``"approved"``,
                ``"executed"``, ``"position"``).
            data: Event-specific fields (symbol, action, price, etc.).

        Returns:
            The full record dict (timestamp + type + data) for callers
            that want to inspect or forward it.
        """
        record: dict[str, Any] = {
            "timestamp": self._now(),
            "type": event_type,
        }
        record.update(data)
        await self._write(record)
        await self._emit(record)
        return record

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Trade-ID generation
    # ------------------------------------------------------------------

    @staticmethod
    def _new_id() -> str:
        """Generate a unique trade identifier."""
        return uuid.uuid4().hex[:12]

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    async def signal(
        self,
        symbol: str,
        action: str,
        price: float,
        strategy: str,
        trade_id: str | None = None,
    ) -> str:
        """Record a trading signal emitted by a cell.

        Args:
            symbol: Trading pair symbol.
            action: ``"BUY"`` or ``"SELL"``.
            price: Signal price.
            strategy: Cell / strategy name.
            trade_id: Optional existing ID.  If omitted a new one is
                generated.

        Returns:
            The ``trade_id`` for this trade — pass it to subsequent
            journal calls (``approved``, ``executed``, etc.) so events
            are linked.
        """
        tid = trade_id or self._new_id()
        await self.log("signal", {
            "trade_id": tid,
            "symbol": symbol,
            "action": action,
            "price": price,
            "strategy": strategy,
        })
        return tid

    async def approved(
        self,
        symbol: str,
        action: str,
        reason: str = "risk_check_passed",
        trade_id: str = "",
    ) -> dict[str, Any]:
        """Record a signal passing the risk management gate."""
        return await self.log("approved", {
            "trade_id": trade_id,
            "symbol": symbol,
            "action": action,
            "reason": reason,
        })

    async def rejected(
        self,
        symbol: str,
        action: str,
        reason: str = "risk_rejected",
        trade_id: str = "",
    ) -> dict[str, Any]:
        """Record a signal rejected by the risk manager."""
        return await self.log("rejected", {
            "trade_id": trade_id,
            "symbol": symbol,
            "action": action,
            "reason": reason,
        })

    async def executed(
        self,
        symbol: str,
        action: str,
        qty: float,
        price: float,
        trade_id: str = "",
    ) -> dict[str, Any]:
        """Record a successfully filled order."""
        return await self.log("executed", {
            "trade_id": trade_id,
            "symbol": symbol,
            "action": action,
            "qty": qty,
            "price": price,
        })

    async def position_opened(
        self,
        symbol: str,
        capital: float,
        trade_id: str = "",
    ) -> dict[str, Any]:
        """Record a new position being opened."""
        return await self.log("position", {
            "trade_id": trade_id,
            "symbol": symbol,
            "status": "opened",
            "capital": capital,
        })

    async def position_closed(
        self,
        symbol: str,
        pnl: float,
        capital: float,
        trade_id: str = "",
    ) -> dict[str, Any]:
        """Record a position being closed."""
        return await self.log("position", {
            "trade_id": trade_id,
            "symbol": symbol,
            "status": "closed",
            "pnl": round(pnl, 2),
            "capital": capital,
        })
