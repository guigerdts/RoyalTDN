"""Base Cell class for the CellMesh architecture.

Each Cell monitors a single trading symbol, accumulates market data,
evaluates entry/exit rules via the InferenceEngine, and emits trading
signals when conditions are met.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class Cell:
    """Autonomous trading cell.

    Maintains internal bar history and state machine (IDLE / IN_POSITION).
    On each tick event, evaluates entry or exit rules and returns a
    trading signal dict when triggered.
    """

    def __init__(
        self,
        config: dict[str, Any],
        inference_engine: Any = None,
    ) -> None:
        """Initialise the cell from a YAML config block.

        Args:
            config: Dict with keys ``name``, ``symbol``, ``qty``,
                ``stop_loss``, ``take_profit``, ``entry``, ``exit``.
            inference_engine: InferenceEngine instance for rule evaluation.
        """
        self.name: str = config.get("name", "unnamed")
        self.symbol: str = config.get("symbol", "")
        self.state: str = "IDLE"
        self.qty: float = float(config.get("qty", 0.01))
        self.stop_loss_pct: float = float(config.get("stop_loss", 0.0))
        self.take_profit_pct: float = float(config.get("take_profit", 0.0))

        self.config: dict[str, Any] = config
        self.inference_engine: Any = inference_engine
        self.entry_config: dict[str, Any] = config.get("entry", {})
        self.exit_config: dict[str, Any] = config.get("exit", {})

        self.bars: list[dict[str, float]] = []
        self.entry_price: float = 0.0

    async def handle(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Process a market event and return a trading signal if triggered.

        Args:
            event: Event dict with at least ``symbol``, ``type``, ``price``,
                and an optional ``data`` dict containing OHLCV fields.

        Returns:
            A signal dict (``action``, ``symbol``, ``price``, ``qty``) or
            None if no action is required.
        """
        # Ignore events for other symbols
        if event.get("symbol") != self.symbol:
            return None

        # Accumulate bar data
        data = event.get("data")
        if data and isinstance(data, dict):
            self.bars.append(data)

        current_price = event.get("price", 0.0)

        if self.state == "IDLE":
            return await self._check_entry(current_price)

        if self.state == "IN_POSITION":
            return self._check_exit(current_price)

        return None

    async def _check_entry(self, current_price: float) -> dict[str, Any] | None:
        """Evaluate entry conditions.

        Returns a BUY signal if the inference engine confirms the entry
        config against accumulated market data.
        """
        if not self.entry_config or not self.inference_engine:
            return None

        market_data = self._build_data()
        try:
            should_enter = self.inference_engine.evaluate(
                self.entry_config, market_data
            )
        except Exception:
            logger.exception("Error evaluando condiciones de entrada para {}", self.name)
            return None

        if not should_enter:
            return None

        self.state = "IN_POSITION"
        self.entry_price = current_price
        logger.info(
            "{} {} ENTRADA @ ${:.2f}",
            self.symbol,
            self.name,
            current_price,
        )
        return {
            "action": "BUY",
            "symbol": self.symbol,
            "price": current_price,
            "qty": self.qty,
        }

    def _check_exit(self, current_price: float) -> dict[str, Any] | None:
        """Evaluate exit conditions (stop-loss, take-profit, or rule-based).

        Returns a SELL signal if any exit condition is met.
        """
        if self.entry_price == 0.0:
            return None

        # Stop-loss check
        if self.stop_loss_pct > 0.0:
            stop_price = self.entry_price * (1.0 - self.stop_loss_pct)
            if current_price <= stop_price:
                logger.info(
                    "{} {} STOP-LOSS @ ${:.2f} (entry ${:.2f})",
                    self.symbol,
                    self.name,
                    current_price,
                    self.entry_price,
                )
                return self._exit_signal(current_price)

        # Take-profit check
        if self.take_profit_pct > 0.0:
            take_price = self.entry_price * (1.0 + self.take_profit_pct)
            if current_price >= take_price:
                logger.info(
                    "{} {} TAKE-PROFIT @ ${:.2f} (entry ${:.2f})",
                    self.symbol,
                    self.name,
                    current_price,
                    self.entry_price,
                )
                return self._exit_signal(current_price)

        # Rule-based exit
        if self.exit_config and self.inference_engine:
            market_data = self._build_data()
            try:
                should_exit = self.inference_engine.evaluate(
                    self.exit_config, market_data
                )
            except Exception:
                logger.exception("Error evaluando condiciones de salida para {}", self.name)
                return None

            if should_exit:
                return self._exit_signal(current_price)

        return None

    def _exit_signal(self, current_price: float) -> dict[str, Any]:
        """Generate a SELL signal and reset cell state."""
        self.state = "IDLE"
        entry_price = self.entry_price
        self.entry_price = 0.0
        return {
            "action": "SELL",
            "symbol": self.symbol,
            "price": current_price,
            "qty": self.qty,
        }

    def _build_data(self) -> dict[str, list[float]]:
        """Build a market-data dict from accumulated bars.

        Returns:
            Dict with ``close``, ``volume``, ``high``, ``low`` lists.
        """
        return {
            "close": [b.get("close", 0.0) for b in self.bars],
            "volume": [b.get("volume", 0.0) for b in self.bars],
            "high": [b.get("high", 0.0) for b in self.bars],
            "low": [b.get("low", 0.0) for b in self.bars],
        }
