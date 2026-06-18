"""StateLoader — reads logs/*.json with TTL cache and graceful error handling."""

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger


class StateLoader:
    """Reads bot state from logs/*.json with TTL cache.

    Each ``load_*`` method reads the corresponding JSON file from *logs_dir*
    and returns a parsed dict or list. Missing or corrupt files return an
    appropriate default value instead of crashing.

    Cache is per-file with a configurable TTL (default 1 second).  If the
    file hasn't changed on disk and the cache is still valid, the cached
    value is returned without re-reading the file.
    """

    def __init__(self, logs_dir: str = "logs", cache_ttl: float = 1.0) -> None:
        self._logs_dir = Path(logs_dir)
        self._cache_ttl = cache_ttl
        # {path: (timestamp, data)}
        self._cache: dict[Path, tuple[float, Any]] = {}

    # ── Private helpers ──────────────────────────────────────────────────

    def _load_file(self, filename: str, default: Any = None) -> Any:
        """Read and parse a JSON file with caching and error handling.

        Args:
            filename: Relative file name (e.g. ``"status.json"``).
            default: Value to return if the file is missing or corrupt.

        Returns:
            Parsed JSON data, or *default* on error.
        """
        path = self._logs_dir / filename
        now = time.monotonic()

        # Cache hit?
        if path in self._cache:
            cached_time, cached_value = self._cache[path]
            if (now - cached_time) < self._cache_ttl:
                return cached_value

        # Read file
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._cache[path] = (now, default)
            return default
        except json.JSONDecodeError:
            logger.warning("Corrupt JSON in {}, using default", filename)
            self._cache[path] = (now, default)
            return default

        self._cache[path] = (now, data)
        return data

    # ── Public load methods ──────────────────────────────────────────────

    def load_status(self) -> dict:
        """Load ``logs/status.json``.

        Returns:
            Full status dict, or ``{}`` if missing/corrupt.
        """
        return self._load_file("status.json", {})

    def load_equity(self) -> dict:
        """Load ``logs/equity.json``.

        The ``equity_curve`` key is trimmed to the last 100 points.

        Returns:
            Full equity dict, or ``{}`` if missing/corrupt.
        """
        data = self._load_file("equity.json", {})
        if "equity_curve" in data and isinstance(data["equity_curve"], list):
            data["equity_curve"] = data["equity_curve"][-100:]
        return data

    def load_positions(self) -> dict:
        """Load ``logs/positions.json``.

        Returns:
            Full positions dict, or ``{}`` if missing/corrupt.
        """
        return self._load_file("positions.json", {})

    def load_scanner_results(self) -> dict:
        """Load ``logs/scanner_results.json``.

        Returns:
            Full scanner-result dict, or a safe empty structure if
            missing/corrupt.
        """
        return self._load_file(
            "scanner_results.json",
            {"last_scan": {}, "scan_history": [], "updated_at": None},
        )

    def load_strategies(self) -> dict:
        """Load ``logs/strategies.json``.

        Returns:
            Full strategies dict, or ``{}`` if missing/corrupt.
        """
        return self._load_file("strategies.json", {})

    def load_trades(self) -> dict:
        """Load ``logs/trades.json``.

        The ``trades`` key is trimmed to the last 50 entries.

        Returns:
            Full trades dict, or ``{}`` if missing/corrupt.
        """
        data = self._load_file("trades.json", {})
        if "trades" in data and isinstance(data["trades"], list):
            data["trades"] = data["trades"][-50:]
        return data

    def load_all(self) -> dict:
        """Load all state files in one call.

        Returns:
            A dict with keys ``status``, ``equity``, ``positions``,
            ``scanner``, ``strategies``, ``trades``.
        """
        return {
            "status": self.load_status(),
            "equity": self.load_equity(),
            "positions": self.load_positions(),
            "scanner": self.load_scanner_results(),
            "strategies": self.load_strategies(),
            "trades": self.load_trades(),
        }
