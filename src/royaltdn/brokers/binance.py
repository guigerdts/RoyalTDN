"""RoyalTDN — BinanceBroker concrete implementation.

Connects to Binance Spot Testnet (or Production) using pure requests +
HMAC-SHA-256 signature.  No external SDK dependency.

Mapping:  https://testnet.binance.vision  (testnet)
          https://api.binance.com        (production)
"""

import hashlib
import hmac
import time
from datetime import datetime
from typing import List, Optional

import pandas as pd
import requests

from royaltdn.brokers.base import BaseBroker, OrderResult


class BinanceBroker(BaseBroker):
    """Binance Spot broker (Testnet / Production).

    Signs every authenticated request with an HMAC-SHA-256 signature.
    Market data (klines) and trading (account, orders) are available via
    the same auth mechanism.

    Args:
        api_key: Binance API key (``X-MBX-APIKEY`` header).
        secret_key: Binance secret key (used for HMAC signing).
        testnet: Whether to use the Testnet environment (default ``True``).
    """

    BASE_URL_SANDBOX = "https://testnet.binance.vision"
    BASE_URL_PROD = "https://api.binance.com"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        testnet: bool = True,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._base_url = self.BASE_URL_SANDBOX if testnet else self.BASE_URL_PROD
        self._broker_name = "binance"

    # ── HMAC signing ─────────────────────────────────────────────────────

    def _sign(self, params: dict) -> str:
        """Generate HMAC-SHA-256 signature for *params*.

        Sorts keys alphabetically before signing (required by Binance).
        """
        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(
            self._secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _signed_request(self, method: str, path: str, params: dict = None) -> dict:
        """Make an authenticated request to the Binance REST API.

        Injects ``timestamp`` and ``signature`` into *params*, sets the
        ``X-MBX-APIKEY`` header, and dispatches GET / POST.

        Raises ``requests.HTTPError`` on non-2xx responses.
        """
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = self._sign(params)
        headers = {"X-MBX-APIKEY": self._api_key}
        url = f"{self._base_url}{path}"

        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=10)
        else:
            resp = requests.post(url, headers=headers, params=params, timeout=10)

        resp.raise_for_status()
        return resp.json()

    # ── Account ──────────────────────────────────────────────────────────

    def get_account_balance(self) -> float:
        """Return free USDT balance from the Binance account."""
        data = self._signed_request("GET", "/api/v3/account")
        for balance in data.get("balances", []):
            if balance["asset"] == "USDT":
                return float(balance["free"])
        return 0.0

    # ── Market data ──────────────────────────────────────────────────────

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV klines from Binance as a DataFrame.

        Columns: timestamp (index), open, high, low, close, volume.
        Uses the GET /api/v3/klines endpoint.
        """
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "1Hour": "1h", "4h": "4h",
            "1d": "1d", "1Day": "1d", "1W": "1w",
        }
        interval = interval_map.get(timeframe, "1h")

        params = {
            "symbol": self.normalize_symbol(symbol),
            "interval": interval,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
            "limit": 500,
        }

        data = self._signed_request("GET", "/api/v3/klines", params)

        rows = []
        for k in data:
            rows.append({
                "timestamp": datetime.fromtimestamp(k[0] / 1000),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df.set_index("timestamp", inplace=True)
        return df

    # ── Orders ───────────────────────────────────────────────────────────

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
    ) -> Optional[OrderResult]:
        """Submit a MARKET order to Binance.

        Returns:
            OrderResult on success, ``None`` on HTTP error.
        """
        params = {
            "symbol": self.normalize_symbol(symbol),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty,
        }

        try:
            data = self._signed_request("POST", "/api/v3/order", params)
            fill_price = 0.0
            if data.get("fills"):
                fill_price = float(data["fills"][0].get("price", 0))
            return OrderResult(
                order_id=str(data.get("orderId", "")),
                symbol=symbol,
                side=side,
                qty=qty,
                price=fill_price,
                status="FILLED" if data.get("status") == "FILLED"
                else data.get("status", "NEW"),
                broker=self._broker_name,
            )
        except requests.HTTPError:
            return None

    # ── Positions ────────────────────────────────────────────────────────

    def get_open_positions(self) -> List[dict]:
        """Return non-zero asset balances as position dicts.

        Each dict contains: symbol, qty (free + locked), free, locked, broker.
        """
        data = self._signed_request("GET", "/api/v3/account")
        positions = []
        for bal in data.get("balances", []):
            free = float(bal["free"])
            locked = float(bal["locked"])
            if free > 0 or locked > 0:
                positions.append({
                    "symbol": f"{bal['asset']}/USDT",
                    "qty": free + locked,
                    "free": free,
                    "locked": locked,
                    "broker": self._broker_name,
                })
        return positions

    def close_position(self, symbol: str) -> bool:
        """Sell the full position for *symbol*.

        Looks up the current balance for the asset portion of *symbol* and
        submits a market sell order.  Returns ``True`` if the order was
        accepted.
        """
        positions = self.get_open_positions()
        target = self.normalize_symbol(symbol).replace("USDT", "")
        for pos in positions:
            asset = pos["symbol"].split("/")[0]
            if asset == target and pos["qty"] > 0:
                result = self.submit_order(symbol, "sell", pos["qty"])
                return result is not None
        return False

    # ── Market status ────────────────────────────────────────────────────

    def is_market_open(self, symbol: str) -> bool:
        """Binance crypto spot markets operate 24/7."""
        return True

    # ── Symbol normalisation ─────────────────────────────────────────────

    def normalize_symbol(self, symbol: str) -> str:
        """Convert canonical symbol to Binance's native format.

        - Strips ``/``
        - Maps ``USD`` → ``USDT`` (except when already ``USDT``)

        Examples:
            ``"BTC/USD"`` → ``"BTCUSDT"``
            ``"BTC/USDT"`` → ``"BTCUSDT"``
            ``"ETH/USD"`` → ``"ETHUSDT"``
            ``"BTCUSDT"`` → ``"BTCUSDT"``
        """
        cleaned = symbol.replace("/", "")
        if cleaned.endswith("USD") and not cleaned.endswith("USDT"):
            cleaned = cleaned + "T"
        return cleaned.upper()
