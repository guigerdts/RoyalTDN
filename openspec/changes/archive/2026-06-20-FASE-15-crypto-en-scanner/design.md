# Design: FASE 15 — Crypto en el Scanner

## Technical Approach

Add crypto pair scanning (BTC/USD, ETH/USD, etc.) as a new `AssetUniverse` type alongside existing `etfs`/`sp500`/`all`. Crypto detection uses `/` in the symbol string — `LiquidityFilter` and `_batch_get_symbol_data()` branch to `get_crypto_bars()` / `CryptoHistoricalDataClient` when a symbol contains `/`. The `int(b.volume)` cast is changed to `float(b.volume)` universally to handle `Decimal` volumes from crypto bars.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Type detection | `/` in symbol = crypto | Dedicated param, separate universe list | Self-documenting; no new coupling. Crypto pairs always contain `/`. |
| Crypto client wiring | Injected as separate `crypto_data_client` param to `Scanner.__init__()` | Single client with union method, auto-detect in filters.py | Keeps filter logic stateless; `Scanner` owns dispatch. `LiquidityFilter` receives correct client per symbol from caller. |
| TokenBucket | Shared single instance | Separate bucket per client type | Alpaca rate limit is per-account, not per-endpoint. Shared bucket accurately respects the 200 req/min limit. |
| Crypto universe | Hardcoded `DEFAULT_CRYPTO` list | API discovery, config file | 10 pairs stable, no discovery endpoint needed. Proposal scope explicitly out-of-scope for dynamic discovery. |
| Volume type fix | `int(b.volume)` → `float(b.volume)` universally | Try/except per type | Stock bars use `int` but `float()` handles both. Single path reduces branches. |

## Data Flow

```
                       ┌──────────────────┐
                       │    main.py       │
                       │  creates both    │
                       │  data clients    │
                       └────────┬─────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
      ┌───────────────┐ ┌─────────────┐ ┌────────────────┐
      │ AssetUniverse │ │ Scanner     │ │ LiquidityFilter │
      │ "crypto" →    │ │ __init__    │ │ .filter()       │
      │ 10 pairs      │ │ stores both │ │ per symbol:     │
      └───────┬───────┘ │ clients     │ │  "/" in sym?    │
              │         └──────┬──────┘ │  ┌─yes→get_crypto_bars
              ▼                 ▼        │  └─no →get_stock_bars
      Scanner.scan()    _batch_get_      └────────────────────
      calls univ +      symbol_data()
      filter + batch    splits batches by type,
                        calls correct client per batch
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/royaltdn/scanner/universe.py` | Modify | Add `"crypto"` to `VALID_UNIVERSE_TYPES`, `DEFAULT_CRYPTO` list, `_get_default_crypto()` method |
| `src/royaltdn/scanner/filters.py` | Modify | Add `CryptoHistoricalDataClient` import + `CryptoBarsRequest` import. Branch on `/` in symbol → `get_crypto_bars()`. Shared `TokenBucket`. |
| `src/royaltdn/scanner/scanner.py` | Modify | Add `crypto_data_client` param to `__init__()`. Split batches by type in `_batch_get_symbol_data()`. `int(b.volume)` → `float(b.volume)`. Add imports. |
| `src/royaltdn/main.py` | Modify | Create both `StockHistoricalDataClient` and `CryptoHistoricalDataClient`. Pass both to `Scanner`. |
| `src/royaltdn/frontend/menu/app.py` | Modify | Add `"crypto": "Crypto (10 pairs)"` to `universe_label` dict (line ~1329). |

## Interfaces / Contracts

```python
# Scanner.__init__() — new signature (backward-compatible via optional param)
class Scanner:
    def __init__(
        self,
        universe: AssetUniverse,
        liquidity_filter: LiquidityFilter,
        strategies: Dict[str, BaseStrategy],
        data_client: Any,                              # StockHistoricalDataClient
        crypto_data_client: Optional[Any] = None,      # NEW: CryptoHistoricalDataClient
    ):
        ...

    # _batch_get_symbol_data() — internal type detection
    def _batch_get_symbol_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        # Split symbols into crypto (contains "/") and stocks
        # Build separate batch requests per type
        # Call self.data_client.get_stock_bars() for stock batches
        # Call self.crypto_data_client.get_crypto_bars() for crypto batches
        # Universal: volume = float(b.volume)

# LiquidityFilter.filter() — branching inside loop
class LiquidityFilter:
    def filter(self, symbols: List[str], data_client: Any) -> List[str]:
        for symbol in symbols:
            request_cls = CryptoBarsRequest if "/" in symbol else StockBarsRequest
            bars = crypto_client.get_crypto_bars(req) if "/" in symbol
                   else stock_client.get_stock_bars(req)
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit — Universe | `SCANNER_UNIVERSE=crypto` returns 10 pairs | `AssetUniverse("key","secret", universe_type="crypto")` → `len(symbols)==10`, all contain `/` |
| Unit — Universe | Existing `test_asset_universe_invalid_type` | **Will break** — `"crypto"` is now valid, so test must be updated to use an actual invalid type like `"invalid_xyz"` |
| Unit — Filter | Crypto symbol branches to `CryptoBarsRequest` | Mock `CryptoHistoricalDataClient`; pass `BTC/USD` → verify `get_crypto_bars()` called |
| Unit — Filter | Stock symbol still uses `StockBarsRequest` | Mock `StockHistoricalDataClient`; pass `SPY` → verify `get_stock_bars()` called |
| Unit — Filter | Mixed list processes both types | `["SPY","BTC/USD","QQQ"]` → 3 calls, correct client per type |
| Unit — Scanner Batch | Crypto-only batch calls `get_crypto_bars` | Mock both clients; verify correct method per batch |
| Unit — Scanner Batch | Mixed symbols split into proper batches | 150 stocks + 10 crypto → 2 stock batches + 1 crypto batch |
| Integration | Full scan with crypto symbols | `Scanner` with mocked clients generates signals for crypto pairs |
| Regression | All existing stock tests pass | Existing 15+ tests with `data_client.get_stock_bars` mocks unchanged |

**Critical test update**: `test_asset_universe_invalid_type()` currently uses `"crypto"` as the invalid type → must change to `"invalid_xyz"`.

## Migration / Rollout

No migration required. `SCANNER_UNIVERSE=crypto` activates the new type; existing configurations (`etfs`/`sp500`/`all`) remain unchanged.

## Open Questions

None.
