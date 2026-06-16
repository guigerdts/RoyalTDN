"""
RoyalTDN — Frontend Loaders: JSON file readers for bot status files.

Fase 6 — Hito 2: loaders y charts para frontend Streamlit.

All functions return safe defaults (empty dict, empty list) on error.
Never raise exceptions.
"""

import json
import logging
import os
import re
from collections import deque
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("royaltdn.frontend.loaders")

LOGS_DIR = Path("logs")

# ── TTL Cache ─────────────────────────────────────────────────────

_CACHE: dict[str, tuple[float, object]] = {}
CACHE_TTL_SECONDS = 3  # 3 seconds — matches Streamlit's 3s rerun


def _cached(ttl: int = CACHE_TTL_SECONDS):
    """Decorator: caches function return with TTL in seconds.

    Cache key is the function name + str(arguments)."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{kwargs}"
            now = datetime.now(timezone.utc).timestamp()
            if key in _CACHE:
                cached_at, value = _CACHE[key]
                if now - cached_at < ttl:
                    return value
            result = func(*args, **kwargs)
            _CACHE[key] = (now, result)
            return result
        return wrapper
    return decorator


def _clear_cache() -> None:
    """Clear the loader cache (useful for testing)."""
    _CACHE.clear()


# ── Safe JSON loader ─────────────────────────────────────────────

def load_json(path: Path) -> Optional[dict]:
    """Read and parse a JSON file safely.

    Returns:
        dict on success, None on any error (missing, corrupt, permission).
    """
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        logger.warning("Error reading %s: %s", path, e)
        return None


# ── Individual loaders ───────────────────────────────────────────

@_cached(ttl=CACHE_TTL_SECONDS)
def load_status() -> dict:
    """Load status.json. Returns {} on error."""
    data = load_json(LOGS_DIR / "status.json")
    return data if data else {}


@_cached(ttl=CACHE_TTL_SECONDS)
def load_equity() -> dict:
    """Load equity.json. Returns {} on error."""
    data = load_json(LOGS_DIR / "equity.json")
    return data if data else {}


@_cached(ttl=CACHE_TTL_SECONDS)
def load_positions() -> dict:
    """Load positions.json. Returns {} on error."""
    data = load_json(LOGS_DIR / "positions.json")
    return data if data else {}


@_cached(ttl=CACHE_TTL_SECONDS)
def load_signals() -> dict:
    """Load signals.json. Returns {} on error."""
    data = load_json(LOGS_DIR / "signals.json")
    return data if data else {}


@_cached(ttl=CACHE_TTL_SECONDS)
def load_scanner_results() -> dict:
    """Load scanner_results.json. Returns {} on error."""
    data = load_json(LOGS_DIR / "scanner_results.json")
    return data if data else {}


@_cached(ttl=CACHE_TTL_SECONDS)
def load_strategies() -> dict:
    """Load strategies.json. Returns {} on error."""
    data = load_json(LOGS_DIR / "strategies.json")
    return data if data else {}


@_cached(ttl=CACHE_TTL_SECONDS)
def load_trades() -> dict:
    """Load trades.json. Returns {} on error."""
    data = load_json(LOGS_DIR / "trades.json")
    return data if data else {}


# ── Staleness check ─────────────────────────────────────────────

def is_stale(updated_at: str, max_age_seconds: int = 300) -> bool:
    """Check if a timestamp is older than max_age_seconds from now.

    Args:
        updated_at: ISO 8601 timestamp string (may end with Z).
        max_age_seconds: Max allowed age in seconds (default 300 = 5 min).

    Returns:
        True if stale, missing, or unparseable.
    """
    if not updated_at:
        return True
    try:
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        delta = (datetime.now(timezone.utc) - ts).total_seconds()
        return delta > max_age_seconds
    except (ValueError, TypeError):
        return True


# ── Log tail reader ─────────────────────────────────────────────

def read_log_tail(
    filepath: str | Path = "logs/bot.log",
    lines: int = 100,
    level_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
    search_text: Optional[str] = None,
) -> list[str]:
    """Read last N lines from a log file, with optional filtering.

    Args:
        filepath: Path to log file (default: logs/bot.log).
        lines: Max lines to return (default: 100).
        level_filter: If set, only return lines containing this level
                     (e.g. "ERROR", "WARNING"). Case-insensitive.
        module_filter: If set, only return lines containing this module
                      name. Case-insensitive.
        search_text: If set, only return lines containing this text.
                    Case-insensitive.

    Returns:
        List of matching log lines. Empty list on error.
    """
    path = Path(filepath) if isinstance(filepath, str) else filepath
    try:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            line_list = list(deque(f, maxlen=lines * 4))  # read extra for filtering
    except (OSError, PermissionError) as e:
        logger.warning("Error reading log %s: %s", path, e)
        return []

    # Apply filters
    result: list[str] = line_list
    if level_filter:
        result = [l for l in result if level_filter.upper() in l.upper()]
    if module_filter:
        result = [l for l in result if module_filter.lower() in l.lower()]
    if search_text:
        result = [l for l in result if search_text.lower() in l.lower()]

    return result[-lines:]
