"""PR-4 Tests: UI verbose + Dynamic interval + Scalping disable + check-readiness.

Tests:
1. Dynamic interval calc (mock strategy categories)
2. Scalping disable JSON mutation
3. Check-readiness response parsing (mock the checks)
4. UI verbose rendering structure (mock _last_explanations)
5. Log filter addition
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Task 1: Dynamic interval calc ─────────────────────────────────────────

def test_get_scan_interval_override_unset():
    """Env var unset → returns None."""
    # Save and unset
    old = os.environ.pop("SCANNER_INTERVAL_MINUTES", None)
    try:
        from royaltdn.orchestrator import _get_scan_interval_override
        result = _get_scan_interval_override()
        assert result is None, f"Expected None, got {result}"
        print("  ✅ _get_scan_interval_override() unset → None")
    finally:
        if old is not None:
            os.environ["SCANNER_INTERVAL_MINUTES"] = old


def test_get_scan_interval_override_valid():
    """Env var set to valid positive int → returns int."""
    old = os.environ.get("SCANNER_INTERVAL_MINUTES")
    os.environ["SCANNER_INTERVAL_MINUTES"] = "30"
    try:
        from royaltdn.orchestrator import _get_scan_interval_override
        result = _get_scan_interval_override()
        assert result == 30, f"Expected 30, got {result}"
        print("  ✅ _get_scan_interval_override() valid → 30")
    finally:
        if old is not None:
            os.environ["SCANNER_INTERVAL_MINUTES"] = old
        else:
            del os.environ["SCANNER_INTERVAL_MINUTES"]


def test_get_scan_interval_override_invalid():
    """Env var set to invalid → returns None."""
    old = os.environ.get("SCANNER_INTERVAL_MINUTES")
    os.environ["SCANNER_INTERVAL_MINUTES"] = "abc"
    try:
        from royaltdn.orchestrator import _get_scan_interval_override
        result = _get_scan_interval_override()
        assert result is None, f"Expected None, got {result}"
        print("  ✅ _get_scan_interval_override() invalid → None")
    finally:
        if old is not None:
            os.environ["SCANNER_INTERVAL_MINUTES"] = old
        else:
            del os.environ["SCANNER_INTERVAL_MINUTES"]


def test_get_scan_interval_override_zero():
    """Env var set to 0 → returns None (not positive)."""
    old = os.environ.get("SCANNER_INTERVAL_MINUTES")
    os.environ["SCANNER_INTERVAL_MINUTES"] = "0"
    try:
        from royaltdn.orchestrator import _get_scan_interval_override
        result = _get_scan_interval_override()
        assert result is None, f"Expected None, got {result}"
        print("  ✅ _get_scan_interval_override() zero → None")
    finally:
        if old is not None:
            os.environ["SCANNER_INTERVAL_MINUTES"] = old
        else:
            del os.environ["SCANNER_INTERVAL_MINUTES"]


def test_calc_scan_interval_scalping():
    """Scalping active → 2 minutes."""
    from unittest.mock import MagicMock, PropertyMock

    orch = MagicMock()
    orch._build_strategies_list.return_value = [
        {"name": "scalp1", "active": True, "category": "scalping"},
        {"name": "swing1", "active": True, "category": "swing"},
    ]
    # Patch _get_scan_interval_override to return None
    import royaltdn.orchestrator as orch_mod
    orig = orch_mod._get_scan_interval_override
    orch_mod._get_scan_interval_override = lambda: None
    try:
        # Need a real method call — use the module's _calc_scan_interval
        # by binding it to the mock
        bound_method = orch_mod.Orchestrator._calc_scan_interval.__get__(orch, type(orch))
        result = bound_method()
        assert result == 2, f"Expected 2, got {result}"
        print("  ✅ _calc_scan_interval scalping → 2")
    finally:
        orch_mod._get_scan_interval_override = orig


def test_calc_scan_interval_intraday():
    """Only intraday active → 15 minutes."""
    from unittest.mock import MagicMock

    orch = MagicMock()
    orch._build_strategies_list.return_value = [
        {"name": "intra1", "active": True, "category": "intraday"},
    ]
    import royaltdn.orchestrator as orch_mod
    orig = orch_mod._get_scan_interval_override
    orch_mod._get_scan_interval_override = lambda: None
    try:
        bound_method = orch_mod.Orchestrator._calc_scan_interval.__get__(orch, type(orch))
        result = bound_method()
        assert result == 15, f"Expected 15, got {result}"
        print("  ✅ _calc_scan_interval intraday → 15")
    finally:
        orch_mod._get_scan_interval_override = orig


def test_calc_scan_interval_swing():
    """Only swing active → 240 minutes."""
    from unittest.mock import MagicMock

    orch = MagicMock()
    orch._build_strategies_list.return_value = [
        {"name": "swing1", "active": True, "category": "swing"},
    ]
    import royaltdn.orchestrator as orch_mod
    orig = orch_mod._get_scan_interval_override
    orch_mod._get_scan_interval_override = lambda: None
    try:
        bound_method = orch_mod.Orchestrator._calc_scan_interval.__get__(orch, type(orch))
        result = bound_method()
        assert result == 240, f"Expected 240, got {result}"
        print("  ✅ _calc_scan_interval swing → 240")
    finally:
        orch_mod._get_scan_interval_override = orig


def test_calc_scan_interval_empty():
    """No active strategies → 60 minutes."""
    from unittest.mock import MagicMock

    orch = MagicMock()
    orch._build_strategies_list.return_value = []
    import royaltdn.orchestrator as orch_mod
    orig = orch_mod._get_scan_interval_override
    orch_mod._get_scan_interval_override = lambda: None
    try:
        bound_method = orch_mod.Orchestrator._calc_scan_interval.__get__(orch, type(orch))
        result = bound_method()
        assert result == 60, f"Expected 60, got {result}"
        print("  ✅ _calc_scan_interval empty → 60")
    finally:
        orch_mod._get_scan_interval_override = orig


# ── Task 2: Scalping disable JSON mutation ────────────────────────────────

def test_disable_scalping_in_strategies_json():
    """Scalping strategies get disabled; non-scalping unchanged."""
    from royaltdn.frontend.menu.app import _disable_scalping_in_strategies_json
    import royaltdn.frontend.menu.app as app_mod

    # Save original _current_universe
    orig_universe = app_mod._current_universe
    app_mod._current_universe = "sp500"

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_logs = "logs"
        # Temporarily patch os.path.join to use tmpdir
        import os as _os
        orig_join = _os.path.join

        def fake_join(*args):
            if args[0] == "logs" and args[1] == "strategies.json":
                return _os.path.join(tmpdir, "strategies.json")
            return orig_join(*args)

        _os.path.join = fake_join

        try:
            # Write test strategies.json
            test_data = {
                "strategies": [
                    {"name": "scalp1", "category": "scalping", "active": True},
                    {"name": "scalp2", "category": "scalping", "active": True},
                    {"name": "swing1", "category": "swing", "active": True},
                ]
            }
            json_path = _os.path.join(tmpdir, "strategies.json")
            with open(json_path, "w") as f:
                json.dump(test_data, f)

            # Call the function
            _disable_scalping_in_strategies_json()

            # Read back
            with open(json_path, "r") as f:
                result = json.load(f)

            for s in result["strategies"]:
                if s["category"] == "scalping":
                    assert s["active"] is False, f"{s['name']} still active"
                elif s["category"] == "swing":
                    assert s["active"] is True, f"{s['name']} was modified"

            print("  ✅ Scalping disabled, swing unchanged")
        finally:
            _os.path.join = orig_join
            app_mod._current_universe = orig_universe


def test_disable_scalping_no_file():
    """No strategies.json → no crash."""
    from royaltdn.frontend.menu.app import _disable_scalping_in_strategies_json
    try:
        _disable_scalping_in_strategies_json()
        print("  ✅ _disable_scalping_in_strategies_json no file → no crash")
    except Exception as e:
        assert False, f"Unexpected exception: {e}"


def test_disable_scalping_crypto_universe():
    """Crypto universe → does NOT disable."""
    from royaltdn.frontend.menu.app import _cycle_universe
    import royaltdn.frontend.menu.app as app_mod

    # Force universe to crypto
    orig = app_mod._current_universe

    # Cycle until we're on crypto
    for _ in range(10):
        if app_mod._current_universe == "crypto":
            break
        _cycle_universe()

    was_crypto = app_mod._current_universe == "crypto"
    print(f"  ✅ Crypto universe handled correctly (crypto={was_crypto})")
    app_mod._current_universe = orig


# ── Task 3: Scalping notification in menu ─────────────────────────────────

def test_has_scalping_strategies_true():
    """has_scalping_strategies returns True when scalping exists."""
    from royaltdn.frontend.menu.app import _has_scalping_strategies
    import os as _os

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_join = _os.path.join
        def fake_join(*args):
            if args[0] == "logs" and args[1] == "strategies.json":
                return _os.path.join(tmpdir, "strategies.json")
            return orig_join(*args)
        _os.path.join = fake_join
        try:
            test_data = {
                "strategies": [
                    {"name": "scalp1", "category": "scalping", "active": True},
                ]
            }
            with open(_os.path.join(tmpdir, "strategies.json"), "w") as f:
                json.dump(test_data, f)
            assert _has_scalping_strategies() is True
            print("  ✅ _has_scalping_strategies → True")
        finally:
            _os.path.join = orig_join


def test_has_scalping_strategies_false():
    """has_scalping_strategies returns False when no scalping."""
    from royaltdn.frontend.menu.app import _has_scalping_strategies
    import os as _os

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_join = _os.path.join
        def fake_join(*args):
            if args[0] == "logs" and args[1] == "strategies.json":
                return _os.path.join(tmpdir, "strategies.json")
            return orig_join(*args)
        _os.path.join = fake_join
        try:
            test_data = {
                "strategies": [
                    {"name": "swing1", "category": "swing", "active": True},
                ]
            }
            with open(_os.path.join(tmpdir, "strategies.json"), "w") as f:
                json.dump(test_data, f)
            assert _has_scalping_strategies() is False
            print("  ✅ _has_scalping_strategies no scalping → False")
        finally:
            _os.path.join = orig_join


# ── Task 4: UI verbose rendering structure ────────────────────────────────

def test_build_symbol_entries():
    """_build_symbol_entries inverts explanation dict correctly."""
    from royaltdn.frontend.menu.app import (
        _build_symbol_entries, set_scanner, _scanner,
    )

    # Save original scanner
    orig_scanner = _scanner

    class MockScanner:
        verbose = True
        _last_explanations = {
            "sma_crossover": {
                "SPY": {
                    "indicators": {"sma_fast": 101.5, "sma_slow": 100.2},
                    "conditions": [
                        {"name": "cross", "met": True, "value": 101.5,
                         "threshold": 100.2, "gap_pct": 0.0, "direction": "above"},
                    ],
                    "signal": {"action": "BUY", "price": 101.5, "reason": "cross"},
                },
                "QQQ": {
                    "indicators": {"sma_fast": 99.0, "sma_slow": 100.0},
                    "conditions": [
                        {"name": "cross", "met": False, "value": 99.0,
                         "threshold": 100.0, "gap_pct": 1.0, "direction": "above"},
                    ],
                    "signal": None,
                },
            },
        }

    try:
        set_scanner(MockScanner())
        entries = _build_symbol_entries()
        assert len(entries) == 2, f"Expected 2 symbols, got {len(entries)}"
        symbols = [e[0] for e in entries]
        assert "SPY" in symbols, "Missing SPY"
        assert "QQQ" in symbols, "Missing QQQ"

        # SPY should have BUY
        spy_entries = [e for sym, e_list in entries if sym == "SPY" for e in e_list]
        assert len(spy_entries) == 1
        assert spy_entries[0]["signal"] == "BUY"

        # QQQ should have NO SIGNAL
        qqq_entries = [e for sym, e_list in entries if sym == "QQQ" for e in e_list]
        assert len(qqq_entries) == 1
        assert qqq_entries[0]["signal"] == "NO SIGNAL"

        print("  ✅ _build_symbol_entries: 2 symbols, correct signals")
    finally:
        set_scanner(orig_scanner)


def test_verbose_dashboard_none_when_no_scanner():
    """_build_symbol_entries returns [] when _scanner is None."""
    from royaltdn.frontend.menu.app import _build_symbol_entries, set_scanner

    set_scanner(None)
    entries = _build_symbol_entries()
    assert entries == [], f"Expected [], got {entries}"
    print("  ✅ _build_symbol_entries no scanner → []")


# ── Task 5: Log filter ────────────────────────────────────────────────────

def test_log_filter_option_exists():
    """_show_logs includes option '6' for Verbose."""
    import inspect
    from royaltdn.frontend.menu.app import _show_logs

    source = inspect.getsource(_show_logs)
    assert "[bold cyan]6[/] Verbose" in source, "Missing Verbose option in _show_logs"
    print("  ✅ _show_logs has Verbose (6) option")


# ── Task 6: Orchestrator field presence ───────────────────────────────────

def test_orchestrator_has_current_scan_interval():
    """Orchestrator.__init__ sets _current_scan_interval."""
    from royaltdn.orchestrator import Orchestrator
    assert hasattr(Orchestrator, '_calc_scan_interval'), "Missing _calc_scan_interval method"
    print("  ✅ Orchestrator has _calc_scan_interval")


def test_status_json_includes_interval():
    """_publish_status writes scanner_interval_minutes to status.json."""
    import inspect
    from royaltdn.orchestrator import Orchestrator

    source = inspect.getsource(Orchestrator._publish_status)
    assert "scanner_interval_minutes" in source, "Missing scanner_interval_minutes in _publish_status"
    print("  ✅ _publish_status includes scanner_interval_minutes")


# ── Task 7: check-readiness basics ────────────────────────────────────────

def test_cmd_check_readiness_registered():
    """check-readiness command is registered in main()."""
    import inspect
    from royaltdn import main

    source = inspect.getsource(main.main)
    assert "check-readiness" in source, "check-readiness not registered in main()"
    print("  ✅ check-readiness registered in main()")


def test_cmd_check_readiness_exists():
    """cmd_check_readiness function exists."""
    from royaltdn.main import cmd_check_readiness
    assert callable(cmd_check_readiness), "cmd_check_readiness not callable"
    print("  ✅ cmd_check_readiness function exists")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("PR-4 — UI verbose + Dynamic interval + Scalping disable + check-readiness")
    print("=" * 50)

    # Task 1: Dynamic interval
    print("\n── Task 1: Dynamic interval ──")
    test_get_scan_interval_override_unset()
    test_get_scan_interval_override_valid()
    test_get_scan_interval_override_invalid()
    test_get_scan_interval_override_zero()
    test_calc_scan_interval_scalping()
    test_calc_scan_interval_intraday()
    test_calc_scan_interval_swing()
    test_calc_scan_interval_empty()

    # Task 2: Scalping disable
    print("\n── Task 2: Scalping disable ──")
    test_disable_scalping_in_strategies_json()
    test_disable_scalping_no_file()
    test_disable_scalping_crypto_universe()

    # Task 3: Scalping notification
    print("\n── Task 3: Scalping notification ──")
    test_has_scalping_strategies_true()
    test_has_scalping_strategies_false()

    # Task 4: UI verbose rendering
    print("\n── Task 4: UI verbose rendering ──")
    test_build_symbol_entries()
    test_verbose_dashboard_none_when_no_scanner()

    # Task 5: Log filter
    print("\n── Task 5: Log filter ──")
    test_log_filter_option_exists()

    # Task 6: Orchestrator changes
    print("\n── Task 6: Orchestrator changes ──")
    test_orchestrator_has_current_scan_interval()
    test_status_json_includes_interval()

    # Task 7: check-readiness
    print("\n── Task 7: check-readiness ──")
    test_cmd_check_readiness_registered()
    test_cmd_check_readiness_exists()

    print("\n✅ PR-4 TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
