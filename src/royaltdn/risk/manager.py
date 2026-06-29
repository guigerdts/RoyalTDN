"""Risk manager for the CellMesh architecture.

Evaluates trading signals against portfolio constraints and market
conditions before allowing execution.
"""

from __future__ import annotations

from typing import Any

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
        trade_tracker: Any = None,
        max_per_symbol: int = 3,
    ) -> None:
        """Initialise the risk manager.

        Args:
            portfolio: Portfolio instance for state queries.
            max_positions: Maximum number of concurrent long positions.
            max_drawdown: Maximum allowed drawdown fraction (0.03 = 3%).
            config_path: Path to ``config.yaml``. When set, ``max_positions``
                is re-read from the file periodically so that live changes
                take effect without restarting the bot.
            trade_tracker: Optional TradeTracker for per-cell performance
                metrics. When provided and ``max_positions`` is reached,
                cells with higher win rate can evict lower-performing ones.
            max_per_symbol: Maximum concurrent positions per symbol across
                all cells (default 3). Prevents a single symbol from hogging
                all slots.
        """
        from pathlib import Path

        self.portfolio = portfolio
        self.max_positions = max_positions
        self.max_drawdown = max_drawdown
        self._config_path: Path | None = Path(config_path) if config_path else None
        self._last_config_reload: float = 0.0
        self._config_reload_interval: float = 60.0  # seconds
        self._trade_tracker = trade_tracker
        self.max_per_symbol = max_per_symbol

        # Track active entries by (symbol, cell_name, direction) — 3-tuples.
        # Direction is "long" or "short" (lowercase). SHORT and BUY entries
        # share the same position limit pool (max_positions).
        self._active_entries: set[tuple[str, str, str]] = set()

        # Track position qty per cell so that each cell sells only its
        # own portion when multiple cells share the same symbol.
        # Key: (symbol, cell_name, direction) -> qty assigned at entry time.
        self._entry_qty: dict[tuple[str, str, str], float] = {}

    def _positions_for_symbol(self, symbol: str, direction: str | None = None) -> list[tuple[str, str, str]]:
        """Return active entries for *symbol*, optionally filtered by direction."""
        return [
            e for e in self._active_entries
            if e[0] == symbol and (direction is None or e[2] == direction)
        ]

    def _find_worst_cell(self) -> tuple[str, str, str] | None:
        """Find the active entry with the lowest win rate for eviction.

        Returns the entry tuple ``(symbol, cell_name, direction)`` of the
        worst-performing cell, or ``None`` if no performance data exists.
        """
        if self._trade_tracker is None:
            return None
        stats = self._trade_tracker.per_cell_stats()

        best_evict: tuple[str, str, str] | None = None
        worst_win_rate = float("inf")  # lower is worse → we look for minimum

        for entry in self._active_entries:
            _sym, cell_name, _dir = entry
            cell_stats = stats.get(cell_name, {})
            wr = cell_stats.get("win_rate", 0.5)  # default 0.5 if no trades
            if wr < worst_win_rate:
                worst_win_rate = wr
                best_evict = entry

        return best_evict

    def _try_evict(
        self,
        incoming_cell: str,
        symbol: str,
        qty: float,
        signal: dict[str, Any],
        direction: str = "long",
    ) -> dict[str, Any] | None:
        """Try to evict the worst-performing cell to make room for *incoming_cell*.

        Returns an approved signal dict with an ``"evicted"`` field when
        eviction succeeds, or ``None`` when the incoming cell does not
        outperform the worst active cell.
        """
        if self._trade_tracker is None:
            return None

        stats = self._trade_tracker.per_cell_stats()
        incoming_wr = stats.get(incoming_cell, {}).get("win_rate", 0.5)

        # Find the worst active cell among cells WITH at least one trade
        worst_entry: tuple[str, str, str] | None = None
        worst_wr = float("inf")

        for entry in self._active_entries:
            _sym, _cell, _dir = entry
            wr = stats.get(_cell, {}).get("win_rate", None)
            if wr is not None and wr < worst_wr:
                worst_wr = wr
                worst_entry = entry

        # If no active cells have trade data yet, don't evict
        if worst_entry is None:
            return None

        # Only evict if incoming cell is performing better
        if incoming_wr <= worst_wr:
            return None

        # ── Evict the worst cell ──────────────────────────────────────
        evict_sym, evict_cell, evict_dir = worst_entry
        evict_qty = self._entry_qty.pop(worst_entry, 0.0)
        self._active_entries.discard(worst_entry)

        logger.info(
            "RISK EVICT: {} cell={} (win_rate={:.1%}) -> {} cell={} (win_rate={:.1%})",
            evict_cell, evict_sym, worst_wr,
            incoming_cell, symbol, incoming_wr,
        )

        # Register incoming entry
        self._active_entries.add((symbol, incoming_cell, direction))
        self._entry_qty[(symbol, incoming_cell, direction)] = qty

        return {
            "approved": True,
            **signal,
            "qty": qty,
            "evicted": {
                "symbol": evict_sym,
                "cell_name": evict_cell,
                "direction": evict_dir,
                "qty": evict_qty,
            },
        }

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
            return {"approved": False, "reason": "null_signal",
                    "detail": "Señal nula recibida"}

        # Re-read max_positions from config.yaml periodically
        self._reload_config_if_needed()

        action = signal.get("action", "")
        symbol = signal.get("symbol", "")
        cell_name: str = signal.get("cell_name", symbol)  # fallback to symbol
        price = float(signal.get("price", 0))
        sizing = float(signal.get("sizing", 0.01))

        # ── BUY entry (long) or BUY-to-close (short) ────────────────────
        if action == "BUY":
            # Check if this is a BUY-to-close for an existing SHORT
            short_key = (symbol, cell_name, "short")
            if short_key in self._active_entries:
                qty = self._entry_qty.pop(short_key, None)
                self._active_entries.discard(short_key)
                if qty is None or qty <= 0:
                    return {"approved": False, "reason": "no_position",
                            "detail": f"No hay posición short para {symbol} al cubrir (cell={cell_name})"}
                signal["qty"] = qty
                logger.info(
                    "RISK: {} BUY-TO-COVER aprobada — qty={} cell={}",
                    symbol, qty, cell_name,
                )
                return {"approved": True, **signal}

            # ── Equity + qty calculation (uses total value, not raw cash) ──
            equity = self.portfolio.get_total_value()
            if equity <= 0 or price <= 0:
                logger.warning(
                    "RISK REJECT: invalid equity/price (equity={}, price={}) — {} cell={}",
                    equity, price, symbol, cell_name,
                )
                return {"approved": False, "reason": "invalid_params",
                        "detail": f"Equity o precio inválido: equity={equity}, price={price}"}

            raw_qty = (equity * sizing) / price
            min_qty = (equity * 0.001) / price if price > 0 else 0.0
            qty = max(min_qty, raw_qty)
            signal["qty"] = qty

            # ── Per-symbol position limit ──────────────────────────────
            symbol_positions = len(self._positions_for_symbol(symbol))
            if symbol_positions >= self.max_per_symbol:
                logger.warning(
                    "RISK REJECT: max_per_symbol reached ({}/{}) — {} cell={}",
                    symbol_positions, self.max_per_symbol, symbol, cell_name,
                )
                return {"approved": False, "reason": "max_per_symbol",
                        "detail": f"Límite de {self.max_per_symbol} posiciones por símbolo alcanzado ({symbol}, cell={cell_name})"}

            # ── Position limit with cell performance eviction ──────────
            current_positions = len(self._active_entries)
            logger.info(
                "RiskManager: checking signal — positions={}/{} (symbol={}, cell={})",
                current_positions, self.max_positions, symbol, cell_name,
            )
            if current_positions >= self.max_positions:
                # Try evicting the worst-performing cell's position
                evict = self._try_evict(cell_name, symbol, qty, signal)
                if evict is not None:
                    return evict

                logger.warning(
                    "RISK REJECT: max_positions reached ({}/{}) — {} cell={}",
                    current_positions, self.max_positions, symbol, cell_name,
                )
                return {"approved": False, "reason": "max_positions",
                        "detail": f"Límite de {self.max_positions} posiciones alcanzado ({symbol}, cell={cell_name})"}

            # Drawdown check
            drawdown = self.portfolio.get_drawdown()
            if drawdown >= self.max_drawdown:
                logger.warning(
                    "RISK REJECT: drawdown limit exceeded ({:.2%} >= {:.2%}) — {} cell={}",
                    drawdown, self.max_drawdown, symbol, cell_name,
                )
                return {"approved": False, "reason": "drawdown",
                        "detail": f"Drawdown {drawdown:.2%} supera límite {self.max_drawdown:.2%}"}

            # Register with direction="long"
            self._active_entries.add((symbol, cell_name, "long"))
            self._entry_qty[(symbol, cell_name, "long")] = qty
            logger.info(
                "RISK: {} {} aprobada — qty={:.4f} (equity=${:.2f}, sizing={:.2%}, price=${:.2f}, cell={})",
                action, symbol, qty, equity, sizing, price, cell_name,
            )
            return {"approved": True, **signal}

        # ── SHORT entry ─────────────────────────────────────────────────
        elif action == "SHORT":
            # Equity + qty calculation (uses total portfolio value)
            equity = self.portfolio.get_total_value()
            if capital <= 0 or price <= 0:
                return {"approved": False, "reason": "invalid_params",
                        "detail": f"Capital o precio inválido: capital={capital}, price={price}"}

            raw_qty = (equity * sizing) / price
            min_qty = (equity * 0.001) / price if price > 0 else 0.0
            qty = max(min_qty, raw_qty)
            signal["qty"] = qty

            # Per-symbol position limit (all directions)
            symbol_positions = len(self._positions_for_symbol(symbol))
            if symbol_positions >= self.max_per_symbol:
                logger.warning(
                    "RISK REJECT (SHORT): max_per_symbol reached ({}/{}) — {} cell={}",
                    symbol_positions, self.max_per_symbol, symbol, cell_name,
                )
                return {"approved": False, "reason": "max_per_symbol",
                        "detail": f"Límite de {self.max_per_symbol} posiciones short por símbolo ({symbol}, cell={cell_name})"}

            # Position limit with eviction
            current_positions = len(self._active_entries)
            if current_positions >= self.max_positions:
                evict = self._try_evict(cell_name, symbol, qty, signal, direction="short")
                if evict is not None:
                    return evict

                logger.warning(
                    "RISK REJECT (SHORT): max_positions reached ({}/{}) — {} cell={}",
                    current_positions, self.max_positions, symbol, cell_name,
                )
                return {"approved": False, "reason": "max_positions",
                        "detail": f"Límite de {self.max_positions} posiciones alcanzado ({symbol}, cell={cell_name})"}

            # Drawdown check
            drawdown = self.portfolio.get_drawdown()
            if drawdown >= self.max_drawdown:
                logger.warning(
                    "RISK REJECT (SHORT): drawdown limit exceeded ({:.2%} >= {:.2%}) — {} cell={}",
                    drawdown, self.max_drawdown, symbol, cell_name,
                )
                return {"approved": False, "reason": "drawdown",
                        "detail": f"Drawdown {drawdown:.2%} supera límite {self.max_drawdown:.2%}"}

            self._active_entries.add((symbol, cell_name, "short"))
            self._entry_qty[(symbol, cell_name, "short")] = qty
            logger.info(
                "RISK: SHORT {} aprobada — qty={:.4f} (equity=${:.2f}, sizing={:.2%}, price=${:.2f}, cell={})",
                symbol, qty, equity, sizing, price, cell_name,
            )
            return {"approved": True, **signal}

        # ── SELL (long exit) ─────────────────────────────────────────────
        elif action == "SELL":
            qty = self._entry_qty.pop((symbol, cell_name, "long"), None)
            if qty is None:
                qty = self.portfolio.positions.get(symbol, 0.0)
            if qty <= 0:
                logger.warning(
                    "RISK REJECT: no position to sell (qty={}) — {} cell={}",
                    qty, symbol, cell_name,
                )
                return {"approved": False, "reason": "no_position",
                        "detail": f"No hay posición abierta para {symbol} al cerrar (cell={cell_name})"}

            self._active_entries.discard((symbol, cell_name, "long"))
            signal["qty"] = qty
            logger.info(
                "RISK: {} SELL aprobada — qty={} cell={}",
                symbol, qty, cell_name,
            )
            return {"approved": True, **signal}

        # ── Unknown action ───────────────────────────────────────────────
        else:
            logger.warning(
                "RISK REJECT: unknown action '{}' — {} cell={}",
                action, symbol, cell_name,
            )
            return {"approved": False, "reason": "unknown_action",
                    "detail": f"Acción desconocida: {action} (symbol={symbol}, cell={cell_name})"}
