#!/usr/bin/env python3
"""Tests for RiskManager (FASE 16 additions).

Verifies:
1. check_portfolio_risk() — max positions, per-symbol exposure
2. get_atr() with crypto client (integration check)

Uso:
    pytest tests/test_risk_manager.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, patch


class TestCheckPortfolioRisk:
    """Test suite for check_portfolio_risk()."""

    def test_passes_when_under_limits(self):
        from royaltdn.risk_manager import check_portfolio_risk
        mock_portfolio = MagicMock()
        mock_portfolio.position_count.return_value = 2
        mock_portfolio.get_all_positions.return_value = {"AAPL": "pos1", "MSFT": "pos2"}
        mock_portfolio.get_symbol_exposure.return_value = 0.10
        mock_portfolio.get_total_exposure.return_value = 0.20

        passed, reason = check_portfolio_risk(mock_portfolio, 100000, max_positions=5, max_exposure_pct=0.25)
        assert passed is True
        assert reason == "ok"

    def test_fails_when_max_positions_reached(self):
        from royaltdn.risk_manager import check_portfolio_risk
        mock_portfolio = MagicMock()
        mock_portfolio.position_count.return_value = 5

        passed, reason = check_portfolio_risk(mock_portfolio, 100000, max_positions=5, max_exposure_pct=0.25)
        assert passed is False
        assert "max_positions_reached" in reason

    def test_fails_when_symbol_exceeds_max_exposure(self):
        from royaltdn.risk_manager import check_portfolio_risk
        mock_portfolio = MagicMock()
        mock_portfolio.position_count.return_value = 1
        mock_portfolio.get_all_positions.return_value = {"AAPL": "pos"}
        mock_portfolio.get_symbol_exposure.return_value = 0.30  # 30% > 25%

        passed, reason = check_portfolio_risk(mock_portfolio, 100000, max_positions=5, max_exposure_pct=0.25)
        assert passed is False
        assert "exposure_limit_exceeded" in reason

    def test_fails_when_total_exposure_exceeds_80_percent(self):
        from royaltdn.risk_manager import check_portfolio_risk
        mock_portfolio = MagicMock()
        mock_portfolio.position_count.return_value = 1
        mock_portfolio.get_all_positions.return_value = {"AAPL": "pos"}
        mock_portfolio.get_symbol_exposure.return_value = 0.20
        mock_portfolio.get_total_exposure.return_value = 0.85  # 85% > 80%

        passed, reason = check_portfolio_risk(mock_portfolio, 100000, max_positions=5, max_exposure_pct=0.25)
        assert passed is False
        assert "total_exposure_exceeded" in reason

    def test_passes_with_zero_equity(self):
        from royaltdn.risk_manager import check_portfolio_risk
        mock_portfolio = MagicMock()
        mock_portfolio.position_count.return_value = 0

        passed, reason = check_portfolio_risk(mock_portfolio, 0, max_positions=5, max_exposure_pct=0.25)
        assert passed is True


class TestGetATR:
    """Test suite for get_atr() with crypto support."""

    def test_get_atr_uses_crypto_client_for_crypto_symbols(self):
        from royaltdn.risk_manager import get_atr

        mock_stock_client = MagicMock()
        mock_crypto_client = MagicMock()
        mock_crypto_client.get_crypto_bars.return_value.df = MagicMock()

        with patch("royaltdn.risk_manager.CryptoBarsRequest"):
            with patch("royaltdn.risk_manager.pd.DataFrame") as mock_df:
                import pandas as pd
                import numpy as np

                # Create enough data for ATR calculation
                dates = pd.date_range("2024-01-01", periods=20, freq="D")
                df = pd.DataFrame({
                    "high": np.random.uniform(100, 110, 20),
                    "low": np.random.uniform(90, 100, 20),
                    "close": np.random.uniform(95, 105, 20),
                }, index=dates)
                mock_crypto_client.get_crypto_bars.return_value.df = df

                result = get_atr(mock_stock_client, "BTC/USD", period=14, crypto_data_client=mock_crypto_client)
                assert isinstance(result, float)
                assert result > 0
                mock_crypto_client.get_crypto_bars.assert_called_once()

    def test_get_atr_uses_stock_client_for_stock_symbols(self):
        from royaltdn.risk_manager import get_atr

        mock_stock_client = MagicMock()

        import pandas as pd
        import numpy as np

        dates = pd.date_range("2024-01-01", periods=20, freq="D")
        df = pd.DataFrame({
            "high": np.random.uniform(100, 110, 20),
            "low": np.random.uniform(90, 100, 20),
            "close": np.random.uniform(95, 105, 20),
        }, index=dates)
        mock_stock_client.get_stock_bars.return_value.df = df

        result = get_atr(mock_stock_client, "AAPL", period=14)
        assert isinstance(result, float)
        assert result > 0
        mock_stock_client.get_stock_bars.assert_called_once()
