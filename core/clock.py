"""Clock abstraction for the CellMesh architecture.

Supports both real-time execution (via RealClock) and simulated
time for backtesting (via SimClock).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


class RealClock:
    """Wall-clock time provider.

    Uses UTC for all timestamps. Suitable for production live trading.
    """

    @staticmethod
    def now() -> datetime:
        """Return the current UTC datetime.

        Returns:
            Current UTC timestamp.
        """
        return datetime.now(timezone.utc)

    @staticmethod
    async def sleep(seconds: float) -> None:
        """Sleep for *seconds* of real wall-clock time.

        Args:
            seconds: Number of seconds to sleep.
        """
        await asyncio.sleep(seconds)


class SimClock:
    """Simulated clock for backtesting.

    Advances time at a configurable speed ratio relative to real time.
    Useful for replaying historical data faster or slower than real-time.
    """

    def __init__(self, start_time: datetime, speed: float = 1.0) -> None:
        """Initialise the simulated clock.

        Args:
            start_time: The initial simulation timestamp.
            speed: Simulation speed multiplier.
                1.0 = real-time, 2.0 = twice as fast, 0.5 = half speed.
        """
        self._current: datetime = start_time
        self._speed: float = speed

    def now(self) -> datetime:
        """Return the current simulated timestamp.

        Returns:
            The internal simulated clock value.
        """
        return self._current

    async def sleep(self, seconds: float) -> None:
        """Sleep for *seconds* of simulated time, adjusted by speed.

        Real wall-clock sleep duration is ``seconds / speed``.

        Args:
            seconds: Number of simulated seconds to wait.
        """
        await asyncio.sleep(seconds / self._speed)

    def advance(self, delta: timedelta) -> None:
        """Advance the simulated clock by the given delta.

        Args:
            delta: The timedelta to add to the current time.
        """
        self._current += delta
