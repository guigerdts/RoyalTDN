"""Tests for the Textual TUI screens and IPC actions.

Uses ``asyncio.run()`` wrapper pattern because ``pytest-asyncio`` /
``pytest-textual`` are not installed.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from textual.pilot import Pilot
from textual.widgets import Button


# ── async test helper ──────────────────────────────────────────────────


def _run_async(coro):
    """Helper to run async test code in a sync pytest function."""
    return asyncio.run(coro)


# ── Dashboard mount test ───────────────────────────────────────────────


class TestDashboard:
    def test_dashboard_mounts_empty(self):
        """Dashboard renders KPIs without errors on empty state."""

        async def _test():
            from royaltdn.frontend.textual import RoyalTDNApp

            async with RoyalTDNApp().run_test() as pilot:
                app = pilot.app
                # Dashboard should be visible by default
                dashboard = app.query_one("#dashboard")
                assert dashboard is not None
                assert dashboard.display is True

                # KPIs should render without error
                kpi_grid = app.query_one("#kpi-grid")
                assert kpi_grid is not None

                # Positions table should exist
                positions = app.query_one("#positions-table")
                assert positions is not None

        _run_async(_test())


# ── Screen navigation tests ────────────────────────────────────────────


class TestScreenNavigation:
    def test_screen_navigation(self):
        """Pressing keys 1-6 and h switches to the correct screen."""

        async def _test():
            from royaltdn.frontend.textual import RoyalTDNApp

            async with RoyalTDNApp().run_test() as pilot:
                app = pilot.app
                screen_map = app._screen_map

                # Key bindings to test and expected screen IDs
                tests = [
                    ("1", "dashboard"),
                    ("2", "scanner"),
                    ("3", "estrategias"),
                    ("4", "trades"),
                    ("5", "logs"),
                    ("6", "builder"),
                    ("h", "help"),
                ]

                for key, expected_id in tests:
                    await pilot.press(key)
                    # Only the expected screen should be visible
                    for sid, child in screen_map.items():
                        if sid == expected_id:
                            assert child.display is True, (
                                f"Screen {expected_id} should be visible after key '{key}'"
                            )
                        else:
                            assert child.display is False, (
                                f"Screen {sid} should be hidden after key '{key}'"
                            )

        _run_async(_test())


# ── IPC action tests ───────────────────────────────────────────────────


class TestIPCActions:
    def test_ipc_actions(self, mocker):
        """Pressing p, r, s triggers the corresponding IPC commands."""

        mock_pause = mocker.patch("royaltdn.frontend.console.commands.pause_bot")
        mock_resume = mocker.patch("royaltdn.frontend.console.commands.resume_bot")
        mock_scanner = mocker.patch("royaltdn.frontend.console.commands.trigger_scanner")

        async def _test():
            from royaltdn.frontend.textual import RoyalTDNApp

            async with RoyalTDNApp().run_test() as pilot:
                # Press 'p' to pause
                await pilot.press("p")
                mock_pause.assert_called_once()

                # Press 'r' to resume
                await pilot.press("r")
                mock_resume.assert_called_once()

                # Press 's' to trigger scanner
                await pilot.press("s")
                mock_scanner.assert_called_once()

        _run_async(_test())


# ── Builder indicator test ──────────────────────────────────────────────


class TestBuilderAddIndicator:
    def test_builder_add_indicator(self):
        """Navigate to builder and add an indicator."""

        async def _test():
            from royaltdn.frontend.textual import RoyalTDNApp

            async with RoyalTDNApp().run_test() as pilot:
                app = pilot.app

                # Navigate to builder (key "6")
                await pilot.press("6")
                builder = app.query_one("#builder")
                assert builder.display is True

                # Find the indicators tab content
                # The Select widget for indicator selection should exist
                indicator_select = builder.query_one("#indicator-select")
                assert indicator_select is not None

                # Select the first real indicator option (SMA)
                # Select widgets accept value via pilot
                indicator_select.value = "SMA"
                # Click "Agregar indicador" button
                add_button = builder.query_one("#add-indicator", Button)
                assert add_button is not None

                # Focus the button and press enter to click
                add_button.focus()
                await pilot.press("enter")

                # The indicator should appear in selected_indicators state
                assert any(
                    ind.get("id") == "SMA" or ind.get("name", "").upper() == "SMA"
                    for ind in builder.selected_indicators
                ), "SMA should be in selected indicators after adding"

        _run_async(_test())


# ── Help screen test ────────────────────────────────────────────────────


class TestHelpScreen:
    def test_help_screen_renders(self):
        """Navigate to help screen and verify it contains key binding text."""

        async def _test():
            from royaltdn.frontend.textual import RoyalTDNApp

            async with RoyalTDNApp().run_test() as pilot:
                app = pilot.app

                # Navigate to help (key "h")
                await pilot.press("h")
                help_screen = app.query_one("#help")
                assert help_screen is not None
                assert help_screen.display is True

                # Verify the help content contains key binding descriptions
                help_content = app.query_one("#help-content")
                assert help_content is not None
                rendered = str(help_content.renderable or "")
                assert "Ayuda" in rendered
                assert "Dashboard" in rendered
                assert "Scanner" in rendered
                assert "Salir" in rendered

        _run_async(_test())


# ── Quit test ──────────────────────────────────────────────────────────


class TestQuit:
    def test_quit(self):
        """Pressing 'q' exits the app cleanly."""

        async def _test():
            from royaltdn.frontend.textual import RoyalTDNApp

            async with RoyalTDNApp().run_test() as pilot:
                await pilot.press("q")
                # After pressing q, the app should have exited
                assert pilot.app.is_running is False

        _run_async(_test())
