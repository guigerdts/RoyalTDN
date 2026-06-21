"""RoyalTDN — Base broker interface (abstract).

Defines the contract that every broker implementation must satisfy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import pandas as pd


@dataclass
class OrderResult:
    """Standardised order result returned by every broker."""

    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    status: str
    broker: str


class BaseBroker(ABC):
    """Abstract broker interface.

    Every concrete broker (Alpaca, Binance, …) must implement all seven
    methods below.  This lets the Orchestrator and Scanner treat all
    brokers uniformly.
    """

    @abstractmethod
    def get_account_balance(self) -> float:
        """Return the current cash/equity balance for this account."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV bars for *symbol* as a DataFrame.

        Columns (at minimum): timestamp, open, high, low, close, volume.
        """

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
    ) -> Optional[OrderResult]:
        """Submit a market order.

        Args:
            symbol: Trading symbol (e.g. "SPY", "BTC/USD", "BTCUSDT").
            side: "buy" or "sell".
            qty: Number of shares / units.

        Returns:
            OrderResult on success, None on failure.
        """

    @abstractmethod
    def get_open_positions(self) -> List[dict]:
        """Return list of open positions.

        Each dict includes at least: symbol, qty, entry, current, pnl, broker.
        """

    @abstractmethod
    def close_position(self, symbol: str) -> bool:
        """Close an open position by symbol.  Returns True on success."""

    @abstractmethod
    def is_market_open(self, symbol: str) -> bool:
        """Check whether the market for *symbol* is currently open.

        Crypto markets return True 24/7.
        """

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """Convert a canonical symbol to the broker's native format.

        For Alpaca: identity (SPY → SPY, BTC/USD → BTC/USD).
        For Binance: strip "/" and map USD → USDT (BTC/USD → BTCUSDT).
        """
