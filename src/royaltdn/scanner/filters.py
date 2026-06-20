"""
RoyalTDN — LiquidityFilter + TokenBucket for the scanner

Fase 13 — Scanner con Universo Real de Activos

TokenBucket: rate limiting for Alpaca API calls (200 req/min).
LiquidityFilter: filters symbols by volume, price, and spread,
with rate limiting and exponential retry on each get_latest_bar().
"""

import time
from typing import List, Optional, Any

from loguru import logger


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

    Uses Alpaca data_client.get_latest_bar() to get the latest
    bar for each symbol and checks volume, price, and spread.
    Integrates TokenBucket for rate limiting and retry with backoff.

    Args:
        min_volume: Minimum volume (default 500,000).
        min_price: Minimum price (default $5.0).
        max_spread_pct: Maximum spread percentage (default 0.5%).
        token_bucket: TokenBucket instance. If None, creates a default one.
    """

    def __init__(
        self,
        min_volume: int = 500_000,
        min_price: float = 5.0,
        max_spread_pct: float = 0.5,
        token_bucket: Optional[TokenBucket] = None,
    ):
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_spread_pct = max_spread_pct
        self.token_bucket = token_bucket or TokenBucket()

    def filter(self, symbols: List[str], data_client: Any) -> List[str]:
        """Filters a symbol list by liquidity with rate limiting.

        Args:
            symbols: List of symbols to filter.
            data_client: StockHistoricalDataClient from alpaca-py.

        Returns:
            List of symbols that pass the filter.
        """
        if not symbols:
            return []

        passed = []
        from tqdm import tqdm
        import sys

        for symbol in tqdm(
            symbols,
            desc="Filtrando por liquidez",
            unit="sym",
            file=sys.stdout,
            bar_format="{desc}: {n}/{total} — {percentage:.0f}% completado. ~{remaining}",
        ):
            bar = self._call_with_retry(symbol, data_client)
            if bar is None:
                continue

            # Check bar has data
            volume = getattr(bar, "volume", None)
            close = getattr(bar, "close", None)

            # Volume filter
            if volume is None or volume < self.min_volume:
                continue

            # Price filter
            if close is None or close < self.min_price:
                continue

            # Spread filter (if available)
            bid = getattr(bar, "bid_price", None)
            ask = getattr(bar, "ask_price", None)
            if bid is not None and ask is not None and bid > 0 and ask > 0:
                spread_pct = ((ask - bid) / ((ask + bid) / 2)) * 100
                if spread_pct > self.max_spread_pct:
                    continue

            passed.append(symbol)

        logger.info("LiquidityFilter: {}/{} symbols passed", len(passed), len(symbols))
        return passed

    def _call_with_retry(self, symbol: str, data_client: Any) -> Optional[Any]:
        """Wrapper with retry for get_latest_bar.

        Implements exponential backoff: 1s -> 2s -> 4s -> 8s.
        Maximum 5 attempts (initial + 4 retries).
        HTTP 401/403 abort immediately (no retry).
        HTTP 429/503/timeout retry with backoff.

        Args:
            symbol: Symbol to query.
            data_client: StockHistoricalDataClient from alpaca-py.

        Returns:
            Bar object on success, None if all 5 attempts fail.
        """
        backoff = [1, 2, 4, 8]  # seconds between retries

        for attempt in range(5):  # initial + 4 retries
            try:
                # Consume token BEFORE each attempt
                self.token_bucket.consume(1)
                return data_client.get_latest_bar(symbol)

            except Exception as e:
                err_str = str(e).lower()

                # Auth errors — abort immediately
                if "401" in err_str or "403" in err_str:
                    logger.error(
                        "LiquidityFilter: auth error ({}) for {} — aborting",
                        e, symbol,
                    )
                    raise  # propagate to caller

                # Rate limit or server error — retry with backoff
                if "429" in err_str or "503" in err_str or "timeout" in err_str:
                    if attempt < 4:
                        delay = backoff[attempt]
                        logger.debug(
                            "LiquidityFilter: error {} for {} — retry {}/5 in {}s",
                            e, symbol, attempt + 1, delay,
                        )
                        time.sleep(delay)
                        continue

                    logger.warning(
                        "LiquidityFilter: max retries (5) reached for {}",
                        symbol,
                    )
                    return None

                # Unknown error — skip silently
                logger.debug(
                    "LiquidityFilter: unexpected error for {}: {} — skipping",
                    symbol, e,
                )
                return None

        return None
