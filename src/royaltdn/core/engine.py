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
        trade_tracker: Any = None,
    ) -> None:
        """Initialise the event engine.

        Args:
            clock: Clock instance (``RealClock`` or ``SimClock``).
            bus: EventBus instance for event IO.
            risk_manager: RiskManager for trade approval.
            execution_broker: PaperBroker or live broker for order
                execution.
            journal: Optional Journal instance for structured trade logging.
            trade_tracker: Optional TradeTracker instance for closed-trade
                recording and metrics.
        """
        self.clock = clock
        self.bus = bus
        self.risk_manager = risk_manager
        self.execution_broker = execution_broker
        self.journal = journal
        self.trade_tracker = trade_tracker
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

            if approved is None or not approved.get("approved", False):
                detail = (approved.get("detail", "Risk check failed")
                          if approved is not None else "Risk check failed")
                logger.info(
                    "Senal rechazada por risk manager: {} {} — {}",
                    signal_action, signal.get("symbol"), detail,
                )
                if self.journal is not None:
                    await self.journal.rejected(
                        symbol=signal.get("symbol", ""),
                        action=signal_action,
                        reason=detail,
                        trade_id=_trade_id,
                    )
                # Cell stays IDLE — it can retry on the next event.
                # This is crucial: previously the cell set state=
                # IN_POSITION BEFORE risk approval, so a rejection
                # would trap the cell permanently.
                continue

            # Risk check passed — update cell state based on action.
            # BUY after risk approval: normally a long entry, BUT if the
            # signal came from an IN_SHORT exit, it's a BUY-to-close and
            # we must NOT call enter_position() (the cell exits instead).
            # SHORT signals: mark the cell as IN_SHORT.
            enter_pos = getattr(cell, "enter_position", None)
            if signal_action == "BUY" and callable(enter_pos):
                # Check if this BUY is a normal long entry or a BUY-to-close
                # from an IN_SHORT exit. The cell's state tells us:
                # if cell.state == "IN_SHORT", this is buy-to-cover.
                cell_state = getattr(cell, "state", "IDLE")
                if cell_state == "IN_SHORT":
                    # BUY-to-close — do NOT enter_position, will exit later
                    pass
                else:
                    try:
                        enter_pos(approved.get("price", 0.0))
                    except Exception:
                        logger.exception(
                            "Error al marcar celula {} como IN_POSITION", cell_name,
                        )
            elif signal_action == "SHORT" and callable(enter_pos):
                try:
                    enter_pos(approved.get("price", 0.0), direction="short")
                except Exception:
                    logger.exception(
                        "Error al marcar celula {} como IN_SHORT", cell_name,
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

                # Update RiskManager's Portfolio (single source of truth —
                # M2: all state goes through Portfolio, not the broker).
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
                    _entry_price = approved.get("entry_price", 0.0)
                    _exit_price = approved.get("price", 0.0)
                    _qty = approved.get("qty", 0)

                    if _action == "BUY":
                        # BUY could be long entry or short close
                        cell_state = getattr(cell, "state", "IDLE")
                        if cell_state == "IN_SHORT":
                            # BUY-to-close → journal position_closed with short PnL
                            _pnl = (_entry_price - _exit_price) * _qty
                            await self.journal.position_closed(
                                _symbol, _pnl, _capital,
                                direction="short",
                                trade_id=_trade_id,
                            )
                        else:
                            await self.journal.position_opened(
                                _symbol, _capital, trade_id=_trade_id,
                            )
                    elif _action == "SHORT":
                        await self.journal.position_opened(
                            _symbol, _capital,
                            direction="short",
                            trade_id=_trade_id,
                        )
                    elif _action == "SELL":
                        _pnl = (_exit_price - _entry_price) * _qty
                        await self.journal.position_closed(
                            _symbol, _pnl, _capital,
                            trade_id=_trade_id,
                        )

                # -- TradeTracker recording (T3.2) ------------------------------------
                if self.trade_tracker is not None and signal_action == "SELL":
                    _entry = approved.get("entry_price", 0.0)
                    _exit_px = approved.get("price", 0.0)
                    _qty = approved.get("qty", 0)
                    _pnl = (_exit_px - _entry) * _qty
                    self.trade_tracker.record_trade(
                        symbol=approved.get("symbol", ""),
                        direction="long",
                        entry_price=_entry,
                        exit_price=_exit_px,
                        qty=_qty,
                        pnl=_pnl,
                        strategy_name=cell_name,
                        exit_time=str(self.clock.now()),
                        exit_reason="signal",
                    )
                elif self.trade_tracker is not None and signal_action == "BUY":
                    # Only record if this is a buy-to-close (closing a short)
                    cell_state = getattr(cell, "state", "IDLE")
                    if cell_state == "IN_SHORT":
                        _entry = approved.get("entry_price", 0.0)
                        _exit_px = approved.get("price", 0.0)
                        _qty = approved.get("qty", 0)
                        _pnl = (_entry - _exit_px) * _qty
                        self.trade_tracker.record_trade(
                            symbol=approved.get("symbol", ""),
                            direction="short",
                            entry_price=_entry,
                            exit_price=_exit_px,
                            qty=_qty,
                            pnl=_pnl,
                            strategy_name=cell_name,
                            exit_time=str(self.clock.now()),
                            exit_reason="signal",
                        )

                # Reset cell state after successful exit execution.
                exit_pos = getattr(cell, "exit_position", None)
                if signal_action in ("SELL", "BUY") and callable(exit_pos):
                    # For BUY, only call exit_position if this is a buy-to-close
                    if signal_action == "BUY":
                        cell_state = getattr(cell, "state", "IDLE")
                        if cell_state != "IN_SHORT":
                            exit_pos = None  # Don't exit — it's a long entry
                    if exit_pos is not None:
                        try:
                            exit_pos()
                        except Exception:
                            logger.exception(
                                "Error al marcar celula {} como IDLE tras {}",
                                cell_name, signal_action,
                            )

                logger.info(
                    "Trade ejecutado: {} {} {} @ ${:.2f} (orden: {})",
                    approved.get("symbol", ""),
                    approved.get("action", ""),
                    approved.get("qty", 0),
                    approved.get("price", 0.0),
                    result.get("order_id", ""),
                )

        # -- Mark-to-market update (T2.2) ------------------------------------
        try:
            self.risk_manager.portfolio.update_price(
                event.get("symbol", ""), event.get("price", 0.0),
            )
        except Exception:
            logger.exception("Error al actualizar precio en portfolio")

    def run_batch(self, events: list[dict]) -> None:
        """Process a batch of events synchronously (backtesting mode).

        For each event, creates a fresh event loop with ``asyncio.run()``
        so that all async processing (risk approval, broker submission,
        journal writes) completes before returning.

        Skips non-dict entries silently.

        This method was specified in the M4 backtester tasks but never
        implemented on ``EventEngine`` — the tests were written expecting
        it. Added retroactively on 2026-06-27 during branch restructuring
        (see architecture/merged-m1-m4-m5-telegram-chain-to-main).
        """
        import asyncio

        for event in events:
            if not isinstance(event, dict):
                continue
            try:
                asyncio.run(self._process_event(event))
            except Exception:
                logger.exception("Error en run_batch para evento: {}", event)

    def stop(self) -> None:
        """Gracefully stop the event processing loop."""
        self._running = False
        logger.info("EventEngine deteniendose...")
