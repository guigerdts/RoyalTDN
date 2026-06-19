"""Tests for Fase 8 Rich Interactive Console components."""

import json
import os
import threading
from pathlib import Path

import pytest


# ── StateLoader Tests ──────────────────────────────────────────────────


class TestStateLoader:
    """Test StateLoader with real temp files."""

    @pytest.fixture
    def temp_logs(self):
        """Create temp dir with sample JSON files."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            # status.json
            (logs / "status.json").write_text(json.dumps({
                "bot_status": "ONLINE", "mode": "paper",
                "uptime": 3600, "capital": 10000.0,
                "day_pnl": 150.0, "day_pnl_pct": 1.5,
                "drawdown_pct": -2.5, "win_rate": 65.0,
                "consecutive_losses": 2, "scanner_next": 120,
                "paused": False,
            }))
            # equity.json
            (logs / "equity.json").write_text(json.dumps({
                "equity": [{"value": 10000, "time": "2026-01-01T00:00:00"}],
                "current_equity": 10000,
            }))
            # positions.json
            (logs / "positions.json").write_text(json.dumps({
                "open_positions": [],
                "total_open": 0,
            }))
            # scanner_results.json
            (logs / "scanner_results.json").write_text(json.dumps({
                "last_scan": None,
                "signals": [],
                "scan_history": [],
            }))
            # strategies.json
            (logs / "strategies.json").write_text(json.dumps({
                "predefined": [],
                "user_strategies": {},
            }))
            # trades.json
            (logs / "trades.json").write_text(json.dumps({
                "trades": [],
                "total_trades": 0,
                "profit_factor": 0,
                "best_trade": None,
                "worst_trade": None,
                "sharpe": 0,
            }))
            yield str(logs)

    def test_load_all_returns_dict(self, temp_logs):
        from royaltdn.frontend.console.components.state import StateLoader
        loader = StateLoader(logs_dir=temp_logs)
        result = loader.load_all()
        assert isinstance(result, dict)
        assert "status" in result
        assert "equity" in result
        assert "positions" in result
        assert "scanner" in result
        assert "strategies" in result
        assert "trades" in result

    def test_missing_file_returns_default(self, temp_logs):
        from royaltdn.frontend.console.components.state import StateLoader
        loader = StateLoader(logs_dir=temp_logs)
        # Delete a file
        os.remove(os.path.join(temp_logs, "status.json"))
        result = loader.load_status()
        assert result == {}  # default for dict type

    def test_corrupt_json_returns_default(self, temp_logs):
        from royaltdn.frontend.console.components.state import StateLoader
        loader = StateLoader(logs_dir=temp_logs)
        # Corrupt a file
        with open(os.path.join(temp_logs, "status.json"), "w") as f:
            f.write("{corrupt json!!!")
        result = loader.load_status()
        assert result == {}  # default without crash

    def test_cache_ttl_works(self, temp_logs):
        from royaltdn.frontend.console.components.state import StateLoader
        loader = StateLoader(logs_dir=temp_logs, cache_ttl=60)
        # First call populates cache
        r1 = loader.load_status()
        # Modify file on disk
        with open(os.path.join(temp_logs, "status.json"), "w") as f:
            json.dump({"bot_status": "OFFLINE"}, f)
        # Second call should return cached version (within TTL)
        r2 = loader.load_status()
        assert r2["bot_status"] == "ONLINE"  # cached, not "OFFLINE"


# ── LogBuffer Tests ────────────────────────────────────────────────────


class TestLogBuffer:
    def test_add_and_retrieve(self):
        from royaltdn.frontend.console.log_handler import LogBuffer
        buf = LogBuffer(max_lines=200)
        buf.add("INFO: test message")
        lines = buf.get_lines()
        assert len(lines) == 1
        assert "test message" in lines[0]

    def test_filter_by_level(self):
        from royaltdn.frontend.console.log_handler import LogBuffer
        buf = LogBuffer(max_lines=200)
        buf.add("00:00:00 | INFO    | test | info msg")
        buf.add("00:00:01 | WARNING | test | warn msg")
        buf.add("00:00:02 | ERROR   | test | error msg")
        info_lines = buf.get_lines(level_filter="INFO")
        assert len(info_lines) == 1
        assert "info msg" in info_lines[0]

    def test_filter_by_text(self):
        from royaltdn.frontend.console.log_handler import LogBuffer
        buf = LogBuffer(max_lines=200)
        buf.add("INFO: first")
        buf.add("WARNING: second")
        result = buf.get_lines(text_filter="second")
        assert len(result) == 1

    def test_circular_buffer(self):
        from royaltdn.frontend.console.log_handler import LogBuffer
        buf = LogBuffer(max_lines=10)
        for i in range(20):
            buf.add(f"line {i}")
        lines = buf.get_lines()
        assert len(lines) == 10
        assert lines[0] == "line 10"

    def test_thread_safety(self):
        from royaltdn.frontend.console.log_handler import LogBuffer
        buf = LogBuffer(max_lines=200)
        errors = []

        def writer():
            try:
                for i in range(100):
                    buf.add(f"thread line {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        lines = buf.get_lines()
        assert len(lines) == 200  # max

    def test_get_recent(self):
        from royaltdn.frontend.console.log_handler import LogBuffer
        buf = LogBuffer(max_lines=200)
        for i in range(10):
            buf.add(f"line {i}")
        recent = buf.get_recent(3)
        assert len(recent) == 3
        assert "line 7" in recent[0]


# ── Widget Tests ───────────────────────────────────────────────────────


@pytest.mark.skip(reason="Widgets module deleted in Fase 9 — console/ cleanup")
class TestWidgets:
    def test_create_header_online(self):
        from royaltdn.frontend.console.components.widgets import create_header
        state = {"status": {"bot_status": "ONLINE", "mode": "paper",
                            "uptime": 3600, "scanner_next": 120}}
        result = create_header(state)
        assert "Panel" in type(result).__name__

    def test_create_header_offline(self):
        from royaltdn.frontend.console.components.widgets import create_header
        state = {"status": {"bot_status": "OFFLINE"}}
        result = create_header(state)
        assert "Panel" in type(result).__name__

    def test_create_kpi_cards_positive(self):
        from royaltdn.frontend.console.components.widgets import create_kpi_cards
        state = {"status": {"capital": 10000, "day_pnl": 150, "day_pnl_pct": 1.5,
                            "drawdown_pct": -2.5, "win_rate": 65.0}}
        result = create_kpi_cards(state)
        assert "Table" in type(result).__name__

    def test_create_kpi_cards_negative(self):
        from royaltdn.frontend.console.components.widgets import create_kpi_cards
        state = {"status": {"capital": 8000, "day_pnl": -200, "day_pnl_pct": -2.5,
                            "drawdown_pct": -8.0, "win_rate": 40.0}}
        result = create_kpi_cards(state)
        assert "Table" in type(result).__name__

    def test_empty_positions(self):
        from royaltdn.frontend.console.components.widgets import create_positions_table
        state = {"positions": {"open_positions": [], "total_open": 0}}
        result = create_positions_table(state)
        assert "Table" in type(result).__name__

    def test_empty_signals(self):
        from royaltdn.frontend.console.components.widgets import create_signals_table
        result = create_signals_table([])
        assert "Table" in type(result).__name__

    def test_empty_trades(self):
        from royaltdn.frontend.console.components.widgets import create_trades_table
        result = create_trades_table([])
        assert "Table" in type(result).__name__

    def test_create_footer(self):
        from royaltdn.frontend.console.components.widgets import create_footer
        result = create_footer()
        assert "Panel" in type(result).__name__

    def test_create_empty_state(self):
        from royaltdn.frontend.console.components.widgets import create_empty_state
        result = create_empty_state("No data available")
        assert "Panel" in type(result).__name__


# ── Commands Tests ─────────────────────────────────────────────────────


class TestCommands:
    def test_pause_bot(self, tmp_path):
        from royaltdn.frontend.console.commands import pause_bot
        # Override logs dir via monkeypatching or env
        original_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            pause_bot()
            file = tmp_path / "logs" / "pause_signal.json"
            assert file.exists()
            data = json.loads(file.read_text())
            assert data["action"] == "pause"
            assert "timestamp" in data
        finally:
            os.chdir(original_cwd)

    def test_resume_bot(self, tmp_path):
        from royaltdn.frontend.console.commands import resume_bot
        original_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            resume_bot()
            file = tmp_path / "logs" / "pause_signal.json"
            assert file.exists()
            data = json.loads(file.read_text())
            assert data["action"] == "resume"
        finally:
            os.chdir(original_cwd)

    def test_trigger_scanner(self, tmp_path):
        from royaltdn.frontend.console.commands import trigger_scanner
        original_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            trigger_scanner()
            file = tmp_path / "logs" / "scan_now_signal.json"
            assert file.exists()
            data = json.loads(file.read_text())
            assert data["action"] == "scan_now"
        finally:
            os.chdir(original_cwd)

    def test_get_bot_status_missing(self, tmp_path):
        from royaltdn.frontend.console.commands import get_bot_status
        original_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            result = get_bot_status()
            assert result is None
        finally:
            os.chdir(original_cwd)


# ── HandleCommand Tests ────────────────────────────────────────────────


@pytest.mark.skip(reason="Console app.py module deleted in Fase 9 — Textual TUI migration")
class TestHandleCommand:
    def test_cmd_1_sets_dashboard(self):
        from royaltdn.frontend.console.app import handle_command
        running, screen, lf, mf, tf, sm = handle_command("1", "scanner", None, None, None)
        assert screen == "dashboard"
        assert sm == "📊 Dashboard"

    def test_cmd_dashboard_alias(self):
        from royaltdn.frontend.console.app import handle_command
        running, screen, lf, mf, tf, sm = handle_command("dashboard", "scanner", None, None, None)
        assert screen == "dashboard"

    def test_cmd_scan(self):
        from royaltdn.frontend.console.app import handle_command
        running, screen, lf, mf, tf, sm = handle_command("2", "dashboard", None, None, None)
        assert screen == "scanner"
        assert sm == "🔍 Scanner"

    def test_cmd_q_stops(self):
        from royaltdn.frontend.console.app import handle_command
        running, screen, lf, mf, tf, sm = handle_command("q", "dashboard", None, None, None)
        assert running is False

    def test_cmd_exit_stops(self):
        from royaltdn.frontend.console.app import handle_command
        running, screen, lf, mf, tf, sm = handle_command("exit", "dashboard", None, None, None)
        assert running is False

    def test_cmd_invalid_does_not_crash(self):
        from royaltdn.frontend.console.app import handle_command
        running, screen, lf, mf, tf, sm = handle_command("xyzzy", "dashboard", None, None, None)
        assert running is True
        assert screen == "dashboard"
        assert sm is None  # unknown command → no status message

    def test_pause_resume(self):
        from royaltdn.frontend.console.app import handle_command
        running, screen, lf, mf, tf, sm = handle_command("p", "dashboard", None, None, None)
        assert running is True
        assert sm == "✅ Bot PAUSADO"
        running, screen, lf, mf, tf, sm = handle_command("r", "dashboard", None, None, None)
        assert running is True
        assert sm == "▶️ Bot REANUDADO"
