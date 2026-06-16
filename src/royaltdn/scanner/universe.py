"""
RoyalTDN — AssetUniverse: universo de activos para el scanner

Fase 5.6 — Universo y Filtros

Provee:
- S&P 500 símbolos (vía Alpaca Assets API)
- ETFs sectoriales por defecto
- Combinación deduplicada
"""

import logging
import requests
from typing import List, Optional

logger = logging.getLogger("royaltdn.scanner.universe")


class AssetUniverse:
    """Gestiona el universo de símbolos escaneables.

    Obtiene símbolos de S&P 500 desde Alpaca Assets API y combina
    con lista de ETFs sectoriales.
    """

    DEFAULT_ETFS = [
        "XLF", "XLE", "XLK", "XLV", "XLI",
        "XLP", "XLY", "XLB", "XLU", "XRT",
        "SPY", "QQQ", "IWM", "DIA", "GLD", "TLT",
    ]

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        use_paper: bool = True,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.use_paper = use_paper
        self._base_url = "https://paper-api.alpaca.markets" if use_paper else "https://api.alpaca.markets"
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }
        self._sp500_cache: Optional[List[str]] = None
        self._etf_cache: Optional[List[str]] = None
        self._all_cache: Optional[List[str]] = None

    def get_sp500_symbols(self) -> List[str]:
        """Obtiene símbolos del S&P 500 desde Alpaca Assets API.

        Filtra: status=active, exchange=NYSE|NASDAQ, tradable=true.
        Límite: 500 resultados.
        Cachea el resultado.
        """
        if self._sp500_cache is not None:
            return self._sp500_cache

        url = f"{self._base_url}/v2/assets"
        params = {
            "status": "active",
            "exchange": "NYSE,NASDAQ",
            "tradable": "true",
        }

        try:
            response = requests.get(url, headers=self._headers, params=params, timeout=10)
            response.raise_for_status()
            assets = response.json()

            # Filtrar solo acciones (no ETFs, etc.) y tomar hasta 500
            symbols = [
                asset["symbol"]
                for asset in assets
                if asset.get("asset_class") == "us_equity"
            ][:500]

            self._sp500_cache = symbols
            logger.info("AssetUniverse: %d símbolos S&P 500 obtenidos", len(symbols))
            return symbols

        except Exception as e:
            logger.warning("AssetUniverse: error obteniendo S&P 500: %s", e)
            self._sp500_cache = []
            return []

    def get_etf_symbols(self, etf_list: Optional[List[str]] = None) -> List[str]:
        """Retorna lista de ETFs sectoriales.

        Args:
            etf_list: Lista personalizada. Lista de símbolos ETF. Si None, usa DEFAULT_ETFS.

        Returns:
            Lista de símbolos ETF (cacheada).
        """
        if etf_list is not None:
            return etf_list

        if self._etf_cache is not None:
            return self._etf_cache

        self._etf_cache = self.DEFAULT_ETFS.copy()
        logger.info("AssetUniverse: %d ETFs por defecto", len(self._etf_cache))
        return self._etf_cache

    def get_all_symbols(self) -> List[str]:
        """Combina S&P 500 + ETFs (deduplicado).

        Returns:
            Lista única de símbolos (cacheada).
        """
        if self._all_cache is not None:
            return self._all_cache

        sp500 = self.get_sp500_symbols()
        etfs = self.get_etf_symbols()

        # Deduplicar manteniendo orden: S&P 500 primero, luego ETFs
        seen = set()
        all_symbols = []
        for sym in sp500 + etfs:
            if sym not in seen:
                seen.add(sym)
                all_symbols.append(sym)

        self._all_cache = all_symbols
        logger.info("AssetUniverse: %d símbolos totales (S&P 500 + ETFs)", len(all_symbols))
        return all_symbols
