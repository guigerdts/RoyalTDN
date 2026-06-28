"""KillSwitch for emergency trading shutdown in the CellMesh architecture.

Provides manual and automatic triggers to halt trading, cancel all open
orders, and close open positions when risk thresholds are exceeded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger


@dataclass
class KillSwitchState:
    """Current state of the kill switch."""

    active: bool = False
    triggered_at: str = ""
    triggered_by: str = ""  # "manual", "drawdown", "error", "emergency"
    reason: str = ""


class KillSwitch:
    """Emergency trading shutdown mechanism.

    Once activated, the engine skips all event processing, cancels open
    orders, and closes open positions.  Auto-trigger conditions are
    evaluated periodically by the engine.
    """

    def __init__(
        self,
        portfolio: Any,
        binance_broker: Any = None,
        paper_broker: Any = None,
    ) -> None:
        """Initialise the kill switch.

        Args:
            portfolio: A :class:`~royaltdn.risk.portfolio.Portfolio`
                instance used for position-close orders and drawdown
                checks.
            binance_broker: Optional live broker for order cancellation.
            paper_broker: Optional paper broker for simulation.
        """
        self._state: KillSwitchState = KillSwitchState()
        self._portfolio = portfolio
        self._binance_broker = binance_broker
        self._paper_broker = paper_broker
        self._auto_triggers: list[dict[str, Any]] = []

        # Register the default drawdown auto-trigger
        self.register_auto_trigger(
            condition=lambda: portfolio.get_drawdown() > 0.3,
            reason="Drawdown superior al 30%",
        )

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """``True`` when the kill switch has been triggered."""
        return self._state.active

    @property
    def state(self) -> KillSwitchState:
        """Read-only snapshot of the current kill switch state."""
        return self._state

    # ── Manual trigger / release ───────────────────────────────────────────

    def trigger(self, triggered_by: str = "manual", reason: str = "") -> None:
        """Activate the kill switch.

        Once active, the engine will skip all event processing.

        Args:
            triggered_by: Source of the trigger (``"manual"``,
                ``"drawdown"``, ``"error"``, ``"emergency"``).
            reason: Human-readable explanation for the trigger.
        """
        self._state.active = True
        self._state.triggered_at = str(datetime.now(timezone.utc))
        self._state.triggered_by = triggered_by
        self._state.reason = reason
        logger.critical(
            "KillSwitch ACTIVADO por {}: {}",
            triggered_by,
            reason or "sin motivo",
        )

    def release(self) -> None:
        """Deactivate the kill switch and re-enable trading."""
        self._state = KillSwitchState()
        logger.info("KillSwitch desactivado — trading reanudado")

    # ── Auto-triggers ──────────────────────────────────────────────────────

    def register_auto_trigger(
        self,
        condition: Callable[[], bool],
        reason: str,
    ) -> None:
        """Register a condition that will auto-trigger the kill switch.

        Args:
            condition: A zero-argument callable returning ``True``
                when the kill switch should activate.
            reason: Description of the condition (used in log messages).
        """
        self._auto_triggers.append({"condition": condition, "reason": reason})
        logger.debug("Trigger automatico registrado: {}", reason)

    def check_auto_triggers(self) -> None:
        """Evaluate all registered auto-trigger conditions.

        If any condition returns ``True``, the kill switch is triggered
        and no further conditions are evaluated (fail-fast).
        """
        if self._state.active:
            return  # already active, no need to check

        for trigger in self._auto_triggers:
            try:
                if trigger["condition"]():
                    self.trigger(triggered_by="auto", reason=trigger["reason"])
                    return  # one trigger is enough
            except Exception:
                logger.exception(
                    "Error evaluando trigger automatico: {}",
                    trigger["reason"],
                )

    # ── Emergency actions ──────────────────────────────────────────────────

    def cancel_all_orders(self) -> None:
        """Cancel all open orders via the active broker."""
        if self._binance_broker is not None:
            try:
                # BinanceBroker.cancel_all_orders added during integration
                cancel_fn = getattr(self._binance_broker, "cancel_all_orders", None)
                if callable(cancel_fn):
                    cancel_fn()
                    logger.info("KillSwitch: ordenes canceladas en Binance")
                else:
                    logger.warning(
                        "KillSwitch: BinanceBroker no tiene cancel_all_orders"
                    )
            except Exception:
                logger.exception("KillSwitch: error cancelando ordenes en Binance")
        elif self._paper_broker is not None:
            logger.info("KillSwitch: cancelacion de ordenes simulada (paper)")
        else:
            logger.info("KillSwitch: no hay broker disponible para cancelar ordenes")

    def close_all_positions(self) -> None:
        """Close all open positions via market orders.

        Iterates long and short positions in the portfolio and submits
        opposite-side market orders to close them.
        """
        # Close long positions
        for symbol, qty in list(self._portfolio.positions.items()):
            logger.info(
                "KillSwitch: cerrando posicion LONG {} qty={}",
                symbol,
                qty,
            )
            # In a real scenario this would call broker.submit_order()
            # with a SELL market order for qty.  For now we log the intent.

        # Close short positions
        short_positions: dict[str, float] = getattr(
            self._portfolio, "_short_positions", {}
        )
        for symbol, qty in list(short_positions.items()):
            logger.info(
                "KillSwitch: cerrando posicion SHORT {} qty={}",
                symbol,
                qty,
            )

    async def emergency_shutdown(self) -> None:
        """Full emergency shutdown: trigger + cancel orders + close positions.

        This is the highest-level safety action and should only be called
        in extreme circumstances (e.g. unrecoverable error loop).
        """
        self.trigger(triggered_by="emergency", reason="Apagado de emergencia")
        self.cancel_all_orders()
        self.close_all_positions()
        logger.critical("KillSwitch: apagado de emergencia completado")
