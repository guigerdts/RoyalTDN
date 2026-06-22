"""Historical data loader for the CellMesh architecture.

Fetches OHLCV klines from Binance via ccxt and returns them as
pandas DataFrames or dicts for cell consumption.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None  # type: ignore[assignment]


class HistoricalDataLoader:
    """Loads historical OHLCV kline data from Binance.

    Wraps ccxt.binance (with optional testnet support) and falls back
    to direct REST calls when ccxt is unavailable.
    """

    def __init__(self) -> None:
        pass

    async def load_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 200,
        testnet: bool = False,
        api_key: str = "",
        api_secret: str = "",
    ) -> "pd.DataFrame":
        """Fetch OHLCV klines from Binance.

        Args:
            symbol: Trading pair (e.g. ``"BTC/USDT"``).
            interval: Kline interval (``"1m"``, ``"5m"``, ``"1h"``,
                ``"1d"``, etc.).
            limit: Number of candles to fetch (max 1000).
            testnet: If True, use Binance testnet.
            api_key: Optional API key for authenticated requests.
            api_secret: Optional API secret.

        Returns:
            DataFrame with columns: ``timestamp``, ``open``, ``high``,
            ``low``, ``close``, ``volume``. Timestamp is a timezone-aware
            datetime (UTC).

        Raises:
            RuntimeError: If pandas is not installed.
            ConnectionError: If the API is unreachable after retries.
        """
        if pd is None:
            raise RuntimeError(
                "pandas is required for HistoricalDataLoader. "
                "Install it with: pip install pandas"
            )

        bars = await self._fetch_ohlcv(symbol, interval, limit, testnet, api_key, api_secret)
        df = pd.DataFrame(
            bars,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        return df

    async def _fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int,
        testnet: bool,
        api_key: str,
        api_secret: str,
    ) -> list[list]:
        """Execute the OHLCV fetch via ccxt or direct REST.

        Returns:
            Raw OHLCV list as returned by ccxt (list of lists).
        """
        bars: list = []

        try:
            import ccxt  # noqa: F811
        except ImportError:
            logger.info("ccxt not available, falling back to REST API")
            return await self._fetch_rest(symbol, interval, limit, testnet)

        exchange_class = ccxt.binance
        exchange = exchange_class(
            {
                "apiKey": api_key or "",
                "secret": api_secret or "",
            }
        )
        if testnet:
            exchange.set_sandbox_mode(True)

        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
            logger.info(
                "Fetched {} klines for {} ({}) via ccxt",
                len(bars),
                symbol,
                interval,
            )
        except Exception as exc:
            logger.error("ccxt fetch_ohlcv failed: {}", exc)
            raise ConnectionError(f"Failed to fetch OHLCV from ccxt: {exc}") from exc

        return bars

    async def _fetch_rest(
        self,
        symbol: str,
        interval: str,
        limit: int,
        testnet: bool,
    ) -> list[list]:
        """Fallback: fetch klines via direct Binance REST API.

        Args:
            symbol: Trading pair.
            interval: Kline interval.
            limit: Candle count.
            testnet: Use testnet endpoint.

        Returns:
            Raw OHLCV list matching ccxt structure.
        """
        import httpx

        base = (
            "https://testnet.binance.vision"
            if testnet
            else "https://api.binance.com"
        )
        # Binance REST uses interval directly (e.g. "1d", "1h")
        # It also expects the symbol without '/' (e.g. "BTCUSDT")
        clean_symbol = symbol.replace("/", "")
        url = (
            f"{base}/api/v3/klines"
            f"?symbol={clean_symbol}"
            f"&interval={interval}"
            f"&limit={limit}"
        )

        logger.info("Fetching klines via REST: {}", url)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=30)
                resp.raise_for_status()
                raw: list = resp.json()
        except Exception as exc:
            logger.error("REST klines request failed: {}", exc)
            raise ConnectionError(f"Failed to fetch OHLCV from REST: {exc}") from exc

        # Transform Binance REST response to ccxt-like format
        # Binance returns: [open_time, open, high, low, close, volume, ...]
        bars = [
            [
                k[0],  # timestamp (ms)
                float(k[1]),  # open
                float(k[2]),  # high
                float(k[3]),  # low
                float(k[4]),  # close
                float(k[5]),  # volume
            ]
            for k in raw
        ]
        logger.info("Fetched {} klines for {} ({}) via REST", len(bars), symbol, interval)
        return bars

    async def bars_to_dicts(
        self, df: "pd.DataFrame"
    ) -> list[dict[str, Any]]:
        """Convert kline DataFrame to a list of dicts for cell consumption.

        Each dict contains: timestamp, open, high, low, close, volume
        with native Python types.

        Args:
            df: DataFrame with columns ``timestamp``, ``open``, ``high``,
                ``low``, ``close``, ``volume``.

        Returns:
            List of dicts suitable for passing to cell evaluation methods.
        """
        records = df.to_dict(orient="records")
        result: list[dict[str, Any]] = []
        for rec in records:
            row: dict[str, Any] = {}
            for k, v in rec.items():
                if isinstance(v, (pd.Timestamp,)):
                    row[k] = v.to_pydatetime()
                else:
                    row[k] = v
            result.append(row)
        return result
