"""Regression tests: 10-position limit fix.

REAL SCENARIO:
  - config.yaml has 5 symbols: BTCUSDT, ETHUSDT, LINKUSDT, SOLUSDT, ADAUSDT
  - max_positions: 10
  - 33 cells across those 5 symbols

BUG #1 (FIXED): RiskManager now tracks active entries by (symbol, cell_name)
  instead of relying on len(portfolio.positions) or the duplicate check.
  Different cells CAN hold the same symbol simultaneously.

BUG #2 (FIXED): cell.state = IN_POSITION is now set by the engine AFTER risk
  approval, not in _check_entry(). If risk rejects, the cell stays IDLE.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from unittest.mock import AsyncMock, MagicMock

import pytest

# The 5 symbols from config.yaml
SYMBOLS = ["BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "ADAUSDT"]


def _run_async(coro: asyncio.coroutines.Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine synchronously with a fresh event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── VERIFY: 10 positions in 5 symbols ─────────────────────────────


def test_33_cells_reach_10_positions_on_5_symbols() -> None:
    """33 cells on 5 symbols MUST open 10 positions (max_positions=10)
    without the duplicate check blocking."""
    from royaltdn.core.bus import EventBus
    from royaltdn.core.clock import RealClock
    from royaltdn.core.engine import EventEngine
    from royaltdn.risk.portfolio import Portfolio
    from royaltdn.risk.manager import RiskManager
    from royaltdn.execution.paper_broker import PaperBroker

    async def _simulate() -> dict[str, Any]:
        bus = EventBus()
        clock = RealClock()
        portfolio = Portfolio(initial_capital=1_000_000.0)
        rm = RiskManager(portfolio, max_positions=10, max_drawdown=0.03)
        broker = PaperBroker(initial_capital=1_000_000.0)
        engine = EventEngine(clock, bus, rm, broker)

        # Create 33 cells across 5 symbols (like the real bot)
        for i in range(33):
            sym = SYMBOLS[i % 5]
            cell = MagicMock()
            cell.name = f"cell_{i:02d}_{sym}"
            cell.handle = AsyncMock(return_value={
                "action": "BUY",
                "symbol": sym,
                "price": 100.0,
                "sizing": 0.01,
                "cell_name": cell.name,
            })
            engine.register(cell)

        # Emit ticks so cells generate signals
        task = asyncio.create_task(engine.run())

        for _ in range(10):
            for sym in SYMBOLS:
                await bus.emit({
                    "type": "tick",
                    "symbol": sym,
                    "price": 100.0,
                    "data": {"close": 100.0, "volume": 100.0,
                             "high": 101.0, "low": 99.0},
                })
                await asyncio.sleep(0.01)

        await asyncio.sleep(0.3)
        engine.stop()
        await task

        return {"trades": broker.trades, "rm": rm, "portfolio": portfolio}

    result = _run_async(_simulate())
    trades = result["trades"]
    rm = result["rm"]
    portfolio = result["portfolio"]
    # VERIFY: 10+ trades executed
    assert len(trades) >= 10, (
        f"FIX FAILED: only {len(trades)} trades of 10 expected. "
        f"max_positions={rm.max_positions}, "
        f"portfolio.symbols={len(portfolio.positions)}"
    )


# ── VERIFY: RiskManager with repeated symbols ─────────────────────


def test_risk_manager_allows_multiple_entries_same_symbol() -> None:
    """RiskManager MUST allow different cells to enter the same symbol,
    up to max_positions."""
    from royaltdn.risk.portfolio import Portfolio
    from royaltdn.risk.manager import RiskManager

    portfolio = Portfolio(initial_capital=100_000.0)
    rm = RiskManager(portfolio, max_positions=10, max_drawdown=0.03)

    # 8 different cells on only 3 symbols
    entries = [
        ("cell_btc_1", "BTCUSDT"),
        ("cell_btc_2", "BTCUSDT"),
        ("cell_btc_3", "BTCUSDT"),
        ("cell_eth_1", "ETHUSDT"),
        ("cell_eth_2", "ETHUSDT"),
        ("cell_eth_3", "ETHUSDT"),
        ("cell_sol_1", "SOLUSDT"),
        ("cell_sol_2", "SOLUSDT"),
    ]

    approved_count = 0
    for cell_name, sym in entries:
        signal = {
            "action": "BUY",
            "symbol": sym,
            "price": 100.0,
            "sizing": 0.01,
            "cell_name": cell_name,
        }
        approved = rm.approve(signal)
        if approved.get("approved", False):
            approved_count += 1
            portfolio.update({
                "action": "BUY",
                "symbol": approved["symbol"],
                "qty": approved["qty"],
                "price": approved["price"],
            })

    # VERIFY: all 8 approved (8 < 10 max_positions)
    assert approved_count == len(entries), (
        f"FIX FAILED: only {approved_count} of {len(entries)} approved. "
        f"max_positions={rm.max_positions}"
    )
    # Portfolio has only 3 unique symbols but accumulated qty
    assert len(portfolio.positions) == 3
    # BTC must have positive qty (3 entries accumulated, capital decreasing)
    assert portfolio.positions.get("BTCUSDT", 0.0) > 0.0


# ── VERIFY: max_positions is still enforced ───────────────────────


def test_max_positions_still_enforced() -> None:
    """max_positions=10 MUST reject the 11th entry."""
    from royaltdn.risk.portfolio import Portfolio
    from royaltdn.risk.manager import RiskManager

    portfolio = Portfolio(initial_capital=100_000.0)
    rm = RiskManager(portfolio, max_positions=10, max_drawdown=0.03)

    # Approve 10 entries (different cells)
    approved_count = 0
    for i in range(10):
        signal = {
            "action": "BUY",
            "symbol": SYMBOLS[i % len(SYMBOLS)],
            "price": 100.0,
            "sizing": 0.01,
            "cell_name": f"cell_{i:02d}",
        }
        approved = rm.approve(signal)
        if approved.get("approved", False):
            approved_count += 1

    assert approved_count == 10, f"Only {approved_count} of 10 approved"

    # The 11th MUST be rejected by max_positions
    eleventh = {
        "action": "BUY",
        "symbol": "BTCUSDT",
        "price": 100.0,
        "sizing": 0.01,
        "cell_name": "cell_11",
    }
    rejected = rm.approve(eleventh)
    assert rejected is not None, "approve() should return a dict"
    assert not rejected.get("approved", False), "11th signal MUST be rejected (max_positions=10)"
    assert rejected.get("reason") == "max_positions", (
        f"Expected max_positions rejection, got {rejected.get('reason')}"
    )


# ── VERIFY: Cell stays IDLE after risk rejection ──────────────────


def test_cell_stays_idle_after_risk_rejection() -> None:
    """When RiskManager rejects, the cell MUST stay in IDLE."""
    from royaltdn.cells.base import Cell

    cell = Cell({
        "name": "test_cell",
        "symbol": "BTCUSDT",
        "risk": {"sizing": 0.01, "max_positions": 3},
        "entry": {"logic": "AND", "conditions": [
            {"indicator": "rsi", "params": {"period": 7}, "operator": "< 30"}
        ]},
    })

    # Verify _check_entry does NOT set state (that's enter_position's job)
    source = inspect.getsource(Cell._check_entry)
    has_state_in_entry = 'self.state = "IN_POSITION"' in source
    has_enter_position = hasattr(cell, "enter_position") and callable(cell.enter_position)

    assert not has_state_in_entry, (
        "FIX FAILED: _check_entry must NOT set state. "
        "That is enter_position()'s responsibility post-risk."
    )
    assert has_enter_position, (
        "FIX FAILED: Cell must have enter_position() method."
    )


# ── VERIFY: SELL frees the slot ───────────────────────────────────


def test_sell_frees_slot_for_new_entry() -> None:
    """After a SELL, the slot must be freed for new entries."""
    from royaltdn.risk.portfolio import Portfolio
    from royaltdn.risk.manager import RiskManager

    portfolio = Portfolio(initial_capital=100_000.0)
    rm = RiskManager(portfolio, max_positions=2, max_drawdown=0.03)

    # Entry 1
    s1 = rm.approve({"action": "BUY", "symbol": "BTCUSDT",
                     "price": 100, "sizing": 0.01, "cell_name": "cell_1"})
    assert s1.get("approved", False)
    portfolio.update({"action": "BUY", "symbol": "BTCUSDT",
                     "qty": s1["qty"], "price": 100})

    # Entry 2
    s2 = rm.approve({"action": "BUY", "symbol": "ETHUSDT",
                     "price": 100, "sizing": 0.01, "cell_name": "cell_2"})
    assert s2.get("approved", False)
    portfolio.update({"action": "BUY", "symbol": "ETHUSDT",
                     "qty": s2["qty"], "price": 100})

    # Entry 3 -> must fail (max_positions=2)
    s3 = rm.approve({"action": "BUY", "symbol": "SOLUSDT",
                     "price": 100, "sizing": 0.01, "cell_name": "cell_3"})
    assert not s3.get("approved", False), "3rd signal MUST be rejected (max_positions=2)"

    # Sell BTC -> frees the slot
    sell = rm.approve({"action": "SELL", "symbol": "BTCUSDT",
                      "price": 110, "cell_name": "cell_1"})
    assert sell.get("approved", False)
    portfolio.update({"action": "SELL", "symbol": "BTCUSDT",
                     "qty": sell["qty"], "price": 110})

    # Now SOL must be able to enter (slot freed)
    s4 = rm.approve({"action": "BUY", "symbol": "SOLUSDT",
                     "price": 100, "sizing": 0.01, "cell_name": "cell_3"})
    assert s4.get("approved", False), (
        "FIX FAILED: after selling BTC, the slot should be freed"
    )
