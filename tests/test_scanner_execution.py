#!/usr/bin/env python3
"""Tests for scanner signal execution pipeline (FASE 16).

Verifies the 7-gate pipeline in _execute_scanner_signals():
1. Normal signal executed successfully
2. Signal rejected by kill switch
3. Signal rejected by duplicate position
4. Signal rejected by max positions
5. Stock rejected when market closed (weekend)
6. Crypto executed 24/7 (even on weekend)
7. Signal rejected by exposure > 25%
8. Legacy coexistence: SPY skipped when legacy has position

Uso:
    pytest tests/test_scanner_execution.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock


# ── Test helpers ──────────────────────────────────────────────────────────

def _make_orchestrator():
    """Create an Orchestrator with mocked dependencies for scanner execution tests."""
    from royaltdn.orchestrator import Orchestrator

    with patch("royaltdn.orchestrator.PortfolioPositionManager") as mock_ppm_cls:
        mock_ppm = MagicMock()
        mock_ppm_cls.return_value = mock_ppm

        orch = Orchestrator(
            api_key="mock_key",
            secret_key="mock_secret",
            redis_url="redis://localhost:6379/0",
            db_url="",
            symbol="SPY",
        )

        # Configure for scanner execution
        orch.auto_execute = True
        orch.max_positions = 5
        orch.scanner_top_n = 3
        orch._portfolio = mock_ppm
        orch._trading = MagicMock()
        orch._trading.get_account.return_value.equity = "100000"
        orch._killed = False
        orch._consecutive_losses = 0
        orch._initial_equity = 100000.0

        # Mock risk manager functions
        with patch("royaltdn.orchestrator.check_risk_limits") as mock_risk:
            mock_risk.return_value = (False, "ok")

            with patch("royaltdn.orchestrator.get_atr") as mock_atr:
                mock_atr.return_value = 2.5

                with patch("royaltdn.orchestrator.calculate_position_size") as mock_size:
                    mock_size.return_value = 100

                    return orch, mock_ppm, mock_risk, mock_atr, mock_size


# ── Tests ─────────────────────────────────────────────────────────────────

def test_normal_signal_executed() -> None:
    """Happy path: signal passes all gates and is executed."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        mock_ppm.has_position.return_value = False
        mock_ppm.position_count.return_value = 0
        mock_ppm.get_symbol_exposure.return_value = 0.05

        signals = [{"symbol": "AAPL", "action": "BUY", "price": 150.0, "score": 0.9}]

        with patch.object(orch, '_submit_order', new=AsyncMock()) as mock_submit:
            mock_submit.return_value = MagicMock(filled_avg_price="150.5")

            with patch.object(orch, '_append_trade') as mock_trade:
                with patch("royaltdn.orchestrator.notify_entry", new=AsyncMock()):
                    await orch._execute_scanner_signals(signals)

                    mock_submit.assert_called_once()
                    mock_ppm.open_position.assert_called_once()
                    mock_trade.assert_called_once()

    asyncio.run(run())


def test_rejected_by_kill_switch() -> None:
    """Kill switch active: all signals rejected, positions closed."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        mock_risk.return_value = (True, "daily drawdown exceeded 3%")
        mock_ppm.close_all_positions.return_value = []

        signals = [{"symbol": "AAPL", "action": "BUY", "price": 150.0}]

        with patch.object(orch, '_submit_order', new=AsyncMock()):
            await orch._execute_scanner_signals(signals)

            mock_ppm.close_all_positions.assert_called_once()
            assert orch._killed is True

    asyncio.run(run())


def test_rejected_by_duplicate() -> None:
    """Duplicate symbol: signal skipped."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        mock_ppm.has_position.return_value = True  # Already has AAPL
        mock_ppm.position_count.return_value = 1

        signals = [{"symbol": "AAPL", "action": "BUY", "price": 150.0}]

        with patch.object(orch, '_submit_order', new=AsyncMock()) as mock_submit:
            with patch.object(orch, '_append_trade') as mock_trade:
                await orch._execute_scanner_signals(signals)

                mock_submit.assert_not_called()
                mock_ppm.open_position.assert_not_called()

    asyncio.run(run())


def test_rejected_by_max_positions() -> None:
    """Max positions reached: signal skipped."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        orch.max_positions = 5
        mock_ppm.has_position.return_value = False
        mock_ppm.position_count.return_value = 5  # At max

        signals = [{"symbol": "AAPL", "action": "BUY", "price": 150.0}]

        with patch.object(orch, '_submit_order', new=AsyncMock()) as mock_submit:
            await orch._execute_scanner_signals(signals)
            mock_submit.assert_not_called()

    asyncio.run(run())


def test_stock_rejected_market_closed() -> None:
    """Stock symbol rejected when market is closed (weekend)."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        mock_ppm.has_position.return_value = False
        mock_ppm.position_count.return_value = 0

        signals = [{"symbol": "AAPL", "action": "BUY", "price": 150.0}]

        with patch.object(orch, '_is_market_open', return_value=False):
            with patch.object(orch, '_submit_order', new=AsyncMock()) as mock_submit:
                await orch._execute_scanner_signals(signals)
                mock_submit.assert_not_called()

    asyncio.run(run())


def test_crypto_executed_24_7() -> None:
    """Crypto symbol executed regardless of market hours."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        mock_ppm.has_position.return_value = False
        mock_ppm.position_count.return_value = 0
        mock_ppm.get_symbol_exposure.return_value = 0.05

        signals = [{"symbol": "BTC/USD", "action": "BUY", "price": 45000.0}]

        with patch.object(orch, '_submit_order', new=AsyncMock()) as mock_submit:
            mock_submit.return_value = MagicMock(filled_avg_price="45100.0")
            with patch.object(orch, '_append_trade'):
                with patch("royaltdn.orchestrator.notify_entry", new=AsyncMock()):
                    await orch._execute_scanner_signals(signals)
                    mock_submit.assert_called_once()

    asyncio.run(run())


def test_rejected_by_exposure_limit() -> None:
    """Symbol exposure > 25%: signal rejected."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        mock_ppm.has_position.return_value = False
        mock_ppm.position_count.return_value = 1
        mock_ppm.get_symbol_exposure.return_value = 0.30  # 30% > 25%

        signals = [{"symbol": "AAPL", "action": "BUY", "price": 150.0}]

        with patch.object(orch, '_submit_order', new=AsyncMock()) as mock_submit:
            await orch._execute_scanner_signals(signals)
            mock_submit.assert_not_called()

    asyncio.run(run())


def test_legacy_coexistence_spy_skipped() -> None:
    """Legacy mode active + SPY position: scanner SPY signal skipped."""
    async def run():
        orch, mock_ppm, mock_risk, mock_atr, mock_size = _make_orchestrator()
        orch._use_legacy_fallback = True
        mock_ppm.has_position.return_value = True  # Legacy has SPY
        mock_ppm.position_count.return_value = 1

        signals = [{"symbol": "SPY", "action": "BUY", "price": 500.0}]

        with patch.object(orch, '_submit_order', new=AsyncMock()) as mock_submit:
            await orch._execute_scanner_signals(signals)
            mock_submit.assert_not_called()

    asyncio.run(run())
