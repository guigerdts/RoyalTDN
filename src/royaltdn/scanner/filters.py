"""
RoyalTDN — LiquidityFilter + TokenBucket for the scanner

Fase 13 — Scanner con Universo Real de Activos

TokenBucket: rate limiting for Alpaca API calls (200 req/min).
LiquidityFilter: filters symbols by volume, price, and spread,
with rate limiting and exponential retry on each get_stock_bars().
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from alpaca.data.historical import CryptoHistoricalDataClient
from loguru import logger

from royaltdn.brokers.base import BaseBroker
from royaltdn.scanner.universe import is_crypto_symbol


# ═══════════════════════════════════════════════════════════════════════
# TokenBucket — Rate Limiting
# ═══════════════════════════════════════════════════════════════════════

class TokenBucket:
    """Token bucket for API rate limiting.

    Implements the token bucket algorithm with time-based refill.
    200 initial tokens, refill at 200 tokens/minute (3.33 tokens/s).

    Args:
        max_tokens: Maximum bucket capacity (default 200).
        refill_rate: Refill rate in tokens/second (default 200/60).
    """

    def __init__(self, max_tokens: int = 200, refill_rate: float = 200.0 / 60.0):
        self._max_tokens = max_tokens
        self._refill_rate = refill_rate
        self._tokens = float(max_tokens)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refills tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def consume(self, tokens: int = 1) -> None:
        """Consumes tokens, blocking until enough are available.

        Args:
            tokens: Number of tokens to consume (default 1).
        """
        while True:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            # Wait until at least 1 token is available
            deficit = tokens - self._tokens
            wait = deficit / self._refill_rate
            time.sleep(min(wait, 0.1))  # max 100ms per check

    @property
    def available_tokens(self) -> float:
        """Tokens currently available (after refill)."""
        self._refill()
        return self._tokens


# ═══════════════════════════════════════════════════════════════════════
# LiquidityFilter — Liquidity Filter
# ═══════════════════════════════════════════════════════════════════════

class LiquidityFilter:
    """Filters symbols by liquidity criteria.

    Uses Alpaca data_client.get_stock_bars() to fetch the last 5 daily
    bars for each symbol and checks avg volume and latest close price.
    Integrates TokenBucket for rate limiting and retry with backoff.

    Args:
        min_volume: Minimum avg daily volume (default 100,000).
        min_price: Minimum price (default $5.0).
        max_spread_pct: Maximum spread percentage (default 1.0%) — unused
                        with daily bars, kept for API compatibility.
        token_bucket: TokenBucket instance. If None, creates a default one.
    """

    def __init__(
        self,
        min_volume: int = 100_000,
        min_price: float = 5.0,
        max_spread_pct: float = 1.0,
        token_bucket: Optional[TokenBucket] = None,
        brokers: Optional[Dict[str, BaseBroker]] = None,
    ):
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_spread_pct = max_spread_pct
        self.token_bucket = token_bucket or TokenBucket()
        self.brokers = brokers or {}

    def filter(self, symbols: List[str], data_client: Any,
               crypto_data_client: Optional[Any] = None) -> List[str]:
        """Filters a symbol list by liquidity using daily bars.

        Fetches the last 5 daily bars via get_stock_bars() (stocks)
        or get_crypto_bars() (crypto symbols containing '/'),
        computes average volume and latest close price for each symbol.

        Args:
            symbols: List of symbols to filter.
            data_client: StockHistoricalDataClient from alpaca-py.
            crypto_data_client: Optional CryptoHistoricalDataClient for crypto pairs.

        Returns:
            List of symbols that pass the filter.
        """
        if not symbols:
            return []

        from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame

        passed = []
        from tqdm import tqdm
        import sys

        end = datetime.now()
        start = end - timedelta(days=10)  # 10-day window for 5 trading days

        for symbol in tqdm(
            symbols,
            desc="Filtrando por liquidez",
            unit="sym",
            file=sys.stdout,
            bar_format="{desc}: {n}/{total} — {percentage:.0f}% completado. ~{remaining}",
        ):
            try:
                self.token_bucket.consume(1)

                if is_crypto_symbol(symbol):
                    # Prefer broker-based data when available (FASE 17)
                    crypto_broker = self.brokers.get("crypto")
                    if crypto_broker is not None:
                        df = crypto_broker.get_bars(
                            symbol, timeframe="1d", start=start, end=end,
                        )
                    elif crypto_data_client is not None:
                        request = CryptoBarsRequest(
                            symbol_or_symbols=symbol,
                            timeframe=TimeFrame.Day,
                            start=start,
                            end=end,
                        )
                        bars = crypto_data_client.get_crypto_bars(request)
                        df = bars.df
                    else:
                        logger.debug(
                            "LiquidityFilter: no crypto broker/client — skipping {}", symbol,
                        )
                        continue
                else:
                    request = StockBarsRequest(
                        symbol_or_symbols=symbol,
                        timeframe=TimeFrame.Day,
                        start=start,
                        end=end,
                    )
                    bars = data_client.get_stock_bars(request)
                    df = bars.df

                if df.empty or df["volume"].isna().all():
                    logger.warning(
                        "LiquidityFilter[{}]: empty/all-NaN volume data — skipping",
                        symbol,
                    )
                    continue

                avg_volume = df["volume"].mean()
                last_close = df["close"].iloc[-1]

                if avg_volume >= self.min_volume and last_close >= self.min_price:
                    passed.append(symbol)

            except Exception as e:
                logger.debug(
                    "LiquidityFilter: error for {}: {} — skipping", symbol, e,
                )
                continue

        logger.info(
            "LiquidityFilter: {}/{} symbols passed", len(passed), len(symbols),
        )
        return passed
