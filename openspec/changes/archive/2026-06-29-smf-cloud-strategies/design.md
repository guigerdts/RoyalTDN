# Design: SMF Cloud + Adaptive Trailing + 12 Replacement Strategies

## Technical Approach

Single-pass SMF pipeline cached per evaluation cycle, 5 thin wrapper indicators in `_INDICATORS`, adaptive trailing as a new `_check_exit()` branch keyed on optional `min_mult`/`max_mult` YAML params. Shared SMF params (`flow_len`, `ema_period`, `atr_period`) enforced via post-hoc override in the Optuna objective function. 12 strategy YAML blocks across 3 files using SMF + existing indicators (RSI, BB, EMA, ADX).

## Architecture Decisions

### Decision 1: SMF Memoization Strategy

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Accept 5× recomputation per evaluate() | Simple, wastes ~15 pandas ops per bar | ❌ Rejected — too much waste |
| `@lru_cache` on `_compute_smf` | Needs hashable data; lists aren't | ❌ Rejected — cache miss every new bar anyway |
| Module-level `_smf_cache` keyed by `(id(data), flow_len, ema_period, atr_period)` | Cache hits within same evaluate() cycle because all conditions share the same data dict. Cleared when `len > 10`. | ✅ **Chosen** — <10 lines, zero correctness risk |

Implementation: `_compute_smf()` writes to `_smf_cache[ (id(data), flow_len, ema_period, atr_period) ]` and returns cached on hit. Cache cleared when `len > 10` (leak guard). Since `_build_data()` returns a new dict each bar, `id(data)` changes next cycle → 1 computation per bar regardless of condition count.

### Decision 2: Adaptive Trailing in `_check_exit()`

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New `adaptive_trailing` exit type | Parse new type in `_parse_exit_rules`, add new `elif` branch | ❌ Over-engineered |
| Reuse `trailing_stop` with optional `min_mult`/`max_mult` | Existing `trailing_stop` (ATR) branch gets a third variant. Absent params → unchanged behavior. | ✅ **Chosen** — zero backward compat risk |

Flow: `_parse_exit_rules()` reads `min_mult`/`max_mult` from trailing_stop params. `_check_exit()` checks for `exit_trailing_min_mult is not None` between the pct-trailing and ATR-trailing branches. Calls `_compute_smf(self._build_data())["strength"]` when bars ≥ 20 (same guard as entry).

### Decision 3: Shared-Optimizer Params

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Per-condition independent | Each condition optimizes `flow_len` separately → inconsistent SMF cloud across conditions within same cell | ❌ Conceptually wrong |
| Single canonical Optuna key + post-hoc expansion | `suggest_params()` shares one `trial.suggest_int("smf_shared.flow_len")` across all SMF conditions; `apply_params()` receives per-condition keys | ✅ **Chosen** |

`_SMF_SHARED_PARAMS = {"flow_len", "ema_period", "atr_period"}`. In `suggest_params()`, first SMF condition suggests via canonical key; subsequent SMF conditions reuse from `shared_cache` dict. `best_params` has both canonical and per-condition keys → `apply_params()` handles per-condition keys as today.

### Decision 4: Strategy Cells Per Timeframe

| File | Timeframe | Cell 1 | Cell 2 | Cell 3 | Cell 4 |
|------|-----------|--------|--------|--------|--------|
| `scalping.yaml` | 15m | SMF retest + RSI `< 40` | SMF breakout + vol surge | SMF reversion + BB lower | SMF flow > 0.6 + EMA |
| `intraday.yaml` | 1h | SMF basis + EMA(50) | SMF basis + ADX > 25 | SMF lower + BB lower reversion | SMF strength > 0.5 + RSI > 55 |
| `swing.yaml` | 1d | SMF lower + BB lower reversion | SMF basis + RSI `< 35` | SMF strength > 0.5 + ADX > 30 | SMF strength > 0.4 + EMA(100) |

All cells have inverted `short_entry`. Exit types: scalping/intraday use adaptive trailing (`min_mult: 0.8, max_mult: 2.5`); swing uses wider adaptive trailing (`min_mult: 0.7, max_mult: 3.0`) plus fixed take-profit.

## Data Flow

```
Cell.handle(bar)
  │
  ▼
_build_data()  ──→  {close, high, low, volume} lists  ──→  1 dict obj
  │                                                              │
  ▼                                                              ▼
_entry_graph.evaluate(data)                                _check_exit(data)
  │                                                              │
  ├─ smf_flow → _compute_smf(data) → cache[(id, p1,p2,p3)]      │
  ├─ smf_strength → _compute_smf(data) → cache HIT               │
  └─ smf_lower → _compute_smf(data) → cache HIT                  │
  │                                                              │
  ▼                                                              ▼
signal {BUY/SELL}                                          adaptive_mult(strength) × atr
  │                                                              │
  └────────────────────── RiskManager ───────────────────────────┘
```

## File Changes

| File | Action | Δ |
|------|--------|---|
| `src/royaltdn/inference/conditions.py` | Modify | +~150 lines: `_compute_smf`, 5 wrappers, `adaptive_mult`, `_INDICATORS` update, `_smf_cache` |
| `src/royaltdn/cells/base.py` | Modify | ~+30 lines: `_parse_exit_rules` reads `min_mult`/`max_mult`; `_check_exit` adaptive trailing branch |
| `src/royaltdn/scripts/optimize.py` | Modify | ~+20 lines: `_SMF_SHARED_PARAMS`, `shared_cache` in `suggest_params`, 5 `_PARAM_RANGES` entries |
| `src/royaltdn/cells/templates/scalping.yaml` | Modify | 4 strategy blocks replaced |
| `src/royaltdn/cells/templates/intraday.yaml` | Modify | 4 strategy blocks replaced |
| `src/royaltdn/cells/templates/swing.yaml` | Modify | 4 strategy blocks replaced |
| `tests/test_indicators.py` | New | SMF unit tests + adaptive_mult |
| `tests/test_backtesting.py` | Modify | Add adaptive trailing integration test |

## Interfaces / Contracts

```python
# conditions.py additions
def _compute_smf(data, flow_len=24, ema_period=34, atr_period=14) -> dict[str, float]:
    """Returns {clv, raw_flow, mf, strength, mult, basis, atr, upper, lower}.
    Empty dict on insufficient data. Cached per (id(data), params)."""

def smf_flow(data, flow_len=24, ema_period=34, atr_period=14) -> float: ...
def smf_strength(data, flow_len=24, ema_period=34, atr_period=14) -> float: ...
def smf_basis(data, flow_len=24, ema_period=34, atr_period=14) -> float: ...
def smf_upper(data, flow_len=24, ema_period=34, atr_period=14) -> float: ...
def smf_lower(data, flow_len=24, ema_period=34, atr_period=14) -> float: ...

def adaptive_mult(strength: float, min_mult: float = 0.9, max_mult: float = 2.2) -> float:
    """min_mult + (max_mult - min_mult) * clamp(strength, 0, 1)."""

# YAML exit schema (backward compatible):
# trailing_stop with optional min_mult/max_mult → adaptive
```

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Unit | `_compute_smf` with synthetic OHLCV | Feed known close/high/low/volume, assert MF=0.5 for close near high, MF=-0.5 for close near low |
| Unit | 5 wrappers | Verify each extracts correct dict field; 0.0 on empty dict |
| Unit | `adaptive_mult` | Clamping: strength=0 → min_mult, strength=1 → max_mult, strength=0.5 → midpoint, NaN → min_mult |
| Unit | Cache | Same data object → cache hit; new data → cache miss; 10-entry cleanup |
| Unit | Shared params | `suggest_params` with 2 SMF conditions → same `flow_len` value |
| Integration | YAML-based SMF cell | `load_cells` from test YAML, verify graph evaluates with SMF indicators |
| Integration | Adaptive trailing | Backtest with SMF trailing stop, verify exit uses scaled ATR multiplier |
| Regression | Existing strategies | Backtest `swing_reversion` before/after → identical equity curve |

## Migration / Rollout

No migration required. New YAML cells are independent; existing cells unchanged. Rollback: `git checkout -- src/royaltdn/cells/templates/*.yaml`.

## Open Questions

- [ ] Should `_compute_smf` log warnings on volume=0 rows? Edge case in illiquid 15m symbols.
- [ ] `adaptive_mult` function — register in `_INDICATORS` or keep as raw import for `_check_exit` only? (Design: not in `_INDICATORS`, it's an internal utility not evaluable from YAML conditions.)
