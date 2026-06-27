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

    Maintains internal bar history and state machine
    (IDLE / IN_POSITION / IN_SHORT).
    On each tick event, evaluates entry or exit rules and returns a
    trading signal dict when triggered.
    """

    # ── State constants ────────────────────────────────────────────────
    IN_LONG = "IN_POSITION"      # semantic alias for new code
    IN_SHORT = "IN_SHORT"        # short position state

    def __init__(
        self,
        config: dict[str, Any],
        inference_engine: Any = None,
    ) -> None:
        """Initialise the cell from a YAML config block.

        Args:
            config: Dict with keys ``name``, ``symbol``, ``entry``,
                ``short_entry``, ``exit`` (list),
                ``risk`` (dict with ``sizing``).
            inference_engine: InferenceEngine instance for rule evaluation.
        """
        self.name: str = config.get("name", "unnamed")
        self.symbol: str = config.get("symbol", "")
        self.state: str = "IDLE"

        # ── Parse risk config ──────────────────────────────────────────
        risk_cfg: dict = config.get("risk", {})
        self.sizing: float = float(risk_cfg.get("sizing", 0.01))
        self.max_positions: int = int(risk_cfg.get("max_positions", 5))

        # ── Inference engine + pre-built graphs ────────────────────────
        self.config: dict[str, Any] = config
        self.inference_engine: Any = inference_engine
        self.entry_config: dict[str, Any] = config.get("entry", {})
        self.short_entry_config: dict[str, Any] = config.get("short_entry", {})

        # Pre‑build the entry condition graph ONCE (Bug 6)
        self._entry_graph: Any = None
        if self.entry_config and self.inference_engine:
            from royaltdn.inference.graph import build_graph
            try:
                self._entry_graph = build_graph(self.entry_config)
            except Exception:
                logger.exception("Error construyendo grafo de entrada para {}", self.name)

        # Pre‑build the short entry condition graph ONCE
        self._short_entry_graph: Any = None
        if self.short_entry_config and self.inference_engine:
            from royaltdn.inference.graph import build_graph
            try:
                self._short_entry_graph = build_graph(self.short_entry_config)
            except Exception:
                logger.exception("Error construyendo grafo de entrada short para {}", self.name)

        # ── Parse exit list (YAML: list of {type, params}) ─────────────
        self.exit_list: list[dict[str, Any]] = config.get("exit", [])
        self._parse_exit_rules()

        # ── Bar history (capped at 500, Bug 5) ─────────────────────────
        self.bars: list[dict[str, float]] = []
        self.max_bars: int = 500
        self.entry_price: float = 0.0
        self.position_qty: float = 0.0
        self._trailing_high: float = 0.0
        self._trailing_low: float = 0.0

    # ── State management ─────────────────────────────────────────────

    def reset_state(self) -> None:
        """Reset cell to initial IDLE state with empty state."""
        self.state = "IDLE"
        self.bars = []
        self.entry_price = 0.0
        self.position_qty = 0.0
        self._trailing_high = 0.0
        self._trailing_low = 0.0

    # ── Exit rule parsing ─────────────────────────────────────────────

    def _parse_exit_rules(self) -> None:
        """Parse the YAML exit list into structured rule attributes.

        Supports two parameter modes:
        - ``atr_multiplier`` (float): exit distance = multiplier × ATR %
        - ``pct`` (float): exit distance = fixed percentage of entry price
        """
        self.exit_stop_loss: float | None = None      # ATR multiplier
        self.exit_stop_loss_pct: float | None = None   # fixed % (0.062 = 6.2%)
        self.exit_take_profit: float | None = None     # ATR multiplier
        self.exit_take_profit_pct: float | None = None # fixed % (0.062 = 6.2%)
        self.exit_trailing_stop: float | None = None   # ATR multiplier
        self.exit_trailing_stop_pct: float | None = None
        self.exit_zscore_threshold: float | None = None

        for rule in self.exit_list:
            rule_type = rule.get("type", "")
            params = rule.get("params", {})
            if rule_type == "stop_loss":
                if "pct" in params:
                    self.exit_stop_loss_pct = float(params["pct"]) / 100.0
                else:
                    self.exit_stop_loss = float(params.get("atr_multiplier", 1.5))
            elif rule_type == "take_profit":
                if "pct" in params:
                    self.exit_take_profit_pct = float(params["pct"]) / 100.0
                else:
                    self.exit_take_profit = float(params.get("atr_multiplier", 3.0))
            elif rule_type == "trailing_stop":
                if "pct" in params:
                    self.exit_trailing_stop_pct = float(params["pct"]) / 100.0
                else:
                    self.exit_trailing_stop = float(params.get("atr_multiplier", 2.0))
            elif rule_type == "zscore":
                self.exit_zscore_threshold = float(params.get("threshold", 0.5))

    # ── Event handling ────────────────────────────────────────────────

    async def handle(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Process a market event and return a trading signal if triggered.

        Args:
            event: Event dict with at least ``symbol``, ``type``, ``price``,
                and an optional ``data`` dict containing OHLCV fields.

        Returns:
            A signal dict (``action``, ``symbol``, ``price``, ``sizing``) or
            None if no action is required.
        """
        if event.get("symbol") != self.symbol:
            return None

        # Accumulate bar data (capped)
        data = event.get("data")
        if data and isinstance(data, dict):
            self.bars.append(data)
            if len(self.bars) > self.max_bars:
                self.bars.pop(0)

        current_price = event.get("price", 0.0)

        if self.state == "IDLE":
            signal = await self._check_entry(current_price)
            if signal is not None:
                return signal
            return await self._check_short_entry(current_price)

        if self.state in ("IN_POSITION", "IN_SHORT"):
            return self._check_exit(current_price)

        return None

    # ── Entry logic ───────────────────────────────────────────────────

    def enter_position(self, price: float, direction: str = "long") -> None:
        """Mark this cell as IN_POSITION or IN_SHORT after risk approval.

        Called by the EventEngine AFTER the RiskManager approves the
        signal, so that cells rejected by risk stay in IDLE state and
        can retry.

        Args:
            price: Entry price.
            direction: ``"long"`` (default) → ``state = "IN_POSITION"``.
                       ``"short"`` → ``state = "IN_SHORT"``.
        """
        self.state = "IN_SHORT" if direction == "short" else "IN_POSITION"
        self.entry_price = price
        self._trailing_high = 0.0
        self._trailing_low = 0.0
        logger.info(
            "{} {} ENTRADA {} @ ${:.2f}",
            self.symbol, self.name, direction, price,
        )

    async def _check_entry(self, current_price: float) -> dict[str, Any] | None:
        """Evaluate entry conditions.

        NOTE: state is NOT changed here.  The EventEngine calls
        ``enter_position()`` AFTER the RiskManager approves the signal,
        so that cells rejected by risk stay IDLE and can retry.

        Args:
            current_price: Current market price.

        Returns:
            A BUY signal dict if entry conditions are met and inference
            engine confirms, or None otherwise.
        """
        if not self.entry_config or not self.inference_engine:
            return None
        if self._entry_graph is None:
            return None

        market_data = self._build_data()
        if not market_data:
            return None

        try:
            should_enter = self._entry_graph.evaluate(market_data)
        except Exception:
            logger.exception("Error evaluando condiciones de entrada para {}", self.name)
            return None

        if not should_enter:
            return None

        # Risk approval is pending — do NOT change state here.
        # Engine will call enter_position() after approval.
        return {
            "action": "BUY",
            "symbol": self.symbol,
            "price": current_price,
            "sizing": self.sizing,       # fraction of capital
            "cell_name": self.name,      # so RiskManager can track per-cell
        }

    async def _check_short_entry(self, current_price: float) -> dict[str, Any] | None:
        """Evaluate short entry conditions.

        Mirrors ``_check_entry()`` but reads ``self._short_entry_graph``
        and returns an ``action="SHORT"`` signal.

        Args:
            current_price: Current market price.

        Returns:
            A SHORT signal dict if short entry conditions are met, or None.
        """
        if not self.short_entry_config or not self.inference_engine:
            return None
        if self._short_entry_graph is None:
            return None

        market_data = self._build_data()
        if not market_data:
            return None

        try:
            should_enter = self._short_entry_graph.evaluate(market_data)
        except Exception:
            logger.exception("Error evaluando condiciones de entrada short para {}", self.name)
            return None

        if not should_enter:
            return None

        return {
            "action": "SHORT",
            "symbol": self.symbol,
            "price": current_price,
            "sizing": self.sizing,
            "cell_name": self.name,
        }

    # ── Exit logic ────────────────────────────────────────────────────

    def _check_exit(self, current_price: float) -> dict[str, Any] | None:
        """Evaluate exit conditions (ATR-based stop-loss, take-profit,
        trailing stop, or z-score).

        Thresholds are inverted when ``self.state == "IN_SHORT"`` so that
        take-profit triggers when the price falls and stop-loss when it
        rises (the mirror of long logic).

        Args:
            current_price: Current market price.

        Returns:
            A signal dict (action="BUY" for short exits, "SELL" for
            long exits) if any condition is met, or None.
        """
        if self.entry_price == 0.0:
            return None

        atr = self._calc_atr()
        if atr is None or atr == 0.0:
            return None

        atr_pct = atr / self.entry_price if self.entry_price > 0 else 0.0
        is_short = self.state == "IN_SHORT"

        # Stop-loss (supports pct and ATR modes)
        if self.exit_stop_loss_pct is not None:
            if is_short:
                stop_price = self.entry_price * (1.0 + self.exit_stop_loss_pct)
                if current_price >= stop_price:
                    logger.info(
                        "{} {} SHORT STOP-LOSS @ ${:.2f} ({:.1f}%, entry ${:.2f})",
                        self.symbol, self.name, current_price,
                        self.exit_stop_loss_pct * 100, self.entry_price,
                    )
                    return self._exit_signal(current_price)
            else:
                stop_price = self.entry_price * (1.0 - self.exit_stop_loss_pct)
                if current_price <= stop_price:
                    logger.info(
                        "{} {} STOP-LOSS @ ${:.2f} ({:.1f}%, entry ${:.2f})",
                        self.symbol, self.name, current_price,
                        self.exit_stop_loss_pct * 100, self.entry_price,
                    )
                    return self._exit_signal(current_price)
        elif self.exit_stop_loss is not None:
            if is_short:
                stop_price = self.entry_price * (1.0 + self.exit_stop_loss * atr_pct)
                if current_price >= stop_price:
                    logger.info(
                        "{} {} SHORT STOP-LOSS @ ${:.2f} (ATR {:.2f}, entry ${:.2f})",
                        self.symbol, self.name, current_price, atr, self.entry_price,
                    )
                    return self._exit_signal(current_price)
            else:
                stop_price = self.entry_price * (1.0 - self.exit_stop_loss * atr_pct)
                if current_price <= stop_price:
                    logger.info(
                        "{} {} STOP-LOSS @ ${:.2f} (ATR {:.2f}, entry ${:.2f})",
                        self.symbol, self.name, current_price, atr, self.entry_price,
                    )
                    return self._exit_signal(current_price)

        # Take-profit (supports pct and ATR modes)
        if self.exit_take_profit_pct is not None:
            if is_short:
                take_price = self.entry_price * (1.0 - self.exit_take_profit_pct)
                if current_price <= take_price:
                    logger.info(
                        "{} {} SHORT TAKE-PROFIT @ ${:.2f} ({:.1f}%, entry ${:.2f})",
                        self.symbol, self.name, current_price,
                        self.exit_take_profit_pct * 100, self.entry_price,
                    )
                    return self._exit_signal(current_price)
            else:
                take_price = self.entry_price * (1.0 + self.exit_take_profit_pct)
                if current_price >= take_price:
                    logger.info(
                        "{} {} TAKE-PROFIT @ ${:.2f} ({:.1f}%, entry ${:.2f})",
                        self.symbol, self.name, current_price,
                        self.exit_take_profit_pct * 100, self.entry_price,
                    )
                    return self._exit_signal(current_price)
        elif self.exit_take_profit is not None:
            if is_short:
                take_price = self.entry_price * (1.0 - self.exit_take_profit * atr_pct)
                if current_price <= take_price:
                    logger.info(
                        "{} {} SHORT TAKE-PROFIT @ ${:.2f} (ATR {:.2f}, entry ${:.2f})",
                        self.symbol, self.name, current_price, atr, self.entry_price,
                    )
                    return self._exit_signal(current_price)
            else:
                take_price = self.entry_price * (1.0 + self.exit_take_profit * atr_pct)
                if current_price >= take_price:
                    logger.info(
                        "{} {} TAKE-PROFIT @ ${:.2f} (ATR {:.2f}, entry ${:.2f})",
                        self.symbol, self.name, current_price, atr, self.entry_price,
                    )
                    return self._exit_signal(current_price)

        # Trailing stop (supports pct and ATR modes) — direction-aware
        if self.exit_trailing_stop_pct is not None:
            trail_distance = self.exit_trailing_stop_pct * self.entry_price
            if is_short:
                if self._trailing_low == 0.0:
                    self._trailing_low = current_price
                self._trailing_low = min(self._trailing_low, current_price)
                if current_price >= self._trailing_low + trail_distance:
                    logger.info(
                        "{} {} SHORT TRAILING-STOP @ ${:.2f} ({:.1f}%, low ${:.2f})",
                        self.symbol, self.name, current_price,
                        self.exit_trailing_stop_pct * 100, self._trailing_low,
                    )
                    self._trailing_low = 0.0
                    return self._exit_signal(current_price)
            else:
                if self._trailing_high == 0.0:
                    self._trailing_high = current_price
                self._trailing_high = max(self._trailing_high, current_price)
                if current_price <= self._trailing_high - trail_distance:
                    logger.info(
                        "{} {} TRAILING-STOP @ ${:.2f} ({:.1f}%, high ${:.2f})",
                        self.symbol, self.name, current_price,
                        self.exit_trailing_stop_pct * 100, self._trailing_high,
                    )
                    self._trailing_high = 0.0
                    return self._exit_signal(current_price)
        elif self.exit_trailing_stop is not None:
            trail_distance = self.exit_trailing_stop * atr
            if is_short:
                if self._trailing_low == 0.0:
                    self._trailing_low = current_price
                self._trailing_low = min(self._trailing_low, current_price)
                if current_price >= self._trailing_low + trail_distance:
                    logger.info(
                        "{} {} SHORT TRAILING-STOP @ ${:.2f} (ATR {:.2f}, low ${:.2f})",
                        self.symbol, self.name, current_price, atr, self._trailing_low,
                    )
                    self._trailing_low = 0.0
                    return self._exit_signal(current_price)
            else:
                if self._trailing_high == 0.0:
                    self._trailing_high = current_price
                self._trailing_high = max(self._trailing_high, current_price)
                if current_price <= self._trailing_high - trail_distance:
                    logger.info(
                        "{} {} TRAILING-STOP @ ${:.2f} (ATR {:.2f}, high ${:.2f})",
                        self.symbol, self.name, current_price, atr, self._trailing_high,
                    )
                    self._trailing_high = 0.0
                    return self._exit_signal(current_price)

        # Z-score exit (reversion to mean) — direction-neutral
        if self.exit_zscore_threshold is not None:
            market_data = self._build_data()
            if market_data:
                from royaltdn.inference.conditions import evaluate
                try:
                    should_exit = evaluate(
                        "zscore", {"period": 20}, "> {}", market_data
                    )
                    if isinstance(should_exit, (int, float)):
                        if abs(should_exit) < self.exit_zscore_threshold:
                            return self._exit_signal(current_price)
                except Exception:
                    pass

        return None

    def _exit_signal(self, current_price: float) -> dict[str, Any]:
        """Generate an exit signal WITHOUT resetting cell state.

        Returns ``action="BUY"`` when the cell is in ``IN_SHORT``
        (buy-to-cover) and ``action="SELL"`` otherwise (long exit).

        State is reset by the engine via ``exit_position()`` AFTER
        the RiskManager approves AND the broker executes the trade,
        mirroring how ``enter_position()`` works for entry signals.

        Args:
            current_price: Current market price.

        Returns:
            Signal dict with action, symbol, price, sizing,
            entry_price, and cell_name.
        """
        action = "BUY" if self.state == "IN_SHORT" else "SELL"
        return {
            "action": action,
            "symbol": self.symbol,
            "price": current_price,
            "sizing": self.sizing,
            "entry_price": self.entry_price,
            "cell_name": self.name,
        }

    def exit_position(self) -> None:
        """Mark this cell as IDLE after a successful exit.

        Called by the EventEngine AFTER the RiskManager approves and
        the broker executes the exit trade.  This is the mirror of
        ``enter_position()`` — state changes only after confirmation.
        """
        self.state = "IDLE"
        self.entry_price = 0.0
        self._trailing_high = 0.0
        self._trailing_low = 0.0

    # ── Data helpers ──────────────────────────────────────────────────

    def _build_data(self) -> dict[str, list[float]]:
        """Build a market-data dict from accumulated bars.

        Returns:
            Dict with ``close``, ``volume``, ``high``, ``low`` lists.
            Returns empty dict if fewer than 20 bars (insufficient data).
        """
        if len(self.bars) < 20:
            return {}
        return {
            "close": [b.get("close", 0.0) for b in self.bars],
            "volume": [b.get("volume", 0.0) for b in self.bars],
            "high": [b.get("high", 0.0) for b in self.bars],
            "low": [b.get("low", 0.0) for b in self.bars],
        }

    def _calc_atr(self, period: int = 14) -> float | None:
        """Calculate ATR over accumulated bars.

        Args:
            period: lookback window.

        Returns:
            ATR value, or None if insufficient data.
        """
        if len(self.bars) < period + 1:
            return None
        try:
            closes = [b.get("close", 0.0) for b in self.bars]
            highs = [b.get("high", 0.0) for b in self.bars]
            lows = [b.get("low", 0.0) for b in self.bars]

            tr_sum = 0.0
            for i in range(-period, 0):
                high = highs[i]
                low = lows[i]
                prev_close = closes[i - 1]
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                tr_sum += tr
            return tr_sum / period
        except (IndexError, TypeError, ZeroDivisionError):
            return None
