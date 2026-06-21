"""RoyalTDN — AlpacaBroker concrete implementation.

Wraps the official alpaca-py SDK behind the BaseBroker interface.
Used for both stock/ETF (Paper/Live) and crypto trading through Alpaca.
"""

from datetime import datetime
from typing import List, Optional

import pandas as pd

from royaltdn.brokers.base import BaseBroker, OrderResult


class AlpacaBroker(BaseBroker):
    """Broker implementation for Alpaca Markets (Paper / Live).

    Uses TradingClient for orders/account/positions, StockHistoricalDataClient
    for stock bars and CryptoHistoricalDataClient for crypto bars.

    Args:
        api_key: Alpaca API key.
        secret_key: Alpaca secret key.
        paper: Whether to use the paper-trading environment (default True).
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
    ) -> None:
        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import (
            StockHistoricalDataClient,
            CryptoHistoricalDataClient,
        )

        self._trading = TradingClient(api_key, secret_key, paper=paper)
        self._stock_data = StockHistoricalDataClient(api_key, secret_key)
        self._crypto_data = CryptoHistoricalDataClient(api_key, secret_key)
        self._broker_name = "alpaca"

    # ── Account ────────────────────────────────────────────────────────

    def get_account_balance(self) -> float:
        """Return current account equity (cash + positions)."""
        account = self._trading.get_account()
        return float(account.equity)

    # ── Market data ────────────────────────────────────────────────────

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV bars via the appropriate data client.

        Crypto symbols (containing "/") use CryptoHistoricalDataClient.
        All other symbols use StockHistoricalDataClient.
        """
        from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_units = {
            "min": TimeFrameUnit.Minute,
            "h": TimeFrameUnit.Hour,
            "d": TimeFrameUnit.Day,
            "day": TimeFrameUnit.Day,
        }
        # Parse timeframe string like "1h", "15min", "1d"
        import re

        match = re.match(r"(\d+)?\s*(min|h|d|day)", timeframe.lower())
        if match:
            amount = int(match.group(1)) if match.group(1) else 1
            unit = tf_units.get(match.group(2), TimeFrameUnit.Day)
            tf = TimeFrame(amount=amount, unit=unit)
        else:
            tf = TimeFrame.Day

        if "/" in symbol:
            request = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
            )
            response = self._crypto_data.get_crypto_bars(request)
        else:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
                feed="iex",
            )
            response = self._stock_data.get_stock_bars(request)

        df = response.df
        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel(0)
        return df

    # ── Orders ─────────────────────────────────────────────────────────

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
    ) -> Optional[OrderResult]:
        """Submit a day market order via Alpaca.

        Returns:
            OrderResult on success, None on failure.
        """
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        try:
            order = self._trading.submit_order(
                MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
            )
            return OrderResult(
                order_id=order.id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=float(order.filled_avg_price) if order.filled_avg_price else 0.0,
                status=order.status,
                broker=self._broker_name,
            )
        except Exception:
            return None

    # ── Positions ──────────────────────────────────────────────────────

    def get_open_positions(self) -> List[dict]:
        """Return all open positions from Alpaca."""
        positions = self._trading.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "entry": float(p.avg_entry_price),
                "current": float(p.current_price),
                "pnl": float(p.unrealized_pl),
                "broker": self._broker_name,
            }
            for p in positions
        ]

    def close_position(self, symbol: str) -> bool:
        """Close an open position.  Returns True on success."""
        try:
            self._trading.close_position(symbol)
            return True
        except Exception:
            return False

    # ── Market status ──────────────────────────────────────────────────

    def is_market_open(self, symbol: str) -> bool:
        """Check market hours.

        Crypto (symbol with "/") is always open.
        Stocks/ETFs use the Alpaca Clock API.
        """
        if "/" in symbol:
            return True
        clock = self._trading.get_clock()
        return clock.is_open

    # ── Symbol normalisation ───────────────────────────────────────────

    def normalize_symbol(self, symbol: str) -> str:
        """Alpaca uses the same symbol format — identity."""
        return symbol
