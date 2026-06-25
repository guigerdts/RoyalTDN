"""Event engine for the CellMesh architecture.

Orchestrates the processing pipeline: consumes events from the bus,
routes them through registered cells, applies risk management, and
submits approved orders to the execution broker.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class EventEngine:
    """Core event processing engine.

    Runs a continuous loop that:

    1. Pulls the next event from the EventBus.
    2. Feeds it to every registered cell via ``cell.handle(event)``.
    3. If a cell returns a signal, emits a ``signal`` event to the bus.
    4. Submits the signal to the RiskManager for approval.
    5. If approved, submits the order to the ExecutionBroker.
    6. Emits a ``trade`` event on success and updates the broker's
       portfolio.
    """

    def __init__(
        self,
        clock: Any,
        bus: Any,
        risk_manager: Any,
        execution_broker: Any,
        journal: Any = None,
    ) -> None:
        """Initialise the event engine.

        Args:
            clock: Clock instance (``RealClock`` or ``SimClock``).
            bus: EventBus instance for event IO.
            risk_manager: RiskManager for trade approval.
            execution_broker: PaperBroker or live broker for order
                execution.
            journal: Optional Journal instance for structured trade logging.
        """
        self.clock = clock
        self.bus = bus
        self.risk_manager = risk_manager
        self.execution_broker = execution_broker
        self.journal = journal
        self.cells: list[Any] = []
        self._running = False

    def register(self, cell: Any) -> None:
        """Register a cell for event processing.

        Args:
            cell: Cell instance with an ``async handle(event)`` method.
        """
        self.cells.append(cell)
        logger.debug("Celula registrada: {}", getattr(cell, "name", str(cell)))

    async def run(self) -> None:
        """Main event processing loop.

        Continuously pulls events from the bus and processes them
        through all registered cells.
        """
        self._running = True
        logger.info("EventEngine iniciado — {} celulas registradas", len(self.cells))

        while self._running:
            try:
                event = await asyncio.wait_for(self.bus.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue  # no event pending, re-check _running
            except Exception:
                if self._running:
                    logger.exception("Error al obtener evento del bus")
                break

            if not self._running:
                break

            # Only market-data events should reach cells.  Events
            # re-emitted by the Journal (position, approved, rejected,
            # executed — all with type != "tick") carry no current
            # price, and feeding them to cells causes current_price =
            # event.get("price", 0.0) → 0.0, corrupting signals with
            # bogus prices (the original Bug 8).
            etype = event.get("type", "")
            if etype not in ("tick",):
                continue

            await self._process_event(event)

        logger.info("EventEngine detenido")

    async def _process_event(self, event: dict[str, Any]) -> None:
        """Route a single event through the processing pipeline.

        Args:
            event: The event dict to process.
        """
        for cell in self.cells:
            try:
                signal = await cell.handle(event)
            except Exception:
                logger.exception(
                    "Error en celula {} manejando evento",
                    getattr(cell, "name", "?"),
                )
                continue

            if signal is None:
                continue

            cell_name = getattr(cell, "name", "?")
            signal_action = signal.get("action", "")

            # -- Signal event ------------------------------------------------
            signal_event: dict[str, Any] = {
                "type": "signal",
                "symbol": signal.get("symbol", ""),
                "action": signal_action,
                "price": signal.get("price", 0.0),
                "qty": signal.get("qty", 0),
                "timestamp": str(self.clock.now()),
            }
            try:
                await self.bus.emit(signal_event)
            except Exception:
                logger.exception("Error al emitir evento de senal")

            _trade_id = ""
            if self.journal is not None:
                _trade_id = await self.journal.signal(
                    symbol=signal.get("symbol", ""),
                    action=signal_action,
                    price=signal.get("price", 0.0),
                    strategy=cell_name,
                )

            # -- Risk check --------------------------------------------------
            try:
                approved = self.risk_manager.approve(signal)
            except Exception:
                logger.exception("Error en risk manager al aprobar senal")
                continue

            if approved is None:
                logger.info(
                    "Senal rechazada por risk manager: {} {}",
                    signal_action,
                    signal.get("symbol"),
                )
                if self.journal is not None:
                    await self.journal.rejected(
                        symbol=signal.get("symbol", ""),
                        action=signal_action,
                        trade_id=_trade_id,
                    )
                # Cell stays IDLE — it can retry on the next event.
                # This is crucial: previously the cell set state=
                # IN_POSITION BEFORE risk approval, so a rejection
                # would trap the cell permanently.
                continue

            # Risk check passed — mark the cell as IN_POSITION for BUY signals.
            # (SELL signals change the cell state in _exit_signal before
            # returning, so we only update for BUY.)
            enter_pos = getattr(cell, "enter_position", None)
            if signal_action == "BUY" and callable(enter_pos):
                try:
                    enter_pos(approved.get("price", 0.0))
                except Exception:
                    logger.exception(
                        "Error al marcar celula {} como IN_POSITION", cell_name,
                    )

            if self.journal is not None:
                await self.journal.approved(
                    symbol=approved.get("symbol", ""),
                    action=signal_action,
                    trade_id=_trade_id,
                )

            # -- Execution ---------------------------------------------------
            try:
                result = await self.execution_broker.submit_order(approved)
            except Exception:
                logger.exception("Error al ejecutar orden")
                continue

            if result and result.get("status") in ("filled", "complete", "closed"):
                trade_event: dict[str, Any] = {
                    "type": "trade",
                    "symbol": approved.get("symbol", ""),
                    "action": approved.get("action", ""),
                    "qty": approved.get("qty", 0),
                    "price": approved.get("price", 0.0),
                    "order_id": result.get("order_id", ""),
                    "status": result.get("status", "filled"),
                }
                try:
                    await self.bus.emit(trade_event)
                except Exception:
                    logger.exception("Error al emitir evento de trade")

                if self.journal is not None:
                    await self.journal.executed(
                        symbol=approved.get("symbol", ""),
                        action=approved.get("action", ""),
                        qty=approved.get("qty", 0),
                        price=approved.get("price", 0.0),
                        trade_id=_trade_id,
                    )

                # Update broker's internal portfolio
                update_portfolio = getattr(
                    self.execution_broker, "update_portfolio", None
                )
                if callable(update_portfolio):
                    try:
                        update_portfolio(trade_event)
                    except Exception:
                        logger.exception(
                            "Error al actualizar portafolio del broker"
                        )

                # Sync RiskManager's Portfolio (Bug 4)
                try:
                    self.risk_manager.portfolio.update(trade_event)
                except Exception:
                    logger.exception(
                        "Error al actualizar portfolio del risk manager"
                    )

                # Journal position change (uses post-trade capital)
                if self.journal is not None:
                    _action = approved.get("action", "")
                    _symbol = approved.get("symbol", "")
                    _capital = self.risk_manager.portfolio.capital
                    if _action == "BUY":
                        await self.journal.position_opened(
                            _symbol, _capital,
                            trade_id=_trade_id,
                        )
                    elif _action == "SELL":
                        _entry = approved.get("entry_price", 0.0)
                        _exit_px = approved.get("price", 0.0)
                        _qty = approved.get("qty", 0)
                        _pnl = (_exit_px - _entry) * _qty
                        await self.journal.position_closed(
                            _symbol, _pnl, _capital,
                            trade_id=_trade_id,
                        )

                logger.info(
                    "Trade ejecutado: {} {} {} @ ${:.2f} (orden: {})",
                    approved.get("symbol", ""),
                    approved.get("action", ""),
                    approved.get("qty", 0),
                    approved.get("price", 0.0),
                    result.get("order_id", ""),
                )

    def stop(self) -> None:
        """Gracefully stop the event processing loop."""
        self._running = False
        logger.info("EventEngine deteniendose...")
