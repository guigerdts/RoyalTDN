# File Change Map: FASE 18.2 — Parámetros duales + Reorganización visual del menú

## 0. `src/royaltdn/scanner/universe.py` — Modify (1 change)

### Change 0.1: Add `universe_type` property setter
Add after the existing `@property universe_type`:
```python
@universe_type.setter
def universe_type(self, value: str) -> None:
    if value not in self.VALID_UNIVERSE_TYPES:
        raise ValueError(f"Invalid universe type: {value!r}. Valid: {self.VALID_UNIVERSE_TYPES}")
    self._universe_type = value
    self.invalidate_cache()
```

## 1. `src/royaltdn/strategy/base.py` — Modify (4 changes)

### Change 1.1: Add `category` parameter to `__init__`
```python
def __init__(self, timeframe: str = "1d", category: str = "swing"):
    self.timeframe = timeframe
    self._category = category
```

### Change 1.2: Add `category` property
```python
@property
def category(self) -> str:
    return self._category
```

### Change 1.3: Add optional `symbol` param to `generate_signal()` signature
```python
@abstractmethod
def generate_signal(self, data: pd.DataFrame, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
    ...
```

### Change 1.4: Make `get_parameters()` concrete (was abstract)
Remove `@abstractmethod`. Add default implementation:
```python
def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
    return {"timeframe": self.timeframe, "category": self._category}
```

## 2. `src/royaltdn/strategy/sma_strategy.py` — Modify (4 changes)

### Change 2.1: Add `_PROFILES` class-level dict
```python
_PROFILES = {
    "crypto": {"sma_fast": 7, "sma_slow": 25, "timeframe": "1d"},
    "stocks": {"sma_fast": 5, "sma_slow": 20, "timeframe": "1d"},
}
```

### Change 2.2: `__init__` — add `category="swing"`, pass to `super().__init__()`
Inside `__init__`, call `super().__init__(timeframe=timeframe, category=category)`.

### Change 2.3: `generate_signal(data, symbol=None)` — resolve profile to LOCAL vars
Add `symbol: Optional[str] = None` parameter. At the start of the method, resolve profile:
```python
from royaltdn.scanner.universe import is_crypto_symbol
_profile = self._PROFILES["crypto"] if (symbol and is_crypto_symbol(symbol)) else self._PROFILES["stocks"]
sma_fast = _profile["sma_fast"]
sma_slow = _profile["sma_slow"]
timeframe = _profile["timeframe"]  # metadata only
```

**IMPLEMENTATION NOTE**: Use LOCAL variables `sma_fast`/`sma_slow` instead of `self.sma_fast`/`self.sma_slow` inside the method. The `self.sma_fast` attrs stay at their constructor values (stocks default) — they are NOT mutated per call. This avoids thread-safety hazards and makes the profile selection per-call explicit.

### Change 2.4: `get_parameters(symbol=None)` — three-way branch
Add `symbol: Optional[str] = None` parameter:
```python
def get_parameters(self, symbol: Optional[str] = None) -> Dict[str, Any]:
    from royaltdn.scanner.universe import is_crypto_symbol
    if symbol is None:
        # No symbol context: return BOTH profiles with prefixes
        result = {}
        for prefix, profile in [("crypto", self._PROFILES["crypto"]),
                                 ("stocks", self._PROFILES["stocks"])]:
            for k, v in profile.items():
                result[f"{prefix}_{k}"] = v
        result["category"] = self._category
        return result
    elif is_crypto_symbol(symbol):
        return {**self._PROFILES["crypto"], "category": self._category}
    else:
        return {**self._PROFILES["stocks"], "category": self._category}
```

## 3. `src/royaltdn/strategy/bollinger_rsi.py` — Modify (4 changes)

### Change 3.1: Add `_PROFILES` dict
```python
_PROFILES = {
    "crypto": {"bb_period": 15, "bb_std": 2.5, "rsi_period": 10,
               "rsi_oversold": 25, "rsi_overbought": 75,
               "max_bars_hold": 20, "timeframe": "5min"},
    "stocks": {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14,
               "rsi_oversold": 30, "rsi_overbought": 70,
               "max_bars_hold": 30, "timeframe": "15min"},
}
```

### Change 3.2: `__init__` — add `category="swing"`, pass to super
`super().__init__(timeframe=timeframe, category=category)`

### Change 3.3: `generate_signal(data, symbol=None)` — profile resolution
Same pattern as SMA: add `symbol: Optional[str] = None` param, resolve `_profile` at method start using `is_crypto_symbol(symbol)`, and use **local variables** for all profile-specific params. The constructor params (`self.bb_period`, etc.) remain as stock defaults and are NOT mutated.

### Change 3.4: `get_parameters(symbol=None)` — three-way branch
Same pattern as SMA. Returns merged `crypto_*`/`stocks_*` keys when `symbol is None`, single profile otherwise.

## 4. `src/royaltdn/strategy/momentum_atr.py` — Modify (4 changes)

### Change 4.1: Add `_PROFILES` dict
```python
_PROFILES = {
    "crypto": {"momentum_period": 15, "atr_period": 14,
               "atr_max_pct": 4.0, "exit_period": 3, "timeframe": "1d"},
    "stocks": {"momentum_period": 20, "atr_period": 20,
               "atr_max_pct": 2.0, "exit_period": 5, "timeframe": "1d"},
}
```

### Change 4.2: `__init__` — add `category="swing"`, pass to super
`super().__init__(timeframe=timeframe, category=category)`

### Change 4.3: `generate_signal(data, symbol=None)` — profile resolution
Same pattern: add `symbol` param, resolve `_profile` at method start, use local vars.

### Change 4.4: `get_parameters(symbol=None)` — three-way branch
Same pattern as SMA.

## 5. `src/royaltdn/scanner/scanner.py` — Modify (1 change, ~5 lines)

### Change 5.1: Inspect-based symbol dispatch in scan loop

In the `scan()` method, inside the `for strategy_name, strategy` loop (~line 130), change:
```python
# BEFORE (line 132):
signal = strategy.generate_signal(data)

# AFTER:
import inspect
sig = inspect.signature(strategy.generate_signal)
kwargs = {"symbol": symbol} if "symbol" in sig.parameters else {}
signal = strategy.generate_signal(data, **kwargs)
```

## 6. `src/royaltdn/frontend/menu/app.py` — Modify (6 changes)

### Change 6.1: Module-level universe state (near top, after `_last_menu_visit`)
```python
_current_universe: str = "all"
_UNIVERSE_CYCLE = ("all", "etfs", "crypto", "sp500")
_universe_setter: Optional[Callable[[str], None]] = None
```
Add import for `Callable` from `typing` (or use `collections.abc`).

### Change 6.2: `set_universe_setter()` function
```python
def set_universe_setter(fn: Callable[[str], None]) -> None:
    global _universe_setter
    _universe_setter = fn
```

### Change 6.3: `_cycle_universe()` helper
```python
def _cycle_universe() -> str:
    global _current_universe
    idx = (_UNIVERSE_CYCLE.index(_current_universe) + 1) % len(_UNIVERSE_CYCLE)
    _current_universe = _UNIVERSE_CYCLE[idx]
    if _universe_setter is not None:
        _universe_setter(_current_universe)
    return _current_universe
```

### Change 6.4: `_print_header()` — show current universe
After the pause status line, add:
```python
console.print(f"[cyan]Universe: {_current_universe}[/]")
```

### Change 6.5: `_print_menu()` — add 'U' option
In the items list, change "0", "Salir" to end, and add a new item before it:
```python
("U", "Cambiar universo (all→etfs→crypto→sp500→all)"),
("0", "Salir"),
```

### Change 6.6: Main loop — handle 'U'/'u'
In `run_menu()` main loop, after the `elif cmd == "8"` block (line 63), add:
```python
elif cmd.lower() == "u":
    new_uni = _cycle_universe()
    _log_activity(f"Universe changed to {new_uni}", logs_dir)
    console.print(f"[green]Universe changed to: {new_uni}[/]")
    _wait_enter()
```

### Change 6.7: `_show_estrategias()` — category sections
In `_show_estrategias()`, change the flat table rendering to grouped sections:
- Group `entries` by `config.get("category", "swing")`
- Define section config: `{"swing": ("🔵 Swing", "bold blue"), "scalping": ("🟢 Scalping", "bold green"), "intradia": ("🟡 Intradía", "bold yellow")}`
- For each group with entries: render a Table with section-colored header, columns: #, Nombre, Tipo, Activa, Categoría, Parámetros
- For empty groups (scalping, intradia): render `"[dim]No hay estrategias[/]"` in that section's color
- Add column for Categoría between Activa and Parámetros

## 7. `src/royaltdn/main.py` — Modify (1 change, ~3 lines)

### Change 7.1: Wire universe setter before `run_menu()`

Inside `cmd_run()`, after the scanner is created and before calling `run_menu()`, add:
```python
# Wire universe change callback for menu 'U' key
if scanner is not None:
    from royaltdn.frontend.menu.app import set_universe_setter
    set_universe_setter(lambda ut: setattr(scanner.universe, 'universe_type', ut))
```

## Summary

| File | Changes | Lines Changed |
|------|---------|---------------|
| `scanner/universe.py` | +1 (setter) | ~6 |
| `strategy/base.py` | +4 edits | ~12 |
| `strategy/sma_strategy.py` | +4 edits | ~45 |
| `strategy/bollinger_rsi.py` | +4 edits | ~50 |
| `strategy/momentum_atr.py` | +4 edits | ~40 |
| `scanner/scanner.py` | +1 edit | ~5 |
| `frontend/menu/app.py` | +7 edits | ~90 |
| `main.py` | +1 edit | ~3 |
| **Total** | **26 edits** | **~250** |

## Files NOT modified (by design)

| File | Reason |
|------|--------|
| `strategy/factor_rotation.py` | Out of scope per spec — no dual params |
| `strategy/dynamic.py` | Out of scope per spec — user strategies, no dual params |
| `strategy/strategy_store.py` | User strategy storage — no changes needed |
| `frontend/console/commands.py` | No new IPC functions needed (in-process callback used instead) |
| `orchestrator.py` | No IPC polling for universe needed (in-process callback) |
