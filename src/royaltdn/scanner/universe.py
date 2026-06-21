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
from alpaca.trading.requests import GetAssetsRequest


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

    DEFAULT_CRYPTO = [
        "BTC/USD", "ETH/USD", "LTC/USD", "BCH/USD",
        "LINK/USD", "UNI/USD", "AAVE/USD", "POL/USD",
        "DOGE/USD", "SHIB/USD",
    ]

    DEFAULT_CRYPTO_BINANCE: list[str] = [
        "BTCUSDT", "ETHUSDT", "LTCUSDT", "BCHUSDT",
        "LINKUSDT", "UNIUSDT", "AAVEUSDT", "POLUSDT",
        "DOGEUSDT", "SHIBUSDT",
    ]

    VALID_UNIVERSE_TYPES = ("etfs", "sp500", "all", "crypto")

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        use_paper: bool = True,
        universe_type: str = "all",
        cache_ttl: int = 300,
        broker_type: str = "alpaca",
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.use_paper = use_paper
        self._broker_type = broker_type

        # Validate universe_type
        if universe_type not in self.VALID_UNIVERSE_TYPES:
            logger.warning(
                "AssetUniverse: SCANNER_UNIVERSE='{}' invalid — falling back to 'all'",
                universe_type,
            )
            universe_type = "all"
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
        elif self._universe_type == "crypto":
            result = self._get_default_crypto()
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

    @universe_type.setter
    def universe_type(self, value: str) -> None:
        if value not in self.VALID_UNIVERSE_TYPES:
            raise ValueError(
                f"Invalid universe type: {value!r}. Valid: {self.VALID_UNIVERSE_TYPES}"
            )
        self._universe_type = value
        self.invalidate_cache()

    # ── Private methods ───────────────────────────────────────────────

    def _get_etfs(self) -> List[str]:
        """Returns a copy of DEFAULT_ETFS. No API call needed."""
        return self.DEFAULT_ETFS.copy()

    def _get_default_crypto(self) -> List[str]:
        """Returns a copy of the broker-specific crypto constant. No API call needed."""
        if self._broker_type == "binance":
            return self.DEFAULT_CRYPTO_BINANCE.copy()
        return self.DEFAULT_CRYPTO.copy()

    def _get_sp500_via_sdk(self) -> List[str]:
        """Fetches S&P 500 assets via TradingClient.get_all_assets().

        Filters: status=active, asset_class=us_equity, exchange=NYSE|NASDAQ,
        tradable=True. Returns up to 500 symbols.

        Returns:
            List of symbols, or [] if the API fails.
        """
        try:
            req = GetAssetsRequest(
                asset_class=AssetClass.US_EQUITY,
                asset_status=AssetStatus.ACTIVE,
            )
            assets = self._trading_client.get_all_assets(req)

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


# ── Crypto symbol helpers ──────────────────────────────────────────────

_CRYPTO_SYMBOLS: frozenset = frozenset(
    s.replace("/", "").upper() for s in AssetUniverse.DEFAULT_CRYPTO
) | frozenset(AssetUniverse.DEFAULT_CRYPTO_BINANCE)


def is_crypto_symbol(symbol: str) -> bool:
    """Return True if symbol is a known crypto pair (with or without slash).

    Checks for a ``"/"`` in the symbol AND membership in a frozenset built
    from the union of ``DEFAULT_CRYPTO`` (Alpaca) and ``DEFAULT_CRYPTO_BINANCE``
    — so both ``"BTC/USD"`` and ``"BTCUSDT"`` are recognised as crypto.
    """
    return "/" in symbol or symbol.upper() in _CRYPTO_SYMBOLS
