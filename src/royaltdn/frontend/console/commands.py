"""IPC commands — write signal files that the Orchestrator polls.

Every function creates a small JSON file under ``logs/`` which the
Orchestrator reads at the top of its loop iteration.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def _ensure_logs_dir(logs_dir: str = "logs") -> Path:
    path = Path(logs_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def pause_bot(logs_dir: str = "logs") -> None:
    """Write ``pause_signal.json`` with ``action: pause``."""
    log_path = _ensure_logs_dir(logs_dir)
    signal = {"action": "pause", "timestamp": _timestamp()}
    (log_path / "pause_signal.json").write_text(
        json.dumps(signal, indent=2), encoding="utf-8"
    )


def resume_bot(logs_dir: str = "logs") -> None:
    """Write ``pause_signal.json`` with ``action: resume``."""
    log_path = _ensure_logs_dir(logs_dir)
    signal = {"action": "resume", "timestamp": _timestamp()}
    (log_path / "pause_signal.json").write_text(
        json.dumps(signal, indent=2), encoding="utf-8"
    )


def trigger_scanner(logs_dir: str = "logs") -> None:
    """Write ``scan_now_signal.json`` with ``action: scan_now``."""
    log_path = _ensure_logs_dir(logs_dir)
    signal = {"action": "scan_now", "timestamp": _timestamp()}
    (log_path / "scan_now_signal.json").write_text(
        json.dumps(signal, indent=2), encoding="utf-8"
    )


def get_bot_status(logs_dir: str = "logs") -> dict | None:
    """Read and return ``logs/status.json``, or ``None`` if missing."""
    path = Path(logs_dir) / "status.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
