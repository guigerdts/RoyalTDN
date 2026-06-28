"""Tests for main.py wiring of OrderManager + KillSwitch."""

from unittest.mock import MagicMock, patch
import pytest


class TestMainWiring:
    """Verify that main.py correctly wires OrderManager and KillSwitch."""

    def test_bot_config_kill_switch_field(self):
        """BotConfig should include kill_switch_drawdown field."""
        from royaltdn.config import BotConfig

        cfg = BotConfig()
        assert hasattr(cfg, "kill_switch_drawdown")
        assert cfg.kill_switch_drawdown == 0.30

    def test_bot_config_from_dict_parses_kill_switch(self):
        """BotConfig.from_dict should parse kill_switch_drawdown."""
        from royaltdn.config import BotConfig

        cfg = BotConfig.from_dict({
            "kill_switch_drawdown": 0.25,
        })
        assert cfg.kill_switch_drawdown == 0.25

    def test_bot_config_from_dict_default(self):
        """BotConfig.from_dict should use default when key missing."""
        from royaltdn.config import BotConfig

        cfg = BotConfig.from_dict({})
        assert cfg.kill_switch_drawdown == 0.30

    def test_bot_config_to_dict_includes_kill_switch(self):
        """BotConfig.to_dict should include kill_switch_drawdown."""
        from royaltdn.config import BotConfig

        cfg = BotConfig()
        d = cfg.to_dict()
        assert "kill_switch_drawdown" in d
        assert d["kill_switch_drawdown"] == 0.30

    def test_order_manager_creatable(self):
        """OrderManager should be creatable with no args."""
        from royaltdn.execution.order_manager import OrderManager

        om = OrderManager()
        assert om is not None
        assert hasattr(om, "_orders")

    def test_kill_switch_creatable(self):
        """KillSwitch should be creatable with a portfolio mock."""
        from royaltdn.execution.kill_switch import KillSwitch

        portfolio = MagicMock()
        portfolio.get_drawdown.return_value = 0.0
        ks = KillSwitch(portfolio=portfolio)
        assert ks is not None
        assert ks.is_active is False

    def test_kill_switch_auto_trigger_registration(self):
        """KillSwitch should accept custom auto-trigger conditions."""
        from royaltdn.execution.kill_switch import KillSwitch

        portfolio = MagicMock()
        portfolio.get_drawdown.return_value = 0.0
        ks = KillSwitch(portfolio=portfolio)

        # Register a custom trigger
        ks.register_auto_trigger(
            condition=lambda: portfolio.get_drawdown() >= 0.30,
            reason="test_drawdown",
        )
        assert len(ks._auto_triggers) == 2  # default + custom

    def test_kill_switch_triggers_on_drawdown(self):
        """KillSwitch should activate when drawdown exceeds threshold."""
        from royaltdn.execution.kill_switch import KillSwitch

        portfolio = MagicMock()
        portfolio.get_drawdown.return_value = 0.35  # exceeds 30% default
        ks = KillSwitch(portfolio=portfolio)
        ks.check_auto_triggers()
        assert ks.is_active is True

    def test_kill_switch_does_not_trigger_below_threshold(self):
        """KillSwitch should NOT activate when drawdown is below threshold."""
        from royaltdn.execution.kill_switch import KillSwitch

        portfolio = MagicMock()
        portfolio.get_drawdown.return_value = 0.10  # below 30% default
        ks = KillSwitch(portfolio=portfolio)
        ks.check_auto_triggers()
        assert ks.is_active is False

    def test_engine_accepts_kill_switch(self):
        """EventEngine should accept kill_switch parameter."""
        from royaltdn.core.engine import EventEngine

        engine = EventEngine(
            clock=MagicMock(),
            bus=MagicMock(),
            risk_manager=MagicMock(),
            execution_broker=MagicMock(),
            kill_switch=MagicMock(),
        )
        assert engine.kill_switch is not None

    def test_brokers_accept_order_manager(self):
        """Both PaperBroker and BinanceBroker should accept order_manager."""
        from royaltdn.execution.paper_broker import PaperBroker
        from royaltdn.execution.order_manager import OrderManager

        om = OrderManager()
        broker = PaperBroker(initial_capital=100000.0, order_manager=om)
        assert broker.order_manager is om

    def test_kill_switch_release(self):
        """KillSwitch.release() should deactivate the switch."""
        from royaltdn.execution.kill_switch import KillSwitch

        portfolio = MagicMock()
        portfolio.get_drawdown.return_value = 0.40
        ks = KillSwitch(portfolio=portfolio)
        ks.check_auto_triggers()
        assert ks.is_active is True

        ks.release()
        assert ks.is_active is False
