# Design: FASE 18.4 — Scanner verbose + intervalo dinámico + validación dinero real

## Technical Approach

Extract `_compute_indicators()` from each strategy's `generate_signal()` so both it and the new `explain()` share the same computation — zero duplication risk. Add `scan(verbose=True)` to store explanations and write to `logs/scanner_verbose.log`. UI gets a two-level mode (L1 compact dashboard, L2 decision tree). Dynamic interval calculates from active strategy categories. Scalping auto-disables via `_cycle_universe()` in app.py, directly mutating `strategies.json` with no orchestrator involvement. `check-readiness` runs as a standalone CLI command with StateLoader + broker pings.

## Architecture Decisions

### Decision: `explain()` is a CONCRETE method (not `@abstractmethod`)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `@abstractmethod` with docstring default | Forces override — 17 strategies MUST implement before any PR merges; causes instantiation errors in chained PRs | ❌ |
| Concrete method with default return `{"indicators": {}, "conditions": [], "signal": None}` | Backward compatible; strategies without `explain()` still work; scanner checks `hasattr()` before calling | ✅ |

**Rationale**: `@abstractmethod` and "default return" are mutually exclusive — the abstract decorator means the default never runs. A concrete default enables incremental PR chaining: each PR adds `explain()` to a subset of strategies without breaking the rest. The scanner uses `if hasattr(strategy, 'explain')` as a safety gate.

### Decision: Scalping disable in app.py `_cycle_universe()` (NOT orchestrator)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Orchestrator `_build_strategies_list(universe)` filters at publish time | Race window: strategies.json shows scalping active between universe change and next orchestrator publish cycle | ❌ |
| app.py `_cycle_universe()` directly mutates `strategies.json` | Immediacy matches spec; app.py already owns the universe change flow; no cross-thread coordination needed | ✅ |

**Rationale**: The spec says "This SHALL happen inside the `_cycle_universe()` handler before the strategy list is persisted." The orchestrator operates on its own cycle and may take minutes to republish. Direct write from app.py closes the window immediately. The orchestrator's `_build_strategies_list()` simply reads whatever is in `strategies.json` — it publishes, it doesn't decide.

### Decision: `_compute_indicators(data, symbol=None)` — uniform signature

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Mixed: `data` only for simple, `data, symbol` for complex | Inconsistent pattern, harder to review, every call needs `inspect.signature` | ❌ |
| ALL strategies use `_compute_indicators(data, symbol=None)` | Uniform template; strategies ignoring symbol simply drop it; matches `generate_signal()` existing pattern | ✅ |

**Rationale**: Several strategies (momentum_atr, sma_strategy, intraday_trend, etc.) already use `symbol` in `generate_signal()` for profile resolution. Standardizing the same parameter on `_compute_indicators()` keeps signatures congruent. Strategies that don't need symbol ignore the param.

### Decision: Module-level `SCANNER_INTERVAL_MINUTES` replaced by dynamic function

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Keep module-level constant + dynamic calc | Module-load evaluation creates zombie constant that diverges from live state | ❌ |
| `_get_scan_interval_override()` function called each cycle | Single source of truth; env var checked live; backward compatible; constant removed | ✅ |

**Rationale**: Line 77 `SCANNER_INTERVAL_MINUTES = int(os.getenv(...))` evaluates once at import. The design's dynamic interval creates a second mechanism. Converging to a function eliminates the zombie. The function returns `int | None` so callers use dynamic calc as primary, override as fallback.

### Decision: 5 PRs (split PR-3 to stay under 400-line budget)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| 4 PRs as originally planned | PR-3 ~550-650 lines, exceeds 400-line review budget | ❌ |
| 5 PRs: split intraday(PR3a) and swing+all17(PR3b) | Each under 400 lines; reviewer can focus on one category at a time | ✅ |

**Rationale**: 5 intraday + 2 swing + 1 all-17 iteration test generates ~550-650 lines. Splitting into PR3a (5 intraday ~350 lines) and PR3b (3 swing + file_change_map + all-17 test ~300 lines) keeps every PR reviewable.

## Data Flow

```
User CLI --verbose flag
  │
  ▼
main.py: parser → scanner.verbose = True
  │
  ├── scan(verbose=True)
  │   ├── strategy.explain(data) per (symbol, strategy)
  │   ├── stored in scanner._last_explanations
  │   └── written to logs/scanner_verbose.log
  │   └── user reads L1/L2 via app.py
  │
  ├── dynamic interval
  │   └── orchestrator._run_legacy_loop()
  │       ├── _calc_scan_interval() per cycle
  │       │   ├── _get_scan_interval_override() → env var
  │       │   └── else: categories → min interval
  │       ├── recalc scanner_iterations per cycle
  │       └── publish in status.json["scanner_interval_minutes"]
  │
  ├── scalping disable
  │   └── app.py _cycle_universe()
  │       ├── if new_universe not in ("crypto",):
  │       │   → read strategies.json
  │       │   → for each category="scalping": active=False
  │       │   → write strategies.json (atomic write)
  │       │   → log warning
  │       └── if new_universe == "crypto": do nothing (no auto-reactivate)
  │
  └── check-readiness
      └── main.py: cmd_check_readiness()
          ├── StateLoader → trades (≥50), equity (Sharpe>0.5)
          ├── Path(bot.log).read_text() → kill switch, Telegram
          ├── AlpacaBroker.get_account(), Binance ping
          └── Rich Panel + verdict
```

## File Changes

### PR 1: BaseStrategy.explain() concrete + 5 existing strategies + scanner base (~380 lines)

### PR 2: 5 scalping strategies `explain()` (~350 lines)

### PR 3a: 5 intraday strategies `explain()` (~350 lines)

### PR 3b: 3 swing strategies + all-17 test + file_change_map.md (~300 lines)

### PR 4: UI (verbose L1/L2/dynamic interval/scalping notification) + scalping disable wire + `_get_scan_interval_override` + check-readiness + tests (~380 lines)

## Interfaces / Contracts

### explain() return dict (CONCRETE default)

```python
# In BaseStrategy:
def explain(self, data: pd.DataFrame, symbol: Optional[str] = None) -> Dict[str, Any]:
    """Explain why a signal was (or was not) generated.

    Returns dict with:
      - "indicators": computed indicator values
      - "conditions": list of condition checks with gap_pct
      - "signal": signal dict or None

    Concrete default for backward compatibility.
    Strategies MAY override to provide detailed explanations.
    """
    return {"indicators": {}, "conditions": [], "signal": None}

# Override pattern:
{
    "indicators": {
        "sma_fast": 150.25,
        "sma_slow": 148.10,
    },
    "conditions": [
        {
            "name": "sma_fast > sma_slow",
            "met": True,
            "value": 150.25,
            "threshold": 148.10,
            "gap_pct": 0.0,
            "direction": "above",
        },
    ],
    "signal": {              # None if no signal
        "action": "BUY",
        "price": 150.50,
        "reason": "Golden cross detected",
    },
}
```

### _compute_indicators() uniform signature

```python
def _compute_indicators(
    self,
    data: pd.DataFrame,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute strategy-specific indicators.

    Args:
        data: OHLCV DataFrame.
        symbol: Optional, for profile resolution (crypto vs stocks).

    Returns:
        Dict of indicator name → value.
    """
```

### gap_pct calculation

```python
def _calc_gap(value: float, threshold: float, direction: str) -> float:
    if direction == "above":
        if value >= threshold:
            return 0.0
        return abs((value - threshold) / threshold) * 100
    else:  # below
        if value <= threshold:
            return 0.0
        return abs((value - threshold) / threshold) * 100
```

### Dynamic interval pseudocode

```python
def _get_scan_interval_override() -> int | None:
    """Read SCANNER_INTERVAL_MINUTES env var. Returns None if not set or invalid."""
    import os
    raw = os.getenv("SCANNER_INTERVAL_MINUTES", "")
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    if raw and raw != "":
        logger.warning("SCANNER_INTERVAL_MINUTES invalid ({}), using auto", raw)
    return None

def _calc_scan_interval(self) -> int:
    override = _get_scan_interval_override()
    if override is not None:
        return override

    categories = set()
    for s in self._build_strategies_list():
        if s.get("active", True):
            categories.add(s.get("category", "swing"))

    if "scalping" in categories:    return 2
    if "intraday" in categories:    return 15
    if "swing" in categories:       return 240
    return 60
```

### scalping-disable in _cycle_universe()

```python
def _cycle_universe() -> str:
    """Rotate universe and disable scalping if non-crypto."""
    global _current_universe
    idx = (_UNIVERSE_CYCLE.index(_current_universe) + 1) % len(_UNIVERSE_CYCLE)
    new_uni = _UNIVERSE_CYCLE[idx]
    _current_universe = new_uni

    if _universe_setter is not None:
        _universe_setter(_current_universe)

    # Scalping auto-disable: immediately write strategies.json
    if new_uni != "crypto":
        _disable_scalping_in_strategies_json()
    # NOTE: crypto universe does NOT auto-reactivate — user toggles manually

    return _current_universe

def _disable_scalping_in_strategies_json() -> None:
    """Read strategies.json, set active=False for scalping, write back."""
    import json, os
    path = os.path.join("logs", "strategies.json")
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return

    modified = False
    for s in data.get("strategies", []):
        if s.get("category") == "scalping" and s.get("active", False):
            s["active"] = False
            modified = True

    if modified:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        from loguru import logger
        logger.warning("Scalping desactivado por cambio de universo a {}", _current_universe)
```

### check-readiness check structure

```python
{
    "name": "Trades suficientes",
    "passed": True,
    "detail": "52/50 trades",
    "severity": "critical",  # or "warning"
}
```

Verdict logic: all passed → READY (exit 0), 0 critical + warning fails → CASI LISTO (exit 1), 1+ critical fail → NO RECOMENDADO (exit 2).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `explain()` on each strategy | Assert return dict has indicators, conditions, signal keys. Assert met/not-met match `generate_signal()` |
| Unit | `_compute_indicators()` extraction | `generate_signal()` delegates to `_compute_indicators()` — mock indicators to verify |
| Unit | gap_pct calculation | Parametrized: value=100, threshold=110, direction="above" → 9.09% |
| Unit | Dynamic interval | Override strategies list, assert correct interval per category mix |
| Unit | `_get_scan_interval_override()` | Set env var → assert override, unset → assert None |
| Unit | Scalping disable in app.py | Mock strategies.json, call _cycle_universe() to non-crypto → assert scalping disabled; to crypto → assert unchanged |
| Unit | check-readiness | Mock StateLoader/broker pings, assert 6 checks, 3 verdict variants |
| Integration | Scanner `scan(verbose=True)` | 3 strategies × 2 symbols → assert `_last_explanations` has 6 entries, log file written |
| Integration | `--verbose` CLI flag | `main()` with `--verbose` → scanner.verbose=True |

## Migration / Rollout

No migration required. The module-level `SCANNER_INTERVAL_MINUTES` constant in `orchestrator.py` line 77 is replaced by `_get_scan_interval_override()` — existing env var users are unaffected. The constant is removed.

## Open Questions

None — all critical issues resolved.
