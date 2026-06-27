"""OHLCV tick replayer for backtesting.

Drives ``SimClock.advance()`` from bar-to-bar deltas and yields the
same tick events that the production pipeline expects.
"""

from __future__ import annotations

from typing import Any, Iterator

from pandas import DataFrame


class Replayer:
    """Iterate an OHLCV DataFrame, advance the clock, yield tick events.

    Each row produces a single ``{"type": "tick", ...}`` event that
    mirrors what a live data feed would emit.  The replayer is a
    synchronous iterator — it does NOT interact with the event bus
    directly; the caller feeds yielded events to the engine.

    Example::

        replayer = Replayer(ohlcv, clock, "BTC/USDT")
        for event in replayer:
            engine.run_batch([event])
    """

    def __init__(self, ohlcv: DataFrame, clock: Any, symbol: str) -> None:
        """Initialise the replayer.

        Args:
            ohlcv: OHLCV DataFrame with at least a ``timestamp`` column
                and ``open``, ``high``, ``low``, ``close``, ``volume``
                columns.  The timestamp column is assumed to be
                parseable by pandas (datetime, Timestamp, or ISO string).
            clock: ``SimClock`` instance whose ``advance(timedelta)``
                method will be called per row.
            symbol: Trading symbol (e.g. ``"BTC/USDT"``) injected into
                every yielded event.
        """
        self._rows = ohlcv.iterrows()
        self._clock = clock
        self._symbol = symbol
        self._prev_ts: Any = None

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Yield a tick event per OHLCV row, advancing the clock."""
        for _, bar in self._rows:
            ts = bar["timestamp"]
            if self._prev_ts is not None:
                self._clock.advance(ts - self._prev_ts)
            self._prev_ts = ts
            yield self._build_event(bar)

    def _build_event(self, bar: Any) -> dict[str, Any]:
        """Build a tick event dict from a single OHLCV row.

        Args:
            bar: A pandas Series representing one OHLCV row.

        Returns:
            Tick event dict with ``type``, ``symbol``, ``price``, and
            ``data`` sub-dict containing OHLCV fields.
        """
        return {
            "type": "tick",
            "symbol": self._symbol,
            "price": float(bar["close"]),
            "data": {
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": float(bar["volume"]),
            },
        }
