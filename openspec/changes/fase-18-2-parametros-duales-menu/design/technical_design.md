# Design: FASE 18.2 — Parámetros duales crypto/stocks + Reorganización visual del menú

## Technical Approach

Three in-memory dual-profile strategies (SMA, Bollinger RSI, Momentum ATR) + one interface fix + one menu reorg. Backward compatible: the `symbol` param in `generate_signal()` is optional, defaulting to `None` (stock profile). No IPC files. In-process callback for universe changes.

```
BaseStrategy (abc)
  ├── category: str = "swing"
  ├── generate_signal(data, symbol=None)
  └── get_parameters(symbol=None)      ← concrete default impl

  ┌───────┬───────────────┬───────────────┐
  SMA   BollingerRSI   MomentumATR   FactorRotation/Dynamic
                                     (NOT modified — symbol=None only)
```

Profile routing: `is_crypto_symbol(symbol)` → picks crypto or stocks `_PROFILES` dict.

## Architecture Decisions

### Decision: In-process universe change via callback

| Option | Tradeoff | Decision |
|--------|----------|----------|
| IPC file `universe_signal.json` | Orphan consumer in prev. design; violates spec "no persistence" | ❌ |
| `app.py` module var + orchestrator polls file | Creates consumer but still IPC | ❌ |
| In-process `Callable[[str], None]` callback wired from main.py | +0 complexity, same-process (orchestrator is daemon thread in same process), no files, no polling | ✅ **Chosen** |

**Choice**: Add `@universe_type.setter` to `AssetUniverse` (sets `_universe_type` + calls `invalidate_cache()`). Wire a callable in `app.py` via `set_universe_setter(fn)` called from `main.py` after scanner creation. The 'U' handler calls `fn(new_type)` — in-process, no IPC.

### Decision: `get_parameters(symbol)` three-way branch

**Choice**: Explicit three-way instead of previous fallthrough:
- `symbol is None` → return both profiles with `crypto_*` / `stocks_*` prefixes
- `is_crypto_symbol(symbol)` → return crypto single profile
- else → return stocks single profile

### Decision: Scanner adapts for strategies that don't support `symbol`

FactorRotationStrategy and DynamicStrategy override `generate_signal(data)` without `symbol` param. The scanner uses `inspect.signature()` to check if each strategy's method accepts `symbol` before passing it. If not, it falls back to `generate_signal(data)`. This modifies neither strategy and preserves backward compat.

## Data Flow

```
User presses 'U' in menu
  │
  ▼
_cycle_universe() → cycles _current_universe: "all"→"etfs"→"crypto"→"sp500"
  ├── _universe_setter(new_uni)     ← in-process callable
  │     └── AssetUniverse.universe_type = new_uni
  │           ├── self._universe_type = new_uni
  │           └── self.invalidate_cache()
  └── header re-renders with "[cyan]Universe: {name}[/]"

Next scan() call:
  scan_loop:
    for strategy in strategies:
      if inspect 'symbol' param exists:
        strategy.generate_signal(data, symbol=symbol)
      else:
        strategy.generate_signal(data)       ← FactorRotation, Dynamic
```

## Interfaces / Contracts

```python
# AssetUniverse — add setter
@property
def universe_type(self) -> str: ...
@universe_type.setter
def universe_type(self, value: str) -> None:
    if value not in self.VALID_UNIVERSE_TYPES:
        raise ValueError(...)
    self._universe_type = value
    self.invalidate_cache()

# BaseStrategy
class BaseStrategy(ABC):
    def __init__(self, timeframe="1d", category="swing"):
        self._category = category
    @property
    def category(self) -> str: return self._category
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame,
                        symbol: str | None = None) -> dict | None: ...
    def get_parameters(self, symbol: str | None = None) -> dict:  # concrete
        return {"timeframe": self.timeframe, "category": self._category}

# Each dual-param strategy
_PROFILES = {
    "crypto": {...param dict...},
    "stocks": {...param dict...},
}

# app.py
_current_universe: str = "all"
_UNIVERSE_CYCLE = ("all", "etfs", "crypto", "sp500")
_universe_setter: Callable[[str], None] | None = None

def set_universe_setter(fn: Callable[[str], None]) -> None:
    global _universe_setter; _universe_setter = fn

# scanner.py scan loop — inspect-based dispatch
import inspect
for name, strategy in self.strategies.items():
    sig = inspect.signature(strategy.generate_signal)
    kwargs = {"symbol": symbol} if "symbol" in sig.parameters else {}
    signal = strategy.generate_signal(data, **kwargs)
```

## CRITICAL ISSUES RESOLVED

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| CRITICAL 1: Universe IPC file no consumer | `invalidate_universe.json` not read by anyone | In-process callback `set_universe_setter()` + `@universe_type.setter` on `AssetUniverse`. No IPC files. |
| CRITICAL 2: `get_parameters()` fallthrough | `if symbol and is_crypto(symbol)` fell through to stocks for stock symbols | Explicit three-way: None→both, crypto→crypto, else→stocks |
| CRITICAL 3: `generate_signal(symbol)` breaks subclasses | FactorRotation/Dynamic override `generate_signal(data)` without `symbol` | Scanner uses `inspect.signature()` to detect support. Subclasses NOT modified. |

## File Changes

| File | Changes |
|------|---------|
| `scanner/universe.py` | +`universe_type.setter` (~5 lines) |
| `strategy/base.py` | category param/property, `get_parameters()` concrete impl, `generate_signal()` symbol param |
| `strategy/sma_strategy.py` | `_PROFILES` dict, `generate_signal(symbol)` profile routing, `get_parameters(symbol)` three-way |
| `strategy/bollinger_rsi.py` | Same pattern as SMA |
| `strategy/momentum_atr.py` | Same pattern as SMA |
| `scanner/scanner.py` | `inspect.signature` check in scan loop (~3 lines changed) |
| `frontend/menu/app.py` | Universe state/cycle/setter, 'U' key, header display, category sections |
| `main.py` | Wire `set_universe_setter()` after scanner creation (~2 lines) |

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | Each strategy: crypto symbol → crypto profile | `generate_signal(data, symbol="BTC/USD")` assert crypto params used |
| Unit | Each strategy: stock symbol → stock profile | `generate_signal(data, symbol="SPY")` assert stock params |
| Unit | Each strategy: no symbol → stock default | `generate_signal(data)` assert stock params |
| Unit | `category` property (all 3) | `assert s.category == "swing"` |
| Unit | `_cycle_universe()` iteration | Cycle 8× → verify sequence wraps |
| Integration | Scanner inspect dispatch | Mock FactorRotationStrategy, verify `symbol` NOT passed |
| Integration | `get_parameters(None)` returns both profiles | Verify `crypto_*` AND `stocks_*` keys present |
| Integration | Universe setter invalidates cache | Set `universe_type="crypto"` → assert cache cleared |
| E2E | Menu 'U' key cycles + header updates | Integration test with mocked console |
| E2E | Category sections render | Render `_show_estrategias()` with mock entries |

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Scanner passes daily bars to 5min Bollinger profile | Documented known limitation — FASE 18.3 addresses per-symbol timeframe |
| Thread safety: menu + orchestrator share `AssetUniverse.universe_type` | Single-threaded scan loop; GIL protects simple attr sets; no concurrent scan writes |
| `get_parameters()` called without symbol on FactorRotation | All callers (orchestrator, menu) call without args — safe |
