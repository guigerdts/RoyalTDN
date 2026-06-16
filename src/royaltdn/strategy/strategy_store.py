"""StrategyStore — CRUD for user strategy JSON configs.

Atomic writes (tempfile + os.replace), timestamped filenames,
and a flat file store in a configurable directory.
"""

import glob
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Optional


class StrategyStore:
    """Persistent store for user-defined strategy JSON configs."""

    FILE_PATTERN = re.compile(r"^(.+)_(\d{8}_\d{6}_\d{3})\.json$")
    NAME_CLEAN = re.compile(r"[^a-z0-9_\-]")

    def __init__(self, store_dir: str = "user_strategies"):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────

    def save(self, config: dict) -> str:
        """Save a strategy config atomically.

        Args:
            config: Strategy JSON dict (must have a "name" key).

        Returns:
            The saved file path.

        Raises:
            ValueError: if config has no "name" or is not a dict.
        """
        if not isinstance(config, dict):
            raise ValueError("config must be a dict")
        if "name" not in config:
            raise ValueError("config must have a 'name' key")

        name = self._sanitize_name(config["name"])
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]  # YYYYMMDD_HHMMSS_mmm
        filename = f"{name}_{ts}.json"
        path = os.path.join(self.store_dir, filename)

        # Atomic write via tempfile + os.replace
        fd, tmp_path = tempfile.mkstemp(
            dir=self.store_dir, suffix=".tmp", prefix=f".{filename}."
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except BaseException:
            # Cleanup temp file on any error
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return os.path.abspath(path)

    def load(self, name: str) -> Optional[dict]:
        """Load the most recent version of a strategy by name.

        Args:
            name: Strategy name (case-insensitive, sanitized).

        Returns:
            Parsed JSON dict, or None if no versions exist.
        """
        versions = self._find_versions(name)
        if not versions:
            return None
        latest = versions[-1]  # sorted ascending, take last
        return self._load_file(latest)

    def load_all(self) -> list[dict]:
        """Load the most recent version of every strategy.

        Returns:
            List of parsed JSON dicts.
        """
        result = []
        for name in self.list_names():
            cfg = self.load(name)
            if cfg is not None:
                result.append(cfg)
        return result

    def list_names(self) -> list[str]:
        """List available strategy names (unique, sorted)."""
        names: set[str] = set()
        for fname in self._list_json_files():
            m = self.FILE_PATTERN.match(fname)
            if m:
                names.add(m.group(1))
        return sorted(names)

    def delete(self, name: str) -> bool:
        """Delete all versions of a strategy.

        Args:
            name: Strategy name.

        Returns:
            True if at least one file was deleted, False otherwise.
        """
        versions = self._find_versions(name)
        if not versions:
            return False
        for path in versions:
            os.unlink(path)
        return True

    def get_history(self, name: str) -> list[dict]:
        """Get all versions of a strategy, ordered by timestamp ascending.

        Args:
            name: Strategy name.

        Returns:
            List of dicts with keys: config, file, timestamp.
        """
        versions = self._find_versions(name)
        result = []
        for path in versions:
            cfg = self._load_file(path)
            if cfg is None:
                continue
            fname = os.path.basename(path)
            m = self.FILE_PATTERN.match(fname)
            result.append({
                "config": cfg,
                "file": path,
                "timestamp": m.group(2) if m else "",
            })
        return result

    # ── Internal helpers ────────────────────────────────────────────────

    def _sanitize_name(self, name: str) -> str:
        """Clean a strategy name for use as a filename component."""
        cleaned = name.lower().strip()
        cleaned = self.NAME_CLEAN.sub("_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "unnamed"

    def _list_json_files(self) -> list[str]:
        """List all .json files in the store directory."""
        try:
            return sorted(
                f for f in os.listdir(self.store_dir)
                if f.endswith(".json") and not f.endswith(".tmp")
            )
        except FileNotFoundError:
            return []

    def _find_versions(self, name: str) -> list[str]:
        """Find all version files for a strategy, sorted by timestamp ascending."""
        sanitized = self._sanitize_name(name)
        matches: list[str] = []
        for fname in self._list_json_files():
            m = self.FILE_PATTERN.match(fname)
            if m and m.group(1) == sanitized:
                matches.append(os.path.join(self.store_dir, fname))
        return sorted(matches)

    def _load_file(self, path: str) -> Optional[dict]:
        """Load and parse a JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):
            return None
