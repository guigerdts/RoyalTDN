"""Historical data loader for the CellMesh architecture.

Fetches OHLCV klines from Binance via ccxt and returns them as
pandas DataFrames or dicts for cell consumption.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Parquet caching
# ---------------------------------------------------------------------------

CACHE_DIR = Path("cache")

# Binance REST base (production only — testnet has limited historical data)
_BINANCE_REST = "https://api.binance.com"

# Mapping from timeframe string to Binance interval
_VALID_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


def _interval_ms(interval: str) -> int:
    """Approximate milliseconds per candle for the given interval."""
    unit = interval[-1]
    val = int(interval[:-1]) if len(interval) > 1 else 1
    if unit == "m":
        return val * 60_000
    if unit == "h":
        return val * 3_600_000
    if unit == "d":
        return val * 86_400_000
    if unit == "w":
        return val * 604_800_000
    if unit == "M":
        return val * 2_592_000_000  # ~30 days
    return 60_000


def _fetch_klines_range(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list]:
    """Fetch OHLCV klines in the given time range with pagination.

    Args:
        symbol: Trading pair without '/' (e.g. ``"BTCUSDT"``).
        interval: Kline interval.
        start_ms: Start time in milliseconds.
        end_ms: End time in milliseconds.

    Returns:
        Raw OHLCV list.
    """
    import httpx

    bars: list[list] = []
    current_start = start_ms

    with httpx.Client() as client:
        while current_start < end_ms:
            url = (
                f"{_BINANCE_REST}/api/v3/klines"
                f"?symbol={symbol}"
                f"&interval={interval}"
                f"&startTime={current_start}"
                f"&limit=1000"
            )
            # Retry loop with exponential backoff for transient errors
            chunk: list | None = None
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    resp = client.get(url, timeout=30)
                    resp.raise_for_status()
                    chunk = resp.json()
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "Binance request failed (attempt {}/3): {}",
                        attempt + 1, exc,
                    )
                    if "abort" in str(exc).lower() or "reset" in str(exc).lower():
                        # Connection abort/ reset — back off and retry
                        backoff = (attempt + 1) * 2.0
                        logger.info("Retrying in {:.0f}s...", backoff)
                        time.sleep(backoff)
                    else:
                        # Non-transient — raise immediately
                        raise ConnectionError(f"Failed to fetch OHLCV: {exc}") from exc

            if last_exc is not None:
                raise ConnectionError(
                    f"Failed to fetch OHLCV after 3 retries: {last_exc}"
                ) from last_exc

            if not chunk:
                break

            for k in chunk:
                ts = int(k[0])
                if ts > end_ms:
                    break
                bars.append([
                    ts,
                    float(k[1]),  # open
                    float(k[2]),  # high
                    float(k[3]),  # low
                    float(k[4]),  # close
                    float(k[5]),  # volume
                ])

            # Advance startTime to the last candle's open time + 1 ms
            last_ts = int(chunk[-1][0])
            current_start = last_ts + 1

            # Rate limit: 50ms between requests (1200/min safe margin)
            time.sleep(0.05)

    return bars


def _build_df(bars: list[list]) -> "pd.DataFrame":
    """Convert raw OHLCV list to a DataFrame with standard columns."""
    if pd is None:
        raise RuntimeError("pandas is required for historical data operations")
    df = pd.DataFrame(
        bars,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df.sort_values("timestamp", inplace=True)
    df.drop_duplicates(subset=["timestamp"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def download_2y_ohlcv(symbol: str, timeframe: str) -> "pd.DataFrame":
    """Download 2 years of OHLCV data from Binance with pagination.

    Args:
        symbol: Trading pair (e.g. ``"BTCUSDT"``). Use no '/' separator.
        timeframe: Kline interval (``"1m"``, ``"15m"``, ``"1d"``, etc.).

    Returns:
        DataFrame with columns ``timestamp``, ``open``, ``high``, ``low``,
        ``close``, ``volume``.

    Raises:
        ValueError: If the timeframe is invalid.
        ConnectionError: If the API is unreachable.
    """
    if timeframe not in _VALID_INTERVALS:
        raise ValueError(
            f"Invalid timeframe '{timeframe}'. Valid options: {sorted(_VALID_INTERVALS)}"
        )

    clean_symbol = symbol.upper().replace("/", "")
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=730)  # ~2 years
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    logger.info(
        "Downloading {} {} from {} to {} ({} candles)",
        clean_symbol, timeframe,
        start_time.date(), now.date(),
        (end_ms - start_ms) // _interval_ms(timeframe),
    )

    bars = _fetch_klines_range(clean_symbol, timeframe, start_ms, end_ms)
    df = _build_df(bars)
    logger.info("Downloaded {} candles for {} ({})", len(df), clean_symbol, timeframe)
    return df


def read_cache(symbol: str, timeframe: str, max_age_hours: int = 24) -> "pd.DataFrame | None":
    """Read cached OHLCV parquet for the given symbol and timeframe.

    Args:
        symbol: Trading pair (e.g. ``"BTCUSDT"``).
        timeframe: Kline interval.
        max_age_hours: Maximum cache age in hours (default 24).

    Returns:
        DataFrame if a valid cache file exists, else None.
    """
    cache_path = CACHE_DIR / f"{symbol.upper()}_{timeframe}.parquet"
    if not cache_path.exists():
        logger.info("Cache miss — {} not found", cache_path)
        return None

    # Check TTL based on file mtime
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    if age > timedelta(hours=max_age_hours):
        logger.info(
            "Cache expired — {} is {:.1f}h old (max {}h)",
            cache_path, age.total_seconds() / 3600, max_age_hours,
        )
        return None

    try:
        df = pd.read_parquet(cache_path)
        logger.info("Cache hit — {} ({} rows)", cache_path, len(df))
        return df
    except Exception as exc:
        logger.warning("Corrupted cache {} — re-downloading: {}", cache_path, exc)
        cache_path.unlink(missing_ok=True)
        return None


def write_cache(symbol: str, timeframe: str, df: "pd.DataFrame") -> None:
    """Write OHLCV DataFrame to parquet cache.

    Args:
        symbol: Trading pair (e.g. ``"BTCUSDT"``).
        timeframe: Kline interval.
        df: DataFrame with standard OHLCV columns.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{symbol.upper()}_{timeframe}.parquet"
    df.to_parquet(cache_path, index=False)
    logger.info("Cache written — {} ({} rows)", cache_path, len(df))
