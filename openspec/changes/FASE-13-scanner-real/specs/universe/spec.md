# Universe — Specification

## Purpose

AssetUniverse must read the `SCANNER_UNIVERSE` environment variable to decide which symbols to load: `etfs` (16 predefined ETFs), `sp500` (up to 500 active equities from NYSE/NASDAQ), or `all` (both deduplicated). The underlying implementation must migrate from raw `requests.get()` to the official `alpaca-py` SDK (`TradingClient.get_all_assets()`).

## Requirements

### REQ-UNIVERSE-CONFIG — Universo configurable por entorno

`AssetUniverse` MUST read `SCANNER_UNIVERSE` (default: `"etfs"`) and return the appropriate symbol set.
- `"etfs"` SHALL return `DEFAULT_ETFS` (16 sector ETFs: XLF, XLE, XLK, XLV, XLI, XLP, XLY, XLB, XLU, XRT, SPY, QQQ, IWM, DIA, GLD, TLT).
- `"sp500"` SHALL return up to 500 active equities from NYSE/NASDAQ via Alpaca API.
- `"all"` SHALL return the deduplicated union of both sets (S&P 500 first, then ETFs).
- An unrecognized value SHALL fall back to `"etfs"` with a logged warning.
- Changing `SCANNER_UNIVERSE` at runtime SHALL invalidate the in-memory cache.

#### Scenario: SCANNER_UNIVERSE=etfs solo carga DEFAULT_ETFS (16 ETFs)

- GIVEN `SCANNER_UNIVERSE` is set to `"etfs"`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN the returned list contains exactly the 16 symbols from `DEFAULT_ETFS`
- AND no API call is made to Alpaca for the equity list

#### Scenario: SCANNER_UNIVERSE=sp500 carga hasta 500 equities activos

- GIVEN `SCANNER_UNIVERSE` is set to `"sp500"`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN the returned list contains up to 500 symbols
- AND every symbol has `asset_class=us_equity`, `status=active`, `exchange=NYSE|NASDAQ`
- AND `tradable=true` for each symbol

#### Scenario: SCANNER_UNIVERSE=all carga ambos deduplicados

- GIVEN `SCANNER_UNIVERSE` is set to `"all"`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN the returned list contains S&P 500 equities first, then any ETFs not already present
- AND duplicates are removed (no symbol appears twice)

#### Scenario: Variable no definida — default etfs

- GIVEN `SCANNER_UNIVERSE` is NOT set in the environment
- WHEN `AssetUniverse` is initialized
- THEN it defaults to `"etfs"`
- AND only the 16 ETF symbols are returned

#### Scenario: Valor inválido — fallback a etfs con warning

- GIVEN `SCANNER_UNIVERSE` is set to `"crypto"`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN a warning is logged: `"SCANNER_UNIVERSE desconocido: crypto — usando etfs"`
- AND the returned list is the 16 ETF symbols

#### Scenario: Transición de etfs a sp500 invalida cache

- GIVEN the cache was populated with `SCANNER_UNIVERSE=etfs`
- WHEN `SCANNER_UNIVERSE` changes to `"sp500"`
- THEN the cache is invalidated
- AND the next call fetches fresh data from Alpaca

### REQ-UNIVERSE-SDK — AssetUniverse usa alpaca-py en vez de requests

`AssetUniverse` MUST use `TradingClient.get_all_assets()` from `alpaca-py` instead of `requests.get()`.
- Filters: `status=active`, `asset_class=us_equity`, `exchange=NYSE|NASDAQ`.
- Results SHALL be cached in-memory with TTL.
- On API error, SHALL return an empty list gracefully (no crash).

#### Scenario: get_all_assets() con filtros correctos

- GIVEN `TradingClient` is initialized with valid credentials
- WHEN `get_all_assets()` is called with `status=active`, `asset_class=us_equity`, `exchange=NYSE|NASDAQ`
- THEN the response is filtered to only active US equities on NYSE or NASDAQ
- AND each returned asset has `tradable=True`

#### Scenario: Error de API en TradingClient — lista vacía, no crash

- GIVEN `TradingClient.get_all_assets()` raises an APIError
- WHEN `AssetUniverse.get_symbols()` is called
- THEN an empty list `[]` is returned
- AND a warning is logged with the error details
- AND the caller receives a valid list (no exception propagates)

#### Scenario: Timeout de red — graceful fallback

- GIVEN `TradingClient.get_all_assets()` times out after 10s
- WHEN `AssetUniverse.get_symbols()` is called
- THEN an empty list `[]` is returned
- AND a warning is logged: `"AssetUniverse: timeout obteniendo S&P 500"`
- AND execution continues without crashing

#### Scenario: Cache funciona y respeta TTL

- GIVEN the sp500 symbol list was fetched 90s ago (TTL=300s)
- WHEN `get_symbols()` is called
- THEN the cached list is returned
- AND no API call is made

- GIVEN the sp500 symbol list was fetched 310s ago (TTL=300s)
- WHEN `get_symbols()` is called
- THEN a new API call is made
- AND the cache is updated

#### Scenario: Respuesta vacía de Alpaca — lista vacía

- GIVEN `get_all_assets()` returns an empty list
- WHEN `AssetUniverse.get_symbols()` is called
- THEN an empty list `[]` is returned
- AND a warning is logged: `"AssetUniverse: 0 símbolos obtenidos de Alpaca"`

#### Scenario: sp500 devuelve menos de 500 símbolos válidos

- GIVEN Alpaca returns 487 active equities (fewer than the 500 limit)
- WHEN `AssetUniverse.get_symbols()` is called with `SCANNER_UNIVERSE=sp500`
- THEN exactly 487 symbols are returned
- AND no truncation or error occurs

#### Scenario: SCANNER_UNIVERSE=all con fallo parcial en sp500

- GIVEN `get_all_assets()` fails with an API error
- WHEN `AssetUniverse.get_symbols()` is called with `SCANNER_UNIVERSE=all`
- THEN the 16 ETF symbols from `DEFAULT_ETFS` are returned as fallback
- AND a warning is logged: `"AssetUniverse: error obteniendo S&P 500, usando solo ETFs"`

#### Scenario: requests.get() no se importa ni se usa

- GIVEN the `universe.py` module is loaded
- WHEN checking imports
- THEN `requests` is NOT imported at module level
- AND `import requests` does not appear anywhere in the file

#### Scenario: TradingClient filtra correctamente por exchange

- GIVEN `get_all_assets()` returns assets from NYSE, NASDAQ, and ARCA
- WHEN the SDK filter is applied with `exchange=NYSE|NASDAQ`
- THEN ARCA assets are excluded from the result
- AND only NYSE and NASDAQ assets remain
