"""
RoyalTDN — AssetUniverse: asset universe for the scanner

Fase 13 — Scanner con Universo Real de Activos

Migrated from raw requests.get() to alpaca-py TradingClient SDK.
Respects SCANNER_UNIVERSE (etfs/sp500/all). In-memory cache with TTL.
"""

import time
from typing import Dict, List, Optional, Tuple

from loguru import logger
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus


class AssetUniverse:
    """Manages the universe of scannable symbols.

    Retrieves assets from Alpaca via TradingClient.get_all_assets()
    with exchange, status, and asset_class filters. Caches results
    with configurable TTL to minimize API calls.

    Args:
        api_key: Alpaca API key.
        secret_key: Alpaca secret key.
        use_paper: Use paper trading (True) or live (False).
        universe_type: Universe type: "etfs" | "sp500" | "all".
        cache_ttl: Cache TTL in seconds (default 300 = 5 min).
    """

    DEFAULT_ETFS = [
        "SPY", "QQQ", "IWM", "DIA",
        "XLF", "XLE", "XLK", "XLV",
        "XLI", "XLP", "XLY", "XLB",
        "XLU", "XRT", "GLD", "TLT",
    ]

    VALID_UNIVERSE_TYPES = ("etfs", "sp500", "all")

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        use_paper: bool = True,
        universe_type: str = "etfs",
        cache_ttl: int = 300,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.use_paper = use_paper

        # Validate universe_type
        if universe_type not in self.VALID_UNIVERSE_TYPES:
            logger.warning(
                "AssetUniverse: SCANNER_UNIVERSE='{}' invalid — falling back to 'etfs'",
                universe_type,
            )
            universe_type = "etfs"
        self._universe_type = universe_type

        self._cache_ttl = cache_ttl
        # Cache: {key: (timestamp: float, data: List[str])}
        self._cache: Dict[str, Tuple[float, List[str]]] = {}

        # Initialize alpaca-py TradingClient
        self._trading_client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=use_paper,
        )

        logger.info(
            "AssetUniverse initialized — universe_type={} cache_ttl={}s",
            universe_type, cache_ttl,
        )

    # ── Public API ────────────────────────────────────────────────────

    def get_symbols(self) -> List[str]:
        """Returns symbols according to universe_type, with cache and TTL.

        Returns:
            List of symbol strings based on the configured universe type.
        """
        cache_key = f"universe:{self._universe_type}"
        now = time.time()

        # Cache hit?
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if (now - ts) < self._cache_ttl:
                logger.debug("AssetUniverse: cache hit for '{}'", self._universe_type)
                return data

        # Fresh fetch based on universe_type
        if self._universe_type == "etfs":
            result = self._get_etfs()
        elif self._universe_type == "sp500":
            result = self._get_sp500_via_sdk()
        else:  # "all"
            result = self._get_all_deduplicated()

        # Cache result (even if empty — prevents thundering herd)
        self._cache[cache_key] = (now, result)
        logger.info(
            "AssetUniverse: {} symbols loaded for '{}'",
            len(result), self._universe_type,
        )
        return result

    def invalidate_cache(self) -> None:
        """Invalidates the entire cache. Useful if SCANNER_UNIVERSE changes at runtime."""
        self._cache.clear()
        logger.info("AssetUniverse: cache invalidated")

    @property
    def universe_type(self) -> str:
        """Currently active universe type."""
        return self._universe_type

    # ── Private methods ───────────────────────────────────────────────

    def _get_etfs(self) -> List[str]:
        """Returns a copy of DEFAULT_ETFS. No API call needed."""
        return self.DEFAULT_ETFS.copy()

    def _get_sp500_via_sdk(self) -> List[str]:
        """Fetches S&P 500 assets via TradingClient.get_all_assets().

        Filters: status=active, asset_class=us_equity, exchange=NYSE|NASDAQ,
        tradable=True. Returns up to 500 symbols.

        Returns:
            List of symbols, or [] if the API fails.
        """
        try:
            assets = self._trading_client.get_all_assets(
                status=AssetStatus.ACTIVE,
                asset_class=AssetClass.US_EQUITY,
            )

            symbols = [
                a.symbol
                for a in assets
                if a.tradable
                and a.exchange in ("NYSE", "NASDAQ")
            ][:500]

            logger.info(
                "AssetUniverse: {} S&P 500 symbols fetched via SDK",
                len(symbols),
            )
            return symbols

        except Exception as e:
            logger.warning("AssetUniverse: error fetching S&P 500 via SDK: {}", e)

            # Fallback: use stale cache if available
            cache_key = f"universe:{self._universe_type}"
            if cache_key in self._cache:
                stale_data = self._cache[cache_key][1]
                logger.warning(
                    "AssetUniverse: using stale cache ({} symbols) as fallback",
                    len(stale_data),
                )
                return stale_data

            return []

    def _get_all_deduplicated(self) -> List[str]:
        """Combines S&P 500 + ETFs deduplicated.

        S&P 500 first, then non-duplicate ETFs.
        If S&P 500 fails, returns only ETFs.

        Returns:
            Deduplicated list of symbols.
        """
        sp500 = self._get_sp500_via_sdk()
        etfs = self._get_etfs()

        seen = set(sp500)
        result = sp500.copy()
        for sym in etfs:
            if sym not in seen:
                seen.add(sym)
                result.append(sym)

        return result
