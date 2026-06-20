# Cache — Specification

## Purpose

Add in-memory caching for AssetUniverse symbol lists with configurable TTL (default 300s). Add batch data downloading for `_get_symbol_data` — group symbols in batches of up to 100 for `get_stock_bars` calls, reducing ~400 individual API calls to ~4 batch calls.

## Requirements

### REQ-CACHE — Asset cache in-memory con TTL configurable

`AssetUniverse` MUST cache symbol lists in-memory with a TTL (default 300s).
- Cache key format: `f"{universe_type}:{etf_list_hash}"`.
- Cache entry: `(timestamp, data)`.
- On cache hit within TTL, return cached data without API call.
- On cache miss or TTL expiry, fetch from API and update cache.
- Changing `SCANNER_UNIVERSE` MUST invalidate the current cache entry.
- A cache miss with an API error SHALL return an empty list without caching.

#### Scenario: Cache de activos con TTL default 300s

- GIVEN the universe was fetched at T=0
- WHEN `get_symbols()` is called at T=120
- THEN the cached data is returned
- AND no API call is made

#### Scenario: Cache hit retorna datos sin llamar API

- GIVEN the cache contains valid data for `universe_type="sp500"`
- WHEN `get_symbols()` is called with the same universe type
- THEN the cached list is returned immediately
- AND `TradingClient.get_all_assets()` is NOT called

#### Scenario: Cache miss — fetch de API + store

- GIVEN the cache is empty
- WHEN `get_symbols()` is called
- THEN `TradingClient.get_all_assets()` is called
- AND the result is stored in the cache with the current timestamp

#### Scenario: TTL expirado — refetch en próximo acceso

- GIVEN the cache was populated 310s ago (TTL=300s)
- WHEN `get_symbols()` is called
- THEN a new API call is made
- AND the cache is updated with the fresh data and new timestamp

#### Scenario: Invalidez al cambiar SCANNER_UNIVERSE

- GIVEN the cache has data for `universe_type="etfs"`
- WHEN `SCANNER_UNIVERSE` changes to `"sp500"`
- THEN the old cache entry is discarded
- AND `get_symbols()` fetches fresh data for the new universe type

#### Scenario: Cache vacío — primer fetch funciona

- GIVEN the cache is empty and API is reachable
- WHEN `get_symbols()` is called for the first time
- THEN the API returns a valid symbol list
- AND the cache stores `(timestamp, data)`

### REQ-BATCH-DATA — get_stock_bars agrupado en batches de 100

`Scanner._get_symbol_data()` MUST be replaced by a batch-aware method that groups symbols into batches of up to 100 for `get_stock_bars`.
- Each batch SHALL use a single `get_stock_bars(request)` call with `symbol_or_symbols=list_of_symbols`.
- Maximum batch size: 100 symbols per call (Alpaca limit).
- Symbols within a batch SHALL share the same `timeframe=TimeFrame.Day`, `limit=60`.
- A partial batch (e.g., 37 symbols) SHALL be sent as-is.
- An error in one batch SHALL NOT affect other batches.

#### Scenario: get_stock_bars con batches de 100 símbolos

- GIVEN 250 symbols passed the liquidity filter
- WHEN batch download is triggered
- THEN 3 API calls are made: 100, 100, and 50 symbols each
- AND each call uses `get_stock_bars(symbol_or_symbols=batch, timeframe=Day, limit=60)`

#### Scenario: Reducción de ~400 calls a ~4 calls para 400 símbolos

- GIVEN exactly 400 symbols need data
- WHEN the batch method is used
- THEN exactly 4 API calls are made (4 x 100 symbols)
- AND no individual `_get_symbol_data(symbol)` calls are made

#### Scenario: Batch parcial (<100 símbolos) se envía completo

- GIVEN 37 symbols passed the liquidity filter
- WHEN batch download is triggered
- THEN a single API call is made with all 37 symbols
- AND the call completes normally

#### Scenario: Error en un batch — no afecta otros batches

- GIVEN 3 batches of 100 symbols each, and the 2nd batch fails with a timeout
- WHEN batch processing completes
- THEN the 1st and 3rd batches have their data available
- AND the 2nd batch's symbols are skipped with a logged warning
- AND the scan continues for the remaining batches

#### Scenario: Cache key incluye el tipo de universe

- GIVEN `AssetUniverse` has cached `etfs` data under key `"etfs:abc123"`
- WHEN `get_symbols()` is called with `SCANNER_UNIVERSE=sp500`
- THEN a DIFFERENT cache key `"sp500:abc123"` is used
- AND the sp500 data is fetched fresh from API

#### Scenario: Refetch después de TTL expirado actualiza timestamp

- GIVEN cache was populated at T=0 with TTL=300s
- WHEN `get_symbols()` is called at T=310 (cache miss triggers refetch)
- THEN the new cache entry has timestamp ≈ T=310
- AND subsequent calls before T=610 hit the cache
