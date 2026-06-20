# FASE 13 — Scanner con Universo Real de Activos

## Purpose

Professionalize the scanner for production: make `SCANNER_UNIVERSE` operational, add rate limiting with exponential backoff, fix the menu display bug, convert `Scanner.scan()` to async, migrate `AssetUniverse` to alpaca-py SDK, add asset cache with TTL, batch data downloads, declare `tqdm` dependency, and add post-scan metrics in the menu.

## Domains

| Domain | File | Requirements |
|--------|------|-------------|
| [Universe](./universe.md) | `src/royaltdn/scanner/universe.py` | REQ-UNIVERSE-CONFIG, REQ-UNIVERSE-SDK |
| [Rate Limiting](./rate-limiting.md) | `src/royaltdn/scanner/filters.py`, `src/royaltdn/scanner/scanner.py` | REQ-RATE-LIMIT, REQ-RETRY |
| [Cache](./cache.md) | `src/royaltdn/scanner/universe.py`, `src/royaltdn/scanner/scanner.py` | REQ-CACHE, REQ-BATCH-DATA |
| [Async Scan](./async.md) | `src/royaltdn/orchestrator.py` | REQ-ASYNC-SCAN |
| [Display](./display.md) | `src/royaltdn/frontend/menu/app.py` | REQ-DISPLAY-FIX |
| [Integration](./integration.md) | `src/royaltdn/orchestrator.py`, `pyproject.toml` | REQ-AUTO-SCAN, REQ-MANUAL-SCAN, REQ-METRICS-PANEL, REQ-TQDM-DEP |

## Architecture Summary

```
┌─────────────────────────────┐
│      Orchestrator           │
│  ┌─────────────────────┐    │
│  │ _run_scanner()      │    │  loop.run_in_executor() + timeout
│  │ _run_legacy_loop()  │    │  auto-scan every INTERVAL_MINUTES
│  │ _check_signals()    │    │  manual scan via IPC signal
│  └──────────┬──────────┘    │
└─────────────┼───────────────┘
              │
┌─────────────▼───────────────┐
│         Scanner              │
│  ┌─────────────────────┐    │
│  │ _batch_get_symbol_  │    │  get_stock_bars in batches of 100
│  │        data()       │    │
│  └─────────────────────┘    │
│  ┌─────────────────────┐    │
│  │  LiquidityFilter    │    │  TokenBucket rate limiter
│  │  _call_with_retry() │    │  exponential backoff retry
│  └─────────────────────┘    │
│  ┌─────────────────────┐    │
│  │  AssetUniverse      │    │  SCANNER_UNIVERSE etfs/sp500/all
│  │  get_symbols()      │    │  alpaca-py SDK, cache with TTL
│  └─────────────────────┘    │
└─────────────────────────────┘
```

## Env Config

| Variable | Default | Values | Description |
|----------|---------|--------|-------------|
| `SCANNER_UNIVERSE` | `etfs` | `etfs`, `sp500`, `all` | What assets to scan |
| `SCANNER_INTERVAL_MINUTES` | `60` | `0+` | Auto-scan interval. `0` = disabled |
| `SCANNER_CACHE_TTL` | `300` | seconds | TTL for AssetUniverse cache |
| `SCANNER_TIMEOUT` | `300` | seconds | Timeout for `run_in_executor` |
| `SCANNER_TOP_N` | `3` | `1+` | Top N signals to execute |

## Color Contract

| Element | Style |
|---------|-------|
| Action BUY | `green` (ANSI 32) |
| Action SELL | `red` (ANSI 31) |
| Score > 0 | `bold green` |
| Timestamp | `cyan` |
| Panel title | `bold white` |
| Border | `white` |
| No data | `dim white` |

**System:** `Console(color_system='standard')` — 16-color ANSI only.
**Forbidden:** `#rrggbb` hex, 24-bit RGB, emoji in UI.
