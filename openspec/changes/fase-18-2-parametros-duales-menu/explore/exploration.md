# Exploration: FASE 18.2 — Parámetros duales crypto/stocks + Reorganización visual del menú

## Current State

### Strategy Architecture

The system has 3 predefined strategies plus `factor_rotation` (not included in this change), all inheriting from `BaseStrategy` (`src/royaltdn/strategy/base.py`):

**Contract (`BaseStrategy`)**:
- `name` (property): unique identifier string
- `generate_signal(data: pd.DataFrame) -> Optional[dict]`: receives OHLCV DataFrame, returns signal or None
- `get_parameters() -> dict`: returns current parameters
- `validate() -> bool`: validates configuration

**Crucial limitation**: `generate_signal()` receives **only** `data: pd.DataFrame` — no `symbol` parameter. The strategy has no way to know if the data is crypto or stocks. Currently this doesn't matter because all strategies use a single param set.

**Three strategies to modify**:

1. **`SMAStrategy`** (`src/royaltdn/strategy/sma_strategy.py`):
   - Defaults: `sma_fast=5, sma_slow=20, timeframe="1d"`
   - Dual needed: crypto `(7, 25)` vs stocks `(5, 20)`
   - `generate_signal()` computes SMA from `close` column via `compute_sma()` helper

2. **`BollingerRSIStrategy`** (`src/royaltdn/strategy/bollinger_rsi.py`):
   - Defaults: `bb_period=20, bb_std=2.0, rsi_period=14, rsi_oversold=30, rsi_overbought=70, max_bars_hold=30, timeframe="5min"`
   - Dual needed for ALL params including `timeframe`
   - `generate_signal()` computes Bollinger Bands + RSI from `close` column

3. **`MomentumATRStrategy`** (`src/royaltdn/strategy/momentum_atr.py`):
   - Defaults: `momentum_period=20, atr_period=20, atr_max_pct=2.0, exit_period=5, timeframe="1d"`
   - Dual needed for ALL params including `timeframe`
   - `generate_signal()` uses `close` (and optionally `high`/`low`) columns

### Menu System

**`_show_estrategias()`** (`src/royaltdn/frontend/menu/app.py`, line 1484):
- Loads predefined strategies from `logs/strategies.json` (published by orchestrator)
- Loads user strategies from `StrategyStore` (disk: `user_strategies/*.json`)
- Merges them into a single sorted-by-name list
- Renders a flat `Rich Table` with columns: `#`, `Nombre`, `Tipo`, `Activa`, `Parámetros`
- No categories, no colored grouping, no universe switching

**`_print_menu()`** (line 115):
- Main menu renders as a Table with numbered items
- Current items: 1-8 + 0 (salir)
- No 'U' key binding for universe switching

**State loading flow**:
- `StateLoader.load_strategies()` → reads `logs/strategies.json` → returns dict with `strategies[]` list
- Each entry has: `name`, `active`, `params`, `validation`, `symbol`, `timeframe`
- The menu also loads user strategies from `StrategyStore.load_all()`

### Scanner Integration (`src/royaltdn/scanner/scanner.py`)

- Scanner receives `strategies: Dict[str, BaseStrategy]` from `main.py`
- In `scan()`, iterates `self.strategies.items()`:
  ```python
  for strategy_name, strategy in self.strategies.items():
      signal = strategy.generate_signal(data)
  ```
- **No symbol is passed to `generate_signal()`** — symbol context is lost
- Scanner already splits symbols into crypto/stocks for data routing (lines 241-242):
  ```python
  crypto_symbols = [s for s in to_fetch if is_crypto_symbol(s)]
  stock_symbols = [s for s in to_fetch if not is_crypto_symbol(s)]
  ```
- Already imports `is_crypto_symbol` from `scanner.universe`

### Universe Detection (`src/royaltdn/scanner/universe.py`)

- `is_crypto_symbol(symbol: str) -> bool`: checks for `"/"` in symbol or membership in a frozenset of known crypto pairs
- Works for both Alpaca format (`BTC/USD`) and Binance format (`BTCUSDT`)
- Already widely used in scanner and filters

### Strategy Registration (`src/royaltdn/main.py`, line 314-326)

- Strategies are instantiated with defaults and stored in a dict:
  ```python
  strategies["sma_crossover"] = SMAStrategy()
  strategies["bollinger_rsi"] = BollingerRSIStrategy()
  strategies["momentum_atr"] = MomentumATRStrategy()
  ```
- The orchestrator reads `self._scanner.strategies` to publish `logs/strategies.json`

### Parameter Persistence (`src/royaltdn/orchestrator.py`, line 475-520)

- `_build_strategies_list()` calls `strategy.get_parameters()` for each strategy
- Published in `logs/strategies.json` as `strategies[].params` dict
- This is what the menu reads to display parameters

## Affected Areas

### Core Strategy (interface change)
- `src/royaltdn/strategy/base.py` — `generate_signal()` signature needs optional `symbol` parameter, or new method to set symbol context
- `src/royaltdn/strategy/sma_strategy.py` — dual params (crypto/stocks) + dynamic selection
- `src/royaltdn/strategy/bollinger_rsi.py` — dual params for all indicators
- `src/royaltdn/strategy/momentum_atr.py` — dual params for all indicators

### Scanner (pass symbol context)
- `src/royaltdn/scanner/scanner.py` — pass symbol info to `generate_signal()` call (line 132)

### Menu (visual reorganization)
- `src/royaltdn/frontend/menu/app.py`:
  - `_show_estrategias()` — categorized table with color-coded groups
  - `_print_menu()` — add 'U' key binding for universe switching
  - `_strategy_submenu()` — optional category display
- `src/royaltdn/frontend/console/components/state.py` — optional new key for category in strategies

### Main entry (dual profile defaults)
- `src/royaltdn/main.py` — strategy instantiation with dual profiles (lines 314-326)

### Orchestrator (publish dual params)
- `src/royaltdn/orchestrator.py` — `_build_strategies_list()` (line 475) — params reflect dual profiles

### Testing
- `tests/test_strategy.py` — new tests for dual param behavior
- `tests/test_bollinger_rsi.py` — new tests for dual profile selection
- `tests/test_momentum_atr.py` — new tests for dual profile selection
- `tests/test_menu.py` — potential menu tests

## Approaches

### Approach 1 for Dual Params: Add optional `symbol` to `generate_signal()`

Modify `BaseStrategy.generate_signal(self, data, symbol: Optional[str] = None)`. Store both profiles in constructor. Select params at call time.

```python
class SMAStrategy(BaseStrategy):
    def __init__(self, ...):
        self._crypto_params = {"sma_fast": 7, "sma_slow": 25}
        self._stock_params = {"sma_fast": 5, "sma_slow": 20}

    def generate_signal(self, data, symbol=None):
        params = self._crypto_params if symbol and is_crypto_symbol(symbol) else self._stock_params
        # use params...
```

Scanner passes `symbol` explicitly. Existing callers without `symbol` default to stock params.

- **Pros**: Clean, explicit, backward-compatible (optional param), matches requirement ("detecta el tipo de símbolo en cada llamada")
- **Cons**: Changes abstract interface, requires updating all 3 strategies + BaseStrategy + scanner + orchestrator legacy loop
- **Effort**: Medium

### Approach 2 for Dual Params: Pre-call `set_symbol()` setter

Add a `set_symbol_context(symbol)` method to BaseStrategy. Scanner calls it before each `generate_signal()`:

```python
for symbol in symbols:
    strategy.set_symbol_context(symbol)
    signal = strategy.generate_signal(data)
```

Strategy stores `self._current_symbol`, then uses it inside `generate_signal()`.

- **Pros**: Does NOT change `generate_signal()` signature, no changes to dynamic strategies
- **Cons**: Temporal coupling (must call setter before), thread-safety concerns, easy to forget
- **Effort**: Low-Medium

### Approach 3 for Dual Params: Data-driven detection

Strategy detects market type from data characteristics (e.g., typical price range, volume patterns) rather than symbol. No symbol info needed.

- **Pros**: No interface change at all
- **Cons**: Unreliable (crypto can trade at stock-like prices, stocks can have crypto-like volatility), NOT what the requirement asks for
- **Effort**: Low (no change to scanner) but WRONG approach
- **Recommendation**: DO NOT USE

### Recommendation for Dual Params

**Approach 1** (optional `symbol` in `generate_signal()`): It's the cleanest fit for the requirement. The optional parameter keeps backward compat, and the symbol is explicitly available at the point of decision. The scanner already iterates per-symbol and has `is_crypto_symbol` imported.

---

### Approach A for Menu Reorganization: Category table with colored headers

In `_show_estrategias()`, define category assignments:
```python
STRATEGY_CATEGORIES = {
    "sma_crossover": ("\U0001f7e1 Swing", "bold yellow"),
    "bollinger_rsi": ("\U0001f7e1 Swing", "bold yellow"),
    "momentum_atr": ("\U0001f7e1 Swing", "bold yellow"),
}
```

Render category headers as separate sections in the table. Add category column. Predefined strategies get categories; user strategies default to "Personalizadas". Future FASE 18.3 strategies slot into their categories.

- **Pros**: Simple, no structural changes, Rich tables support section headers naturally
- **Cons**: Category assignment is hardcoded (not user-configurable)
- **Effort**: Low

### Approach B for Menu Reorganization: Nested submenu per category

Add an intermediate screen: list categories → pick one → show category strategies. Like a tree menu.

- **Pros**: Clean hierarchy, scales well to 15+ strategies
- **Cons**: More navigation required, slower to access, more code
- **Effort**: Medium

### Recommendation for Menu Reorganization

**Approach A** (colored category table in existing `_show_estrategias()`): Minimizes UI disruption while clearly grouping strategies. The 12 new strategies in FASE 18.3 will be visible in their categories. The existing flat table can be enhanced with colored rows/sections.

---

### Universe Switching (U key)

**Single approach**: Add a `"U"` command in `_print_menu()` that cycles through universe types (`"all"` → `"etfs"` → `"crypto"` → `"sp500"`), writes the new value to `SCANNER_UNIVERSE` env var (or a signal file), and displays the current universe in the header.

- **Effort**: Low
- Implementation in menu + orchestrator must pick up the change on next scan cycle

## Recommendation

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Dual param mechanism | **Approach 1** — optional `symbol` in `generate_signal(symbol=None)` | Cleanest, matches requirement, backward-compatible |
| Menu reorganization | **Approach A** — category table with colored headers | Scales well, minimal code, visible categorization |
| Universe switching | **Single key 'U' in main menu** | Simple, non-invasive |

## Risks

1. **Backward compat of `generate_signal()`**: If any code outside the scanner/orchestrator calls `generate_signal(data)` without `symbol`, the dual params must default to stock profile (sensible fallback). All existing tests pass unchanged.

2. **`get_parameters()` reflects current active profile**: When the menu displays params, it will show whatever profile was last used. Need to decide: show both profiles? Show active only? The `get_parameters()` method should probably return the full config (both profiles) so the menu can display them clearly.

3. **Timeframe dual params**: Crypto often uses shorter timeframes (e.g., `15min`, `1h`) vs stocks (`1d`, `5min`). The scanner currently downloads daily bars only (`TimeFrame.Day`). If crypto uses intraday timeframes, the scanner needs to support different timeframes per symbol group. This is **out of scope** for FASE 18.2 but should be noted.

4. **`get_parameters()` serialization**: The orchestrator publishes params to `logs/strategies.json`. With dual params, this needs to include both profiles or resolve to the active profile. Menu `_get_strategy_params_summary()` builds display from this data.

5. **User strategies (DynamicStrategy)**: Not affected directly, but `DynamicStrategy` also uses `generate_signal(data)` — its signature doesn't change since `symbol` is optional.

6. **Legacy path in orchestrator** (`_run_legacy_loop`, line 1450): Uses `generate_signal(data)` without symbol. Will default to stock params — acceptable for legacy mode which only trades SPY.

## Ready for Proposal

**Yes** — all affected files are identified, all approaches have clear tradeoffs, and the recommended path is well-defined. The orchestrator can proceed to `sdd-propose` with confidence.

### What the orchestrator should tell the user:

> La exploración está completa. Se identificaron **7 archivos a modificar** más tests. La estrategia recomendada es:
> 1. **Parámetros duales**: Agregar `symbol: Optional[str] = None` a `generate_signal()` en `BaseStrategy` — las 3 estrategias almacenan ambos perfiles y seleccionan en cada llamada vía `is_crypto_symbol(symbol)`
> 2. **Menú**: Categorías coloreadas en la tabla de estrategias + tecla 'U' en menú principal para cambiar universo
> 3. **Scanner**: Pasar `symbol` a `generate_signal()` en el loop de escaneo
> 
> La implementación no debería exceder ~250 líneas modificadas. Riesgo bajo.
