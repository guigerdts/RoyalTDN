# Delta for scanner-universe

## Context

Existing universe spec at `openspec/specs/fase13-scanner-universo-real/universe.md` defines `REQ-UNIVERSE-CONFIG` for types `etfs`, `sp500`, `all`. The "Valor inválido" scenario used `"crypto"` as the example invalid value. This delta adds `"crypto"` as a valid type.

## ADDED Requirements

### REQ-UNIVERSE-CRYPTO — Crypto universe type

`AssetUniverse` MUST accept `"crypto"` in `VALID_UNIVERSE_TYPES`. When `SCANNER_UNIVERSE=crypto`, `get_symbols()` SHALL return `DEFAULT_CRYPTO` (10 pairs) from its new `_get_default_crypto()` method. `SCANNER_CRYPTO_MIN_VOLUME` env var SHALL be accepted with default `100_000`.

#### Scenario: SCANNER_UNIVERSE=crypto returns 10 crypto pairs

- GIVEN `SCANNER_UNIVERSE` is set to `"crypto"`
- WHEN `AssetUniverse.get_symbols()` is called
- THEN the returned list contains exactly the 10 `DEFAULT_CRYPTO` pairs
- AND the universe type is stored as `"crypto"`

#### Scenario: crypto in VALID_UNIVERSE_TYPES

- GIVEN `AssetUniverse` is initialized with `universe_type="crypto"`
- WHEN the constructor validates the type
- THEN no fallback warning is logged
- AND `self._universe_type == "crypto"`

## MODIFIED Requirements

### REQ-UNIVERSE-CONFIG — Universo configurable por entorno

`AssetUniverse` MUST read `SCANNER_UNIVERSE` (default: `"etfs"`) and return the appropriate symbol set.
- `"etfs"` SHALL return `DEFAULT_ETFS` (16 sector ETFs).
- `"sp500"` SHALL return up to 500 active equities from NYSE/NASDAQ via Alpaca API.
- `"all"` SHALL return the deduplicated union of both sets.
- `"crypto"` SHALL return `DEFAULT_CRYPTO` (10 crypto pairs).
- An unrecognized value SHALL fall back to `"etfs"` with a logged warning.
- Changing `SCANNER_UNIVERSE` at runtime SHALL invalidate the in-memory cache.
(Previously: 4 types, crypto was treated as invalid)

#### Scenario: Valor inválido — fallback a etfs con warning (updated)

- GIVEN `SCANNER_UNIVERSE` is set to an unrecognized value (e.g. `"bonds"`)
- WHEN `AssetUniverse.get_symbols()` is called
- THEN a warning is logged: `"SCANNER_UNIVERSE desconocido: bonds — usando etfs"`
- AND the returned list is the 16 ETF symbols
(Previously used `"crypto"` as the example — now crypto is valid)
