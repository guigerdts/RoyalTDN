"""Risk manager for the CellMesh architecture.

Evaluates trading signals against portfolio constraints and market
conditions before allowing execution.
"""

from __future__ import annotations

from loguru import logger


class RiskManager:
    """Trade approval gate.

    Enforces:
    - Maximum number of concurrent positions (tracked per cell+symbol).
    - Maximum drawdown threshold.
    - Calculates position size from capital + sizing fraction.

    Tracks active entries by ``(symbol, cell_name)`` so that different
    strategy cells CAN hold the same symbol simultaneously.  The old
    ``symbol in portfolio.positions`` check was removed — it limited
    positions to the number of unique symbols in ``config.yaml``,
    ignoring ``max_positions``.
    """

    def __init__(
        self,
        portfolio: Any,
        max_positions: int = 5,
        max_drawdown: float = 0.03,
        config_path: str | Path | None = None,
    ) -> None:
        """Initialise the risk manager.

        Args:
            portfolio: Portfolio instance for state queries.
            max_positions: Maximum number of concurrent long positions.
            max_drawdown: Maximum allowed drawdown fraction (0.03 = 3%).
            config_path: Path to ``config.yaml``. When set, ``max_positions``
                is re-read from the file periodically so that live changes
                take effect without restarting the bot.
        """
        from pathlib import Path

        self.portfolio = portfolio
        self.max_positions = max_positions
        self.max_drawdown = max_drawdown
        self._config_path: Path | None = Path(config_path) if config_path else None
        self._last_config_reload: float = 0.0
        self._config_reload_interval: float = 60.0  # seconds

        # Track active entries by (symbol, cell_name) instead of relying
        # on len(portfolio.positions) which only counts unique symbols.
        self._active_entries: set[tuple[str, str]] = set()

        # Track position qty per cell so that each cell sells only its
        # own portion when multiple cells share the same symbol.
        # Key: (symbol, cell_name) -> qty assigned at entry time.
        self._entry_qty: dict[tuple[str, str], float] = {}

    def _reload_config_if_needed(self) -> None:
        """Re-read ``max_positions`` from ``config.yaml`` if enough time has
        passed since the last read."""
        import time

        if self._config_path is None:
            return
        now = time.monotonic()
        if now - self._last_config_reload < self._config_reload_interval:
            return
        self._last_config_reload = now
        try:
            import yaml
            with open(self._config_path) as f:
                cfg = yaml.safe_load(f)
            cfg_max = cfg.get("max_positions")
            if cfg_max is not None and isinstance(cfg_max, (int, float)):
                old = self.max_positions
                self.max_positions = int(cfg_max)
                if old != self.max_positions:
                    logger.info(
                        "RiskManager: max_positions actualizado {} -> {} (desde config.yaml)",
                        old, self.max_positions,
                    )
        except Exception as exc:
            logger.warning("RiskManager: no se pudo releer config.yaml: {}", exc)

    def approve(self, signal: dict[str, Any] | None) -> dict[str, Any] | None:
        """Approve or reject a trading signal.

        For BUY signals: checks position limit, drawdown,
        then calculates actual share qty = (capital * sizing) / price.

        Args:
            signal: Signal dict with ``action``, ``symbol``, ``price``,
                ``sizing`` (fraction of capital). May be None.

        Returns:
            The approved signal dict with ``qty`` added, or None if rejected.
        """
        if signal is None:
            logger.warning("RISK REJECT: signal is None — no se puede aprobar")
            return None

        # Re-read max_positions from config.yaml periodically
        self._reload_config_if_needed()

        action = signal.get("action", "")
        symbol = signal.get("symbol", "")
        cell_name: str = signal.get("cell_name", symbol)  # fallback to symbol
        price = float(signal.get("price", 0))
        sizing = float(signal.get("sizing", 0.01))

        if action == "BUY":
            # Position limit check — counts ACTIVE ENTRIES, not unique symbols.
            # Different cells CAN hold the same symbol simultaneously.
            current_positions = len(self._active_entries)
            logger.info(
                "RiskManager: checking signal — positions={}/{} (symbol={}, cell={})",
                current_positions, self.max_positions, symbol, cell_name,
            )
            if current_positions >= self.max_positions:
                logger.warning(
                    "RISK REJECT: max_positions reached ({}/{}) — {} cell={}",
                    current_positions, self.max_positions, symbol, cell_name,
                )
                return None

            # Drawdown check
            drawdown = self.portfolio.get_drawdown()
            if drawdown >= self.max_drawdown:
                logger.warning(
                    "RISK REJECT: drawdown limit exceeded ({:.2%} >= {:.2%}) — {} cell={}",
                    drawdown, self.max_drawdown, symbol, cell_name,
                )
                return None

            # Calculate qty from capital * sizing / price (Bug 3)
            capital = self.portfolio.capital
            if capital <= 0 or price <= 0:
                logger.warning(
                    "RISK REJECT: invalid capital/price (capital={}, price={}) — {} cell={}",
                    capital, price, symbol, cell_name,
                )
                return None

            raw_qty = (capital * sizing) / price
            # Minimum trade: 0.1% of capital worth of asset (prevents dust)
            min_qty = (capital * 0.001) / price if price > 0 else 0.0
            qty = max(min_qty, raw_qty)
            signal["qty"] = qty

            # Register this entry BEFORE returning so max_positions
            # is enforced correctly on the next check.
            self._active_entries.add((symbol, cell_name))
            # Store per-cell qty so each cell sells only its own portion
            self._entry_qty[(symbol, cell_name)] = qty
            logger.info(
                "RISK: {} {} aprobada — qty={:.4f} (capital=${:.2f}, sizing={:.2%}, price=${:.2f}, cell={})",
                action, symbol, qty, capital, sizing, price, cell_name,
            )

        elif action == "SELL":
            # Use per-cell qty first; fall back to total symbol qty
            # for entries created before this fix was deployed.
            qty = self._entry_qty.pop((symbol, cell_name), None)
            if qty is None:
                qty = self.portfolio.positions.get(symbol, 0.0)
            if qty <= 0:
                logger.warning(
                    "RISK REJECT: no position to sell (qty={}) — {} cell={}",
                    qty, symbol, cell_name,
                )
                # Do NOT discard from _active_entries — the cell stays
                # IN_POSITION and can retry the exit on the next tick.
                return None

            # Only free the slot AFTER confirming there IS a position.
            self._active_entries.discard((symbol, cell_name))
            signal["qty"] = qty
            logger.info(
                "RISK: {} SELL aprobada — qty={} cell={}",
                symbol, qty, cell_name,
            )

        else:
            logger.warning(
                "RISK REJECT: unknown action '{}' — {} cell={}",
                action, symbol, cell_name,
            )
            return None

        return signal
