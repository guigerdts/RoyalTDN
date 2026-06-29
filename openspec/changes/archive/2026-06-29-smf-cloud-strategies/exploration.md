## Exploration: smf-cloud-strategies

### Current State

**conditions.py** (`src/royaltdn/inference/conditions.py` — 896 lines):

- **Indicator pattern**: standalone functions taking `data: Any` (dict or Series) + typed params. Return either `float` (numeric: `bollinger_upper`, `vwap`, `ema`) or `bool` (boolean: `volume_surge`, `range_breakout`).
- **Registry**: `_INDICATORS` dict at line 766 maps string names → function objects. All 17 indicators follow this.
- **Evaluation**: `evaluate()` supports two paths:
  - *Simple operator*: `> 30` → calls indicator function, compares to threshold
  - *Compound operator*: `price > bollinger_lower` → `_resolve_value` resolves both sides (supporting `price`, indicator names, and numeric literals)
  - Compound operators use `_OPERATOR_RE` regex at line 789
- **Helpers**: `_safe_numeric(series, min_length)`, `_to_series(data, key)` for type normalization. All functions handle edge cases (insufficient data → 0.0/False, div-by-zero → 0.0/False).

**cells/base.py** (`src/royaltdn/cells/base.py` — 693 lines):

- `Cell` class: per-symbol, per-timeframe autonomous agent. Reads YAML config at init.
- `entry_config`: dict with `logic` (AND/OR) and `conditions` (list of indicator configs)
- Conditions pre-built as graph: `build_graph(entry_config)` → `LogicNode` tree
- Exit rules parsed from `exit` list: supports `stop_loss`, `take_profit`, `trailing_stop`, `zscore` — each with `pct` or `atr_multiplier` params
- `_build_data()`: builds `{close, volume, high, low}` dict from bar history (min 20 bars)
- No multi-timeframe support in a single cell — each cell tracks one timeframe

**cells/loader.py** (`src/royaltdn/cells/loader.py` — 257 lines):

- Reads `*.yaml` from `templates/` directory, expands multi-symbol configs into one Cell per symbol
- Supports `enabled_strategies`/`disabled_strategies` filtering
- Each YAML doc yields one or more Cell instances

**YAML templates** (`src/royaltdn/cells/templates/`):

- Three files: `scalping.yaml` (1m), `intraday.yaml` (5m-30m), `swing.yaml` (1d)
- Each strategy: `name`, `symbol(s)`, `timeframe`, `entry` (logic + conditions), `short_entry`, `exit` (list), `risk`
- Conditions pattern: `{indicator: name, params: {p1: v1}, operator: "> X"}` or compound `"price > indicator"`

**inference/graph.py** (`src/royaltdn/inference/graph.py` — 140 lines):

- `ConditionNode`: leaf, calls `evaluate(indicator, params, operator, data)`
- `LogicNode`: composite, combines children with AND/OR/NOT
- `build_graph(entry_config)` → root LogicNode with full tree
- Supports nested logic: `AND` at root, `OR` within conditions list

**scripts/optimize.py** (`src/royaltdn/scripts/optimize.py`):

- `suggest_params`: walks `entry.conditions[].params`, `exit[].params`, `risk` with flat keys like `entry.{idx}.{indicator}.{param}`
- `_PARAM_RANGES` dict: maps param name → `(type, low, high, step)` for Optuna suggestions
- `_EXCLUDED_PARAMS = {"indicator", "operator", "type", "logic", "conditions"}` — structural fields skipped
- `apply_params`: writes optimized values back to deep-copied config
- Handles compound exit keys like `stop_loss.pct` via `context_key`
- New params like `flow_len`, `ema_period`, `min_mult`, `max_mult` need entries in `_PARAM_RANGES`

### Affected Areas

| File | Why Affected | Change Type |
|------|-------------|-------------|
| `src/royaltdn/inference/conditions.py` | Add 5 SMF indicator functions + `adaptive_mult` utility | Add ~150 lines |
| `src/royaltdn/cells/templates/intraday.yaml` | Add 3 SMF Cloud strategies (15m, 1h) | Add strategy blocks |
| `src/royaltdn/cells/templates/swing.yaml` | Add SMF Cloud strategy (1d) | Add strategy block |
| `src/royaltdn/scripts/optimize.py` | Add `_PARAM_RANGES` entries for new SMF params | Modify ~10 lines |
| `src/royaltdn/inference/conditions.py` (tests) | Unit tests for SMF indicators and `adaptive_mult` | New test file |
| `src/royaltdn/cells/base.py` | (Optional) Exit logic enhancement to use `adaptive_mult` for dynamic trailing stops | Modify if desired |

### Implementation Approach

#### 1. adaptive_mult — Reusable Utility

Pure function, NOT an indicator. Best home: `conditions.py` as a module-level function (since all conditions code lives there and it's the only module the inference engine imports).

```python
def adaptive_mult(strength: float, min_mult: float = 0.9, max_mult: float = 2.2) -> float:
    """Calculate adaptive band multiplier from flow strength.
    
    Maps strength in [0, 1] to multiplier in [min_mult, max_mult].
    
    Args:
        strength: Normalized flow strength (0-1).
        min_mult: Minimum multiplier (widest band).
        max_mult: Maximum multiplier (tightest band).
    
    Returns:
        Adaptive multiplier value.
    """
    strength = max(0.0, min(1.0, strength))
    return min_mult + (max_mult - min_mult) * strength
```

#### 2. SMF Core Computation — Shared helper

A private `_compute_smf(data, flow_len, ema_period, atr_period)` that returns all computed values at once, so the 5 public indicators don't recompute everything independently.

```python
def _compute_smf(
    data: Any,
    flow_len: int = 24,
    ema_period: int = 34,
    atr_period: int = 14,
) -> dict[str, float]:
    """Compute all SMF Cloud values from market data.
    
    Returns dict with keys: clv, raw_flow, mf, strength, mult, basis, atr, upper, lower.
    Returns all zeros if insufficient data.
    """
```

#### 3. Five Indicator Functions

Each wraps `_compute_smf` and returns the relevant value:

| Function | Returns | Used In |
|----------|---------|---------|
| `smf_basis(data, flow_len=24, ema_period=34, atr_period=14) -> float` | EMA Basis | Compound op |
| `smf_upper(data, flow_len=24, ema_period=34, atr_period=14) -> float` | Upper band | Compound op |
| `smf_lower(data, flow_len=24, ema_period=34, atr_period=14) -> float` | Lower band | Compound op |
| `smf_flow(data, flow_len=24, ema_period=34, atr_period=14) -> float` | MF flow | Simple op |
| `smf_strength(data, flow_len=24, ema_period=34, atr_period=14) -> float` | Flow strength | Simple op |

**Important**: Params must be identical across all 5 for consistency. When one indicator's params change, all should change together. The optimizer will treat them independently per condition index.

#### 4. YAML Strategy Structure

Three new strategies across 3 timeframes. Example for 1h:

```yaml
name: smf_cloud_1h
enabled: true
symbols:
  - BTCUSDT
  - ETHUSDT
  - SOLUSDT
timeframe: 1h
max_hold_hours: 24
reentry_cooldown: 0
# Entry: price retests basis with flow > 0 and min strength
entry:
  logic: AND
  conditions:
    - indicator: smf_flow
      params:
        flow_len: 24
        ema_period: 34
        atr_period: 14
      operator: "> 0.0"
    - indicator: smf_strength
      params:
        flow_len: 24
        ema_period: 34
        atr_period: 14
      operator: "> 0.3"
    - indicator: smf_lower
      params:
        flow_len: 24
        ema_period: 34
        atr_period: 14
      operator: price > smf_lower
short_entry:
  logic: AND
  conditions:
    - indicator: smf_flow
      params:
        flow_len: 24
        ema_period: 34
        atr_period: 14
      operator: "< 0.0"
    - indicator: smf_strength
      params:
        flow_len: 24
        ema_period: 34
        atr_period: 14
      operator: "> 0.3"
    - indicator: smf_upper
      params:
        flow_len: 24
        ema_period: 34
        atr_period: 14
      operator: price < smf_upper
exit:
  - type: stop_loss
    params:
      atr_multiplier: 4.0  # default wide, adaptive mult will tighten
  - type: trailing_stop
    params:
      atr_multiplier: 2.0
risk:
  sizing: 0.01
  max_positions: 3
```

Same structure for 15m (timeframe: 15m, max_hold_hours: 8) and 1d (timeframe: 1d, max_hold_hours: 72).

**Note**: The exit rules currently use fixed `atr_multiplier`. Enhancing them with `adaptive_mult` would require modifying `_check_exit()` in `base.py` to call `adaptive_mult(strength)` — this is a separate, optional enhancement.

#### 5. Optimization Wiring

Add to `_PARAM_RANGES` in `optimize.py`:

```python
"flow_len": ("int", 10, 50, None),
"ema_period": ("int", 10, 60, None),
"atr_period": ("int", 7, 30, None),
"min_mult": ("float", 0.5, 1.5, 0.1),
"max_mult": ("float", 1.5, 4.0, 0.1),
```

No other changes needed — `suggest_params()` already walks all condition params generically.

### Risks

1. **Volume Data Quality**: SMF relies heavily on volume data (CLV × volume). On lower timeframes (15m), volume can be erratic for less liquid symbols. Consider requiring a minimum volume threshold or using median volume smoothing.

2. **Shared Parameter Consistency**: All 5 SMF indicators share `flow_len`, `ema_period`, `atr_period`. If optimized independently per condition index, the optimizer could produce inconsistent values (e.g., `smf_flow` optimized with `flow_len=30` but `smf_lower` with `flow_len=10`). This is architecturally valid but semantically wrong — the SMF Cloud is a single computation. Consider using Optuna's `suggest_int` with the same trial key across conditions (e.g., force `entry.0.smf_flow.flow_len` = `entry.2.smf_lower.flow_len`) or document this as a user concern.

3. **Computational Redundancy**: Each condition evaluation recomputes the full SMF pipeline (CLV → RawFlow → MF → Strength → Basis → ATR → bands). With 3 conditions per entry and 5 indicators, that's 15x the same computation per evaluation. The shared `_compute_smf` helper mitigates within a single call, but across conditions in the same evaluation it's still wasteful. Acceptable for 15m-1d strategies with low bar frequency.

4. **Multi-Timeframe Complexity**: Current architecture has one timeframe per cell. The 3 SMF strategies (15m, 1h, 1d) are independent cells with no cross-timeframe confirmation logic. True multi-timeframe confirmation (e.g., "enter on 15m when 1h trend aligns") would require a new architectural feature.

5. **Exit Logic Enhancement**: The `adaptive_mult` utility is straightforward, but wiring it into `_check_exit()` in `base.py` to dynamically calculate trailing stops is more involved. The exit rules currently use fixed `atr_multiplier` values. To use `adaptive_mult`, each exit rule would need to know the current `strength` — which means calculating MF at each tick during the position. This is a separate feature.

### Ready for Proposal

Yes — the approach is clear and well-understood. The orchestrator should proceed to `sdd-propose` with these findings.

Key points for the proposal:
- 5 new indicator functions + `_compute_smf` helper + `adaptive_mult` utility
- 3 new YAML strategy blocks (15m, 1h, 1d)
- 5 new entries in `_PARAM_RANGES`
- No changes to cells/base.py or inference/graph.py required for MVP
- The shared-parameter consistency risk (risk #2) needs a design decision before implementation
