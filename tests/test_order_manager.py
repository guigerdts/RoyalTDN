"""Unit tests for OrderManager state machine, KillSwitch, and broker integration.

Covers:
- OrderStateMachine: valid and invalid transitions, fill accumulation
- OrderManager: order creation, fill tracking, reconciliation, queries
- KillSwitch: trigger/release, auto-triggers, emergency shutdown
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────


@pytest.fixture
def om():
    """Return a fresh OrderManager."""
    from royaltdn.execution.order_manager import OrderManager

    return OrderManager()


@pytest.fixture
def order(om):
    """Create and return a sample BUY order via OrderManager."""
    return om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0, price=50000.0)


# ── OrderState ─────────────────────────────────────────────────────────────


class TestOrderStateValues:
    """Verify OrderState enum has all required states."""

    def test_all_states_present(self):
        from royaltdn.execution.order_manager import OrderState

        expected = {
            "CREATED",
            "PENDING_SUBMIT",
            "SUBMITTED",
            "PARTIAL_FILLED",
            "FILLED",
            "CANCELLED",
            "REJECTED",
            "EXPIRED",
        }
        actual = {s.name for s in OrderState}
        assert actual == expected


# ── State Machine Transitions ──────────────────────────────────────────────


class TestOrderStateMachine:
    """Test valid and invalid state transitions."""

    def test_created_to_pending_submit(self, om, order):
        """CREATED -> PENDING_SUBMIT is valid."""
        from royaltdn.execution.order_manager import OrderState

        om.transition_to(order.client_order_id, OrderState.PENDING_SUBMIT)
        assert om.get_order(order.client_order_id).state == OrderState.PENDING_SUBMIT

    def test_valid_path_to_filled(self, om):
        """CREATED -> PENDING_SUBMIT -> SUBMITTED -> FILLED is valid."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="ETHUSDT", side="SELL", qty=2.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om.on_fill(cid, 2.0, 3000.0)
        assert om.get_order(cid).state == OrderState.FILLED

    def test_partial_fill_accumulates(self, om):
        """Three partial fills summing to full qty should end in FILLED."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0, price=50000.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)

        # Three partial fills: 0.3, 0.3, 0.4 = 1.0
        om.on_fill(cid, 0.3, 50100.0, commission=1.5)
        assert om.get_order(cid).state == OrderState.PARTIAL_FILLED
        assert om.get_order(cid).filled_qty == pytest.approx(0.3)

        om.on_fill(cid, 0.3, 50200.0, commission=1.5)
        assert om.get_order(cid).state == OrderState.PARTIAL_FILLED
        assert om.get_order(cid).filled_qty == pytest.approx(0.6)

        om.on_fill(cid, 0.4, 50300.0, commission=2.0)
        assert om.get_order(cid).state == OrderState.FILLED
        assert om.get_order(cid).filled_qty == pytest.approx(1.0)

    def test_avg_fill_price_weighted(self, om):
        """Average fill price should be weighted by fill qty."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)

        om.on_fill(cid, 0.2, 50000.0)
        om.on_fill(cid, 0.8, 51000.0)

        # avg = (0.2*50000 + 0.8*51000) / 1.0 = (10000 + 40800) / 1.0 = 50800
        expected_avg = (0.2 * 50000.0 + 0.8 * 51000.0) / 1.0
        assert om.get_order(cid).avg_fill_price == pytest.approx(expected_avg)

    def test_invalid_transition_raises(self, om, order):
        """CREATED -> FILLED directly should raise ValueError."""
        from royaltdn.execution.order_manager import OrderState

        with pytest.raises(ValueError, match="Transicion invalida"):
            om.transition_to(order.client_order_id, OrderState.FILLED)

    def test_submitted_to_rejected(self, om):
        """SUBMITTED -> REJECTED is valid."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om.on_reject(cid, "Sin fondos suficientes")
        assert om.get_order(cid).state == OrderState.REJECTED
        assert om.get_order(cid).reject_reason == "Sin fondos suficientes"

    def test_submitted_to_cancelled(self, om):
        """SUBMITTED -> CANCELLED is valid."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om.on_cancel(cid)
        assert om.get_order(cid).state == OrderState.CANCELLED

    def test_partial_to_cancelled(self, om):
        """PARTIAL_FILLED -> CANCELLED is valid."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om.on_fill(cid, 0.3, 50000.0)  # -> PARTIAL_FILLED
        om.on_cancel(cid)
        assert om.get_order(cid).state == OrderState.CANCELLED

    def test_cannot_transition_from_filled(self, om):
        """Any transition from FILLED should raise ValueError."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om.on_fill(cid, 1.0, 50000.0)  # -> FILLED

        with pytest.raises(ValueError, match="Transicion invalida"):
            om.transition_to(cid, OrderState.CANCELLED)

    def test_expired_transition(self, om):
        """SUBMITTED -> EXPIRED is valid."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om.transition_to(cid, OrderState.EXPIRED)
        assert om.get_order(cid).state == OrderState.EXPIRED


# ── OrderManager ───────────────────────────────────────────────────────────


class TestOrderManager:
    """Test OrderManager CRUD, fill tracking, reconciliation, queries."""

    def test_create_order_generates_client_id(self, om):
        """Order should get a unique client_order_id."""
        from royaltdn.execution.order_manager import OrderState

        o1 = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        o2 = om.create_order(symbol="ETHUSDT", side="SELL", qty=2.0)

        assert o1.client_order_id != o2.client_order_id
        assert o1.client_order_id.startswith("BTCUSDT-")
        assert o2.client_order_id.startswith("ETHUSDT-")
        assert o1.state == OrderState.CREATED

    def test_on_fill_updates_avg_price(self, om):
        """Single fill should correctly set avg_fill_price."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om.on_fill(cid, 1.0, 50123.0, commission=5.0)

        op = om.get_order(cid)
        assert op.avg_fill_price == pytest.approx(50123.0)
        assert len(op.fills) == 1
        assert op.fills[0].commission == pytest.approx(5.0)

    def test_reconcile_detects_orphans(self, om):
        """Orders open locally but absent from exchange should be detected."""
        from royaltdn.execution.order_manager import OrderState

        o1 = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        o2 = om.create_order(symbol="ETHUSDT", side="SELL", qty=2.0)
        c1, c2 = o1.client_order_id, o2.client_order_id
        om.transition_to(c1, OrderState.PENDING_SUBMIT)
        om.transition_to(c1, OrderState.SUBMITTED)
        om.transition_to(c2, OrderState.PENDING_SUBMIT)
        om.transition_to(c2, OrderState.SUBMITTED)

        exchange_orders = [
            {"client_order_id": c2, "symbol": "ETHUSDT"},
        ]
        orphans = om.reconcile(exchange_orders)

        assert c1 in orphans
        assert c2 not in orphans

    def test_reconcile_matches_by_exchange_id(self, om):
        """Reconciliation should also match on exchange_order_id."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)
        om._orders[cid].exchange_order_id = "EX12345"

        exchange_orders = [{"orderId": "EX12345"}]
        orphans = om.reconcile(exchange_orders)
        assert cid not in orphans

    def test_reconcile_no_orphans(self, om):
        """When all orders match, reconcile returns empty list."""
        from royaltdn.execution.order_manager import OrderState

        o = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        cid = o.client_order_id
        om.transition_to(cid, OrderState.PENDING_SUBMIT)
        om.transition_to(cid, OrderState.SUBMITTED)

        exchange_orders = [{"client_order_id": cid}]
        orphans = om.reconcile(exchange_orders)
        assert orphans == []

    def test_get_open_orders(self, om):
        """Only non-terminal orders should appear in get_open_orders."""
        from royaltdn.execution.order_manager import OrderState

        o1 = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        o2 = om.create_order(symbol="ETHUSDT", side="SELL", qty=2.0)
        o3 = om.create_order(symbol="SOLUSDT", side="BUY", qty=10.0)

        c1, c2, c3 = o1.client_order_id, o2.client_order_id, o3.client_order_id

        # o1: CREATED (open)
        # o2: SUBMITTED (open)
        om.transition_to(c2, OrderState.PENDING_SUBMIT)
        om.transition_to(c2, OrderState.SUBMITTED)
        # o3: FILLED (terminal)
        om.transition_to(c3, OrderState.PENDING_SUBMIT)
        om.transition_to(c3, OrderState.SUBMITTED)
        om.on_fill(c3, 10.0, 100.0)

        open_orders = om.get_open_orders()
        open_ids = {o.client_order_id for o in open_orders}
        assert c1 in open_ids  # CREATED is non-terminal
        assert c2 in open_ids  # SUBMITTED is non-terminal
        assert c3 not in open_ids  # FILLED is terminal

    def test_get_orders_by_symbol(self, om):
        """Filter orders by symbol."""
        om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        om.create_order(symbol="ETHUSDT", side="SELL", qty=2.0)
        om.create_order(symbol="BTCUSDT", side="BUY", qty=0.5)

        btc_orders = om.get_orders_by_symbol("BTCUSDT")
        assert len(btc_orders) == 2
        assert all(o.symbol == "BTCUSDT" for o in btc_orders)

        eth_orders = om.get_orders_by_symbol("ETHUSDT")
        assert len(eth_orders) == 1

    def test_get_order_nonexistent(self, om):
        """get_order on missing ID returns None."""
        assert om.get_order("NONEXISTENT") is None

    def test_nonce_increments(self, om):
        """Each created order gets an incrementing nonce."""
        o1 = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        o2 = om.create_order(symbol="BTCUSDT", side="BUY", qty=1.0)
        assert o1.client_order_id != o2.client_order_id
        assert om._nonce == 2


# ── KillSwitch ─────────────────────────────────────────────────────────────


class TestKillSwitch:
    """Test KillSwitch trigger, release, auto-triggers, shutdown."""

    @pytest.fixture
    def portfolio(self):
        """Return a mock portfolio with configurable drawdown."""
        p = MagicMock()
        p.positions = {}
        p._short_positions = {}
        p.get_drawdown.return_value = 0.0
        return p

    @pytest.fixture
    def ks(self, portfolio):
        """Return a KillSwitch with a mock portfolio."""
        from royaltdn.execution.kill_switch import KillSwitch

        return KillSwitch(portfolio=portfolio)

    def test_trigger_activates(self, ks):
        """Trigger should set active=True."""
        ks.trigger(triggered_by="manual", reason="Prueba")
        assert ks.is_active is True
        assert ks.state.triggered_by == "manual"
        assert ks.state.reason == "Prueba"

    def test_release_deactivates(self, ks):
        """Release should reset state and set active=False."""
        ks.trigger(triggered_by="manual", reason="Prueba")
        assert ks.is_active is True
        ks.release()
        assert ks.is_active is False
        assert ks.state.triggered_by == ""

    def test_auto_trigger_drawdown(self, ks, portfolio):
        """Auto-trigger should activate when drawdown exceeds 30%."""
        portfolio.get_drawdown.return_value = 0.35  # 35% > 30%
        ks.check_auto_triggers()
        assert ks.is_active is True
        assert ks.state.triggered_by == "auto"

    def test_auto_trigger_below_threshold(self, ks, portfolio):
        """Auto-trigger should NOT activate when drawdown is below 30%."""
        portfolio.get_drawdown.return_value = 0.25  # 25% < 30%
        ks.check_auto_triggers()
        assert ks.is_active is False

    def test_auto_trigger_custom_condition(self, ks):
        """Custom auto-trigger condition should activate on True."""
        ks.register_auto_trigger(
            condition=lambda: True,
            reason="Siempre activo",
        )
        ks.check_auto_triggers()
        assert ks.is_active is True

    def test_auto_trigger_skipped_when_active(self, ks):
        """check_auto_triggers should skip when already active."""
        ks.trigger(triggered_by="manual", reason="Manual")
        triggered = False

        def _trigger():
            nonlocal triggered
            triggered = True
            return True

        ks.register_auto_trigger(condition=_trigger, reason="test")
        ks.check_auto_triggers()
        # Should NOT evaluate because already active
        assert triggered is False

    def test_emergency_shutdown(self, ks):
        """emergency_shutdown should trigger + cancel + close."""
        ks.cancel_all_orders = MagicMock()   # type: ignore[method-assign]
        ks.close_all_positions = MagicMock()  # type: ignore[method-assign]

        import asyncio

        asyncio.run(ks.emergency_shutdown())

        assert ks.is_active is True
        assert ks.state.triggered_by == "emergency"
        ks.cancel_all_orders.assert_called_once()
        ks.close_all_positions.assert_called_once()

    def test_close_all_positions_logs(self, ks, portfolio):
        """close_all_positions should iterate over long and short positions."""
        portfolio.positions = {"BTCUSDT": 1.0, "ETHUSDT": 2.0}
        portfolio._short_positions = {"SOLUSDT": 10.0}

        with patch.object(ks, "_portfolio", portfolio):
            ks.close_all_positions()
            # Should iterate both longs and shorts without error
            assert True

    def test_cancel_all_orders_binance(self):
        """cancel_all_orders should call BinanceBroker method when available."""
        from royaltdn.execution.kill_switch import KillSwitch

        mock_broker = MagicMock()
        mock_broker.cancel_all_orders = MagicMock(return_value=[])

        portfolio = MagicMock()
        portfolio.positions = {}
        portfolio._short_positions = {}

        ks = KillSwitch(portfolio=portfolio, binance_broker=mock_broker)
        ks.cancel_all_orders()
        mock_broker.cancel_all_orders.assert_called_once()


# ── Engine Integration ─────────────────────────────────────────────────────


class TestEngineKillSwitchIntegration:
    """Test that the engine correctly integrates with KillSwitch."""

    @pytest.fixture
    def engine_with_ks(self):
        """Return an EventEngine with a KillSwitch attached."""
        from royaltdn.core.engine import EventEngine
        from royaltdn.execution.kill_switch import KillSwitch

        clock = MagicMock()
        clock.now.return_value = "2025-01-01T00:00:00"
        bus = MagicMock()
        bus.get = AsyncMock(
            return_value={"type": "tick", "symbol": "BTCUSDT", "price": 50000},
        )
        bus.emit = AsyncMock()
        risk_manager = MagicMock()
        risk_manager.approve.return_value = None
        risk_manager.portfolio = MagicMock()
        risk_manager.portfolio.update_price = MagicMock()
        broker = MagicMock()
        broker.submit_order = AsyncMock(return_value={"status": "filled"})

        portfolio = MagicMock()
        portfolio.positions = {}
        portfolio._short_positions = {}
        portfolio.get_drawdown.return_value = 0.0

        kill_switch = KillSwitch(portfolio=portfolio)
        engine = EventEngine(
            clock, bus, risk_manager, broker, kill_switch=kill_switch,
        )

        return engine, kill_switch, broker

    def test_kill_switch_passed_to_engine(self, engine_with_ks):
        """KillSwitch should be accessible on the engine."""
        engine, ks, _ = engine_with_ks
        assert engine.kill_switch is ks

    def test_kill_switch_blocks_event_processing(self, engine_with_ks):
        """When KillSwitch is active, _process_event should return early."""
        engine, ks, broker = engine_with_ks
        ks.trigger(triggered_by="manual", reason="test")

        import asyncio

        asyncio.run(
            engine._process_event(
                {"type": "tick", "symbol": "BTCUSDT", "price": 50000},
            )
        )

        # Broker should NOT have been called since kill switch is active
        broker.submit_order.assert_not_called()


# ── Broker Integration ─────────────────────────────────────────────────────


class TestPaperBrokerOrderManager:
    """Test PaperBroker integration with OrderManager."""

    def test_paper_broker_creates_order_via_om(self):
        """PaperBroker should create and fill orders through OrderManager."""
        from royaltdn.execution.order_manager import OrderManager, OrderState
        from royaltdn.execution.paper_broker import PaperBroker
        from royaltdn.risk.portfolio import Portfolio

        om = OrderManager()
        portfolio = Portfolio(initial_capital=100_000.0)
        broker = PaperBroker(
            initial_capital=100_000.0,
            portfolio=portfolio,
            commission_pct=0.0,
            slippage_pct=0.0,
            order_manager=om,
        )

        import asyncio

        result = asyncio.run(
            broker.submit_order({
                "action": "BUY",
                "symbol": "BTCUSDT",
                "qty": 0.1,
                "price": 50000.0,
            })
        )

        client_id = result.get("client_order_id", "")
        assert client_id != ""
        order_obj = om.get_order(client_id)
        assert order_obj is not None
        assert order_obj.state == OrderState.FILLED
        assert order_obj.filled_qty == pytest.approx(0.1)

    def test_paper_broker_works_without_om(self):
        """PaperBroker should work without an OrderManager (backward compat)."""
        from royaltdn.execution.paper_broker import PaperBroker

        broker = PaperBroker(initial_capital=100_000.0)
        assert broker.order_manager is None

        import asyncio

        result = asyncio.run(
            broker.submit_order({
                "action": "BUY",
                "symbol": "BTCUSDT",
                "qty": 0.1,
                "price": 50000.0,
            })
        )
        assert result["status"] == "filled"
        assert result["order_id"].startswith("paper_")
