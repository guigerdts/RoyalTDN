"""Log buffer for the interactive console — captures Loguru records in a circular buffer."""

from collections import deque
from threading import Lock
from typing import Optional


class LogBuffer:
    """Circular buffer for log lines, accessible from the Rich console UI."""

    def __init__(self, max_lines: int = 200):
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._lock = Lock()

    def add(self, record: str) -> None:
        """Add a formatted log line to the buffer. Thread-safe."""
        with self._lock:
            self._lines.append(record)

    def get_lines(
        self,
        level_filter: Optional[str] = None,
        module_filter: Optional[str] = None,
        text_filter: Optional[str] = None,
        last_n: Optional[int] = None,
    ) -> list[str]:
        """Return filtered log lines.

        Args:
            level_filter: If set, only include lines containing this level (e.g., "INFO").
            module_filter: If set, only include lines containing this module name.
            text_filter: If set, only include lines containing this text (case-insensitive).
            last_n: If set, return only the last N matching lines.

        Returns:
            Filtered list of log lines.
        """
        with self._lock:
            lines = list(self._lines)

        result = lines
        if level_filter:
            result = [l for l in result if f"| {level_filter}" in l]
        if module_filter:
            result = [l for l in result if module_filter.lower() in l.lower()]
        if text_filter:
            result = [l for l in result if text_filter.lower() in l.lower()]
        if last_n is not None:
            result = result[-last_n:]
        return result

    def get_recent(self, n: int = 5) -> list[str]:
        """Return last N unfiltered lines."""
        with self._lock:
            return list(self._lines)[-n:]


def setup_console_log_handler(log_buffer: LogBuffer) -> int:
    """Add *log_buffer* as a Loguru DEBUG-level sink.

    Returns the sink ID (can be used with ``logger.remove()`` later).
    """
    from loguru import logger

    return logger.add(log_buffer.add, level="DEBUG")
