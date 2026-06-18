"""Loguru configuration — centralized logging setup for RoyalTDN.

Provides ``setup_logging()`` that configures Loguru with three sinks:
file (rotation + retention), stderr (colorized), and an optional
LogBuffer sink for the console UI.
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# ── Format strings ──────────────────────────────────────────────────────────

FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss,SSS} | {level: <8} | "
    "{name}:{function}:{line} | {message}"
)

CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>"
)


# ── Setup ───────────────────────────────────────────────────────────────────


def setup_logging(log_buffer: Optional[object] = None) -> None:
    """Configure Loguru with file, stderr, and optional console buffer sinks.

    Removes the default Loguru handler, then adds:

    1. **File sink** — ``logs/bot.log``, rotation 10 MB, retention 7 days,
       level INFO, with structured file format.
    2. **Stderr sink** — colorized output at DEBUG level with console format.
    3. **LogBuffer sink** — if *log_buffer* is provided, its ``.add()`` method
       is registered as a Loguru sink at DEBUG level (for the console UI).

    Args:
        log_buffer: An optional object with an ``.add(record: str)`` method
            (e.g., ``LogBuffer`` instance).
    """
    logger.remove()  # Remove default handler

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # File sink — rotation + retention
    logger.add(
        str(log_dir / "bot.log"),
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format=FILE_FORMAT,
        encoding="utf-8",
    )

    # Console sink (stderr with colors)
    logger.add(
        sys.stderr,
        colorize=True,
        level="DEBUG",
        format=CONSOLE_FORMAT,
    )

    # Optional: LogBuffer sink for console UI
    if log_buffer is not None:
        logger.add(log_buffer.add, level="DEBUG")
