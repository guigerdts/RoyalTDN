#!/usr/bin/env python3
"""Tests for Orchestrator._run_scanner() concurrency, timeout, and error handling.

Verifies:
1. _run_scanner() executes scan via executor without blocking
2. _is_scanning flag prevents concurrent scans
3. Timeout handling
4. Error isolation (errors don't propagate)
5. Auth error (401/403) handling
6. None scanner (scanner not available)

Uso:
    pytest tests/test_scanner_orchestrator.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asyncio
from unittest.mock import MagicMock, patch


# ── Helpers ──────────────────────────────────────────────────────────────

async def _make_orchestrator():
    """Create a minimal Orchestrator with mocked scanner."""
    from royaltdn.orchestrator import Orchestrator
    orch = Orchestrator(
        api_key="mock_key",
        secret_key="mock_secret",
        redis_url="redis://localhost:6379/0",
        db_url=None,
        symbol="SPY",
        sma_fast=5,
        sma_slow=20,
    )
    # Set up minimal scanner mock
    orch._scanner = MagicMock()
    orch._scanner.scan.return_value = [{"symbol": "SPY", "action": "BUY", "price": 100.0}]
    return orch


# ── Existing environment variable tests ─────────────────────────────────

def test_orchestrator_scanner_env_vars() -> None:
    """Scanner environment constants are defined and valid."""
    from royaltdn.orchestrator import (
        SCANNER_MIN_VOLUME,
        SCANNER_MIN_PRICE,
        SCANNER_MAX_SPREAD_PCT,
        SCANNER_INTERVAL_MINUTES,
        STRATEGIES_ENABLED,
        SCANNER_TOP_N,
        SCANNER_UNIVERSE,
    )

    assert SCANNER_MIN_VOLUME >= 0
    assert SCANNER_MIN_PRICE >= 0
    assert SCANNER_MAX_SPREAD_PCT >= 0
    assert SCANNER_INTERVAL_MINUTES > 0
    assert len(STRATEGIES_ENABLED) >= 1
    assert SCANNER_TOP_N >= 1
    assert SCANNER_UNIVERSE in ("etfs", "sp500", "all")
    print("  ✅ Scanner environment constants defined")


def test_orchestrator_construct_without_scanner() -> None:
    """Orchestrator can be constructed without scanner (None until _setup)."""
    from royaltdn.orchestrator import Orchestrator
    orch = Orchestrator(
        api_key="test_key",
        secret_key="test_secret",
        redis_url="redis://localhost:6379/0",
    )
    # Scanner is initialized in _setup(), not __init__
    assert orch._scanner is None
    print("  ✅ Orchestrator constructed (scanner=None until _setup)")


# ── _run_scanner tests ──────────────────────────────────────────────────

def test_orchestrator_run_scanner_executor() -> None:
    """_run_scanner() executes scan via executor without blocking."""
    async def run():
        orch = await _make_orchestrator()
        signals = await orch._run_scanner()
        assert signals is not None
        assert len(signals) > 0
        assert signals[0]["symbol"] == "SPY"
        orch._scanner.scan.assert_called_once()

    asyncio.run(run())


def test_orchestrator_scanner_concurrent() -> None:
    """_is_scanning flag prevents concurrent scans."""
    async def run():
        orch = await _make_orchestrator()
        orch._is_scanning = True
        signals = await orch._run_scanner()
        assert signals is None  # Should skip because already scanning
        orch._scanner.scan.assert_not_called()

    asyncio.run(run())


def test_orchestrator_scanner_timeout() -> None:
    """_run_scanner() handles timeout gracefully (mocked asyncio.wait_for)."""
    async def run():
        orch = await _make_orchestrator()

        orch._scanner.scan.return_value = []

        # Mock wait_for to raise TimeoutError so we test the code path
        # without actually needing a non-cooperative blocking call
        import royaltdn.orchestrator as _orch_mod
        with patch.object(
            _orch_mod.asyncio, "wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            signals = await orch._run_scanner()
            assert signals is None  # Timeout returns None
            assert not orch._is_scanning  # Flag must be reset

    asyncio.run(run())


def test_orchestrator_scanner_error_isolation() -> None:
    """Error inside executor does not propagate to caller."""
    async def run():
        orch = await _make_orchestrator()
        orch._scanner.scan.side_effect = ValueError("something went wrong")
        signals = await orch._run_scanner()
        assert signals is None  # Error returns None
        assert not orch._is_scanning  # Flag reset

    asyncio.run(run())


def test_orchestrator_scanner_auth_error() -> None:
    """401/403 error in scanner is logged but doesn't crash."""
    async def run():
        orch = await _make_orchestrator()
        orch._scanner.scan.side_effect = Exception("401 Unauthorized")
        signals = await orch._run_scanner()
        assert signals is None
        assert not orch._is_scanning

    asyncio.run(run())


def test_orchestrator_scanner_none() -> None:
    """_run_scanner() returns None when scanner is not available."""
    async def run():
        orch = await _make_orchestrator()
        orch._scanner = None
        signals = await orch._run_scanner()
        assert signals is None

    asyncio.run(run())


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 50)
    print("RoyalTDN — Test Scanner + Orchestrator (Fase 13)")
    print("=" * 50)

    test_orchestrator_scanner_env_vars()
    test_orchestrator_construct_without_scanner()
    test_orchestrator_run_scanner_executor()
    test_orchestrator_scanner_concurrent()
    test_orchestrator_scanner_timeout()
    test_orchestrator_scanner_error_isolation()
    test_orchestrator_scanner_auth_error()
    test_orchestrator_scanner_none()

    print("\n✅ ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
