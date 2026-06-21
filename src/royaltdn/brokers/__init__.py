"""RoyalTDN — Broker abstraction layer.

Defines the BaseBroker interface (abstract) and concrete implementations
for each exchange/broker (Alpaca, Binance, etc.).
"""

from .base import BaseBroker, OrderResult
from .alpaca import AlpacaBroker

__all__ = ["BaseBroker", "OrderResult", "AlpacaBroker"]
