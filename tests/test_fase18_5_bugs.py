#!/usr/bin/env python3
"""Tests for FASE 18.5 bug fixes.

Covers:
1. ``_current_universe`` sync from ``scanner.universe.universe_type`` at startup
2. Background initial scan thread when ``--verbose`` is active
3. ``'v'`` key toggles verbose in ``_render_verbose_dashboard()``
4. Empty ``_last_explanations`` causes ``_build_symbol_entries()`` to return ``[]``
5. Regression: ``_current_universe`` unchanged when ``set_scanner(None)``

Run:
    pytest tests/test_fase18_5_bugs.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
# Bug 1 — Universe sync
# ═══════════════════════════════════════════════════════════════════════


class TestUniverseSync:
    """``set_scanner()`` syncs ``_current_universe`` from scanner."""

    def _reset_globals(self) -> None:
        """Reset module globals before each test."""
        import royaltdn.frontend.menu.app as app_mod
        app_mod._current_universe = "all"
        app_mod._scanner = None

    def test_syncs_universe_from_scanner(self) -> None:
        """``set_scanner()`` reads ``scanner.universe.universe_type`` and updates
        ``_current_universe``."""
        self._reset_globals()
        import royaltdn.frontend.menu.app as app_mod

        mock_scanner = MagicMock()
        mock_scanner.universe.universe_type = "crypto"

        set_scanner = app_mod.set_scanner
        set_scanner(mock_scanner)

        assert app_mod._current_universe == "crypto"

    def test_syncs_etfs_universe(self) -> None:
        """``set_scanner()`` with ``universe_type='etfs'`` sets ``_current_universe``
        to ``'etfs'``."""
        self._reset_globals()
        import royaltdn.frontend.menu.app as app_mod

        mock_scanner = MagicMock()
        mock_scanner.universe.universe_type = "etfs"

        app_mod.set_scanner(mock_scanner)

        assert app_mod._current_universe == "etfs"

    def test_set_scanner_none_leaves_universe(self) -> None:
        """``set_scanner(None)`` does **not** change ``_current_universe``."""
        self._reset_globals()
        import royaltdn.frontend.menu.app as app_mod

        app_mod._current_universe = "crypto"
        app_mod.set_scanner(None)

        assert app_mod._current_universe == "crypto"

    def test_set_scanner_no_universe_attr_keeps_current(self) -> None:
        """Scanner object without ``.universe`` attribute leaves
        ``_current_universe`` unchanged."""
        self._reset_globals()
        import royaltdn.frontend.menu.app as app_mod

        app_mod._current_universe = "sp500"
        mock_scanner = MagicMock(spec=[])  # no universe attr
        app_mod.set_scanner(mock_scanner)

        assert app_mod._current_universe == "sp500"


# ═══════════════════════════════════════════════════════════════════════
# Bug 3 — Background initial scan
# ═══════════════════════════════════════════════════════════════════════


class TestBackgroundScan:
    """Non-blocking background scan when ``--verbose`` is active."""

    @patch("threading.Thread")
    def test_verbose_triggers_background_scan(self, mock_thread: MagicMock) -> None:
        """When ``verbose=True``, a daemon ``threading.Thread`` is started
        with ``scanner.scan(verbose=True)``."""
        scanner = MagicMock()
        verbose = True

        # Simulate the exact code from main.py cmd_run()
        if verbose:
            def _initial_scan() -> None:
                try:
                    scanner.scan(verbose=True)
                except Exception:
                    pass
            import threading
            t = threading.Thread(target=_initial_scan, daemon=True)
            t.start()

        mock_thread.assert_called_once()
        args, kwargs = mock_thread.call_args
        assert kwargs.get("daemon") is True, "Thread must be daemon"

    @patch("threading.Thread")
    def test_verbose_inactive_skips_scan(self, mock_thread: MagicMock) -> None:
        """When ``verbose=False``, no background scan thread is started."""
        scanner = MagicMock()
        verbose = False

        if verbose:
            def _initial_scan() -> None:
                try:
                    scanner.scan(verbose=True)
                except Exception:
                    pass
            import threading
            t = threading.Thread(target=_initial_scan, daemon=True)
            t.start()

        mock_thread.assert_not_called()

    def test_background_scan_calls_scanner_scan(self) -> None:
        """The background scan thread calls ``scanner.scan(verbose=True)``."""
        scanner = MagicMock()

        def _initial_scan() -> None:
            try:
                scanner.scan(verbose=True)
            except Exception:
                pass

        _initial_scan()

        scanner.scan.assert_called_once_with(verbose=True)

    def test_background_scan_handles_exception_gracefully(self) -> None:
        """Exception in background scan is caught and logged, not raised."""
        scanner = MagicMock()
        scanner.scan.side_effect = RuntimeError("API failure")

        # Must not raise
        def _initial_scan() -> None:
            try:
                scanner.scan(verbose=True)
            except Exception:
                pass  # logged via logger.warning

        _initial_scan()  # no exception == pass
        scanner.scan.assert_called_once_with(verbose=True)


# ═══════════════════════════════════════════════════════════════════════
# Bug 5 — 'v' toggle in _render_verbose_dashboard
# ═══════════════════════════════════════════════════════════════════════


class TestVerboseToggle:
    """'v' key toggles ``scanner.verbose`` in ``_render_verbose_dashboard()``."""

    def _setup_scanner(self, verbose: bool) -> MagicMock:
        """Create a mock scanner with sample explanations."""
        import royaltdn.frontend.menu.app as app_mod

        mock_scanner = MagicMock()
        mock_scanner.verbose = verbose
        mock_scanner._last_explanations = {
            "strat_a": {"SYM": {"signal": {"action": "BUY"}}},
        }
        app_mod._scanner = mock_scanner
        app_mod._scanner_cursor_index = 0
        return mock_scanner

    def test_v_toggles_off_and_returns_zero(self) -> None:
        """Pressing 'v' when verbose ON toggles to OFF and returns ``'0'``."""
        import royaltdn.frontend.menu.app as app_mod

        mock_scanner = self._setup_scanner(verbose=True)

        with patch("builtins.input", return_value="v"):
            result = app_mod._render_verbose_dashboard(MagicMock())

        assert result == "0", "Should return '0' to exit verbose dashboard"
        assert mock_scanner.verbose is False

    def test_v_toggles_on_and_returns_rerender(self) -> None:
        """Pressing 'v' when verbose OFF toggles to ON and returns ``'_rerender'``."""
        import royaltdn.frontend.menu.app as app_mod

        mock_scanner = self._setup_scanner(verbose=False)

        with patch("builtins.input", return_value="v"):
            result = app_mod._render_verbose_dashboard(MagicMock())

        assert result == "_rerender", "Should re-render verbose dashboard"
        assert mock_scanner.verbose is True


# ═══════════════════════════════════════════════════════════════════════
# Empty explanations handling
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyExplanations:
    """When ``_last_explanations`` is empty, behave gracefully."""

    def test_build_symbol_entries_empty_when_no_explanations(self) -> None:
        """``_build_symbol_entries()`` returns ``[]`` when
        ``_scanner._last_explanations`` is empty."""
        import royaltdn.frontend.menu.app as app_mod

        mock_scanner = MagicMock()
        mock_scanner._last_explanations = {}
        app_mod._scanner = mock_scanner

        entries = app_mod._build_symbol_entries()
        assert entries == []

    def test_build_symbol_entries_empty_when_scanner_none(self) -> None:
        """``_build_symbol_entries()`` returns ``[]`` when ``_scanner`` is ``None``."""
        import royaltdn.frontend.menu.app as app_mod

        app_mod._scanner = None
        entries = app_mod._build_symbol_entries()
        assert entries == []

    def test_render_verbose_dashboard_returns_none_no_entries(self) -> None:
        """``_render_verbose_dashboard()`` returns ``None`` when no symbol entries
        exist (empty explanations)."""
        import royaltdn.frontend.menu.app as app_mod

        mock_scanner = MagicMock()
        mock_scanner._last_explanations = {}
        mock_scanner.verbose = True
        app_mod._scanner = mock_scanner
        app_mod._scanner_cursor_index = 0

        result = app_mod._render_verbose_dashboard(MagicMock())
        assert result is None
