# Design: FASE 17.5 (CIERRE) — Corrección de 2 bugs restantes

## Technical Approach

Two independent fixes:

- **Bug 2 (crypto format)**: Make `AssetUniverse._get_default_crypto()` broker-aware by accepting `broker_type`. Add `DEFAULT_CRYPTO_BINANCE` constant (BTCUSDT, ETHUSDT...) returned when broker is Binance. Mitigate the breaking change: all `"/" in symbol` crypto-detection sites (5 locations across 4 files) are updated to use a centralized `is_crypto_symbol()` helper. Empty DataFrames from crypto broker log visible warning instead of silent skip.

- **Bug 7 (pyc cache)**: One-liner: `sys.dont_write_bytecode = True` at the top of `__init__.py`. Completely independent.

The key risk from the spec phase (slash-based detection breaking with Binance symbols) is addressed by introducing `is_crypto_symbol()` — a function in `universe.py` that checks both `"/" in symbol` AND membership in a `_CRYPTO_SYMBOLS` frozenset (union of both symbol lists). This keeps detection centralized rather than duplicating logic across 5 files.

## Architecture Decisions

### Decision 1: Symbol format strategy — Option A with centralized helper

| Option | Approach | Files Changed | Risk |
|--------|----------|--------------|------|
| **A: Broker-native + fix all slash checks** | Return BTCUSDT for Binance, update detection sites | 7 | Medium — must touch all detection sites |
| B: Keep slash format, normalize at broker boundary | Always return BTC/USD, rely on `normalize_symbol()` | 3 | Low — but doesn't match spec intent |
| C: Helper function `is_crypto_symbol()` | Centrally detect crypto symbols | 7+1 helper | Low — clean, maintainable |

**Choice**: Option A + C — return broker-native format (as spec requires) AND introduce `is_crypto_symbol()` in `universe.py`. Rationale: BinanceBroker already calls `normalize_symbol()` internally for `get_bars()`, `submit_order()`, etc., so passing BTC/USD works. However, the spec explicitly requires Binance-native return format, and the helper makes the change maintainable. Without the helper, adding new crypto pairs or changing formats would require touching 5 files independently.

### Decision 2: Broker detection

**Choice**: Presence of `BINANCE_API_KEY` env var in `main.py`. If set → `broker_type="binance"`, otherwise `"alpaca"`. This matches existing detection pattern and is already used to instantiate `BinanceBroker`. No new env vars needed.

### Decision 3: Helper location

**Choice**: `is_crypto_symbol()` as module-level function in `universe.py`. Rationale: `AssetUniverse` already owns the crypto symbol constants (`DEFAULT_CRYPTO`, `DEFAULT_CRYPTO_BINANCE`). The helper builds a `_CRYPTO_SYMBOLS` frozenset from the union of both lists (normalized to uppercase, slash stripped). Callers import from `royaltdn.scanner.universe` — a dependency that already exists in all affected files.

## Data Flow

```
main.py: detect broker_type ──→ AssetUniverse(broker_type) ──→ _get_default_crypto()
                                   │
                                   ├─ broker_type="alpaca"  → DEFAULT_CRYPTO  (BTC/USD)
                                   └─ broker_type="binance" → DEFAULT_CRYPTO_BINANCE (BTCUSDT)

Symbols flow through scanner pipeline:
  universe.get_symbols()
    → LiquidityFilter.filter()        ← uses is_crypto_symbol() for routing
    → Scanner._batch_get_symbol_data() ← uses is_crypto_symbol() for split
    → broker.get_bars()               ← BinanceBroker calls normalize_symbol() internally
```

## File Changes

### Bug 7 — pyc cache (1 file)

| File | Action | Description |
|------|--------|-------------|
| `src/royaltdn/__init__.py` | Modify | Add `import sys; sys.dont_write_bytecode = True` as first executable lines |

### Bug 2 — Crypto format (6 files)

| File | Action | Description |
|------|--------|-------------|
| `src/royaltdn/scanner/universe.py` | Modify | Add `DEFAULT_CRYPTO_BINANCE`, `_CRYPTO_SYMBOLS` frozenset, `is_crypto_symbol()` helper. Modify `__init__()` to accept `broker_type="alpaca"`. Modify `_get_default_crypto()` to return broker-specific constant. |
| `src/royaltdn/main.py` | Modify | Detect `BINANCE_API_KEY`, pass `broker_type` to `AssetUniverse(broker_type=...)` |
| `src/royaltdn/scanner/filters.py` | Modify | Replace `"/" in symbol` with `is_crypto_symbol(symbol)`. Add warning when `df.empty` after `broker.get_bars()`. |
| `src/royaltdn/scanner/scanner.py` | Modify | Update `_get_broker_for_symbol()` and `_batch_get_symbol_data()` crypto/stock split to use `is_crypto_symbol()` |
| `src/royaltdn/orchestrator.py` | Modify | Update `_get_broker_for_symbol()` to use `is_crypto_symbol()` |
| `src/royaltdn/risk_manager.py` | Modify | Update crypto detection to use `is_crypto_symbol()` |

## Interfaces

```python
# universe.py additions
DEFAULT_CRYPTO_BINANCE: list[str] = [
    "BTCUSDT", "ETHUSDT", "LTCUSDT", "BCHUSDT",
    "LINKUSDT", "UNIUSDT", "AAVEUSDT", "MATICUSDT",
    "DOGEUSDT", "SHIBUSDT",
]

_CRYPTO_SYMBOLS: frozenset = frozenset(
    s.replace("/", "").upper() for s in DEFAULT_CRYPTO
) | frozenset(DEFAULT_CRYPTO_BINANCE)

def is_crypto_symbol(symbol: str) -> bool:
    """Return True if symbol is a known crypto pair (with or without slash)."""
    return "/" in symbol or symbol.upper() in _CRYPTO_SYMBOLS

# AssetUniverse.__init__() new param:
#   broker_type: str = "alpaca",  # "alpaca" | "binance"

# AssetUniverse._get_default_crypto() becomes:
#   def _get_default_crypto(self) -> list[str]:
#       if self._broker_type == "binance":
#           return self.DEFAULT_CRYPTO_BINANCE.copy()
#       return self.DEFAULT_CRYPTO.copy()
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `is_crypto_symbol()` | Parametrized: BTC/USD, BTCUSDT → True; SPY, AAPL → False |
| Unit | `_get_default_crypto()` with broker_type | Test both "alpaca" → slash symbols, "binance" → clean symbols |
| Unit | `LiquidityFilter.filter()` with empty broker df | Verify warning logged and symbol skipped |
| Manual | End-to-end crypto scan with Binance testnet | `SCANNER_UNIVERSE=crypto BINANCE_API_KEY=... python -m royaltdn scanner` — verify BTCUSDT in output, no errors |
| Manual | pyc cache | `find . -name __pycache__ -exec rm -rf {} +` then `python -m royaltdn check` — verify no `.pyc` created |

## Rollback Plan

Both bugs are independent and can be reverted separately:

- Bug 7 revert: `git revert <pyc-commit>` — zero side effects
- Bug 2 revert: `git revert <crypto-commit>` — reverts `universe.py`, `main.py`, and all 4 files with `is_crypto_symbol()` updates atomically

The two changes should be in **separate commits** to enable independent rollback. Both commits in the same PR (single PR, 2 commits).
