# Design: FASE 17.5 — Corrección de 6 bugs detectados en pruebas con Binance Testnet

## Technical Approach

Six isolated bug fixes, grouped into 3 chained PRs by risk and affected layer. No new modules, no new capabilities—only corrections to existing code paths. Each fix is a single commit touching at most 2 files.

## Architecture Decisions

### Decision: `_download_data()` accepts optional `broker` param (Bug 5)

**Choice**: Add `broker: Optional[BaseBroker] = None` to `_download_data()`, passed from `run_backtest()` — which already receives `config` but not broker wiring. The broker will be resolved at the call site in `_quick_backtest()` via a function-level import of a cached `BinanceBroker` from the calling context.

**Alternatives**: Global broker registry, env-var-based factory. Both add complexity for a single routing rule.
**Rationale**: Minimal diff (< 10 lines). The caller (`_quick_backtest` / `_builder_flow`) already has `logs_dir` access — can wire the broker there without new singletons.

### Decision: `config.setdefault("version", 1)` in `_quick_backtest()` (Bug 4)

**Choice**: Add `config.setdefault("version", 1)` one line before `validate_config(config)` in `_quick_backtest()`. This mutates the passed config dict safely because all callers pass a local or deep-copied config.

**Alternatives**: Modify `validate_config()` to accept missing version. Risk: would change schema validation contract for all callers.
**Rationale**: Targeted fix at the only crash site (the quick-backtest flow). Other callers always provide version.

### Decision: Sync `status.json` rewrite after resume (Bug 6)

**Choice**: In `_show_control()`, after `resume_bot(logs_dir)` returns, immediately write `{logs_dir}/status.json` with `{"bot_status": "ONLINE", "paused": false, "timestamp": "..."}` using the existing `_atomic_write` pattern imported from `orchestrator.py`.

**Alternatives**: Sleep + polling loop. Unreliable.
**Rationale**: The orchestrator's `_publish_status()` is async and called on its loop cycle. Writing a synchronous status.json directly mirrors the orchestrator's format and ensures the menu's next `_print_header()` / `_is_bot_paused()` read reflects the true state.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/royaltdn/frontend/menu/app.py` | Modify | Bugs 1, 3, 4, 6 — filter mock entries, crypto default symbol, version setdefault, thread logs_dir + sync status.json |
| `src/royaltdn/scanner/filters.py` | Modify | Bug 2 — NaN/empty DataFrame guard before volume mean |
| `src/royaltdn/strategy/backtesting.py` | Modify | Bug 5 — `_download_data()` routes `/` symbols to `broker.get_bars()` |
| `src/royaltdn/orchestrator.py` | Inspect | Ensure `_publish_status()` writes `status.json` on resume path (no change needed — already correct) |

## Data Flow

```
Bug 1: last_scan["top_signals"] ──filter(strategy!="mock")──→ _render_signals_table()
                                                              ↓ empty → "No hay resultados…"
Bug 2: LiquidityFilter.filter() ──df.empty? → skip
                                   df.volume.allNaN? → skip + debug log
Bug 3: _quick_backtest() ──os.getenv("SCANNER_UNIVERSE")=="crypto"? → "BTC/USDT" : "SPY"
Bug 4: _quick_backtest() ──config.setdefault("version",1)──→ validate_config(config)
Bug 5: _download_data() ──"/" in symbol? ──Yes→ broker.get_bars()───→ normalized DataFrame
                                              No → yfinance (unchanged)
Bug 6: resume_bot() ──pause_signal.json──→ write status.json sync──→ _is_bot_paused() reads updated file
```

## Interfaces / Contracts

### `backtesting._download_data()` modified signature

```python
def _download_data(
    symbol: str,
    timeframe: str,
    period: str,
    max_retries: int = 2,
    broker: Optional[BaseBroker] = None,  # NEW
) -> Optional[pd.DataFrame]:
```

When `broker` is provided and `"/" in symbol`, uses `broker.get_bars()`. Normalizes the returned DataFrame to match yfinance column names (lowercase: `open`, `high`, `low`, `close`, `volume`).

### `LiquidityFilter.filter()` — NaN guard

Before `avg_volume = df["volume"].mean()`, add:
```python
if df.empty or df["volume"].isna().all():
    logger.debug("LiquidityFilter: empty/all-NaN data for {} — skipping", symbol)
    continue
```

### `_print_header()` now threads `logs_dir`

```python
def _print_header(console, logs_dir: str = "logs") -> None:
    ...
    if _is_bot_paused(logs_dir=logs_dir):
```

All callers already have `logs_dir` available in scope. Non-breaking — `logs_dir` has a default.

## Testing Strategy

| Bug | Layer | Approach |
|-----|-------|----------|
| 1 | Unit | Mock `last_scan["top_signals"]` with/without mock entries; verify filtered output / empty state |
| 2 | Unit | Test `LiquidityFilter.filter()` with empty DataFrame and NaN volume — verify skip + no crash |
| 3 | Unit | Monkeypatch `os.getenv("SCANNER_UNIVERSE")` → verify `default_symbol` resolution |
| 4 | Unit | Call `_quick_backtest` with config missing `version`; verify no validation crash |
| 5 | Integration | Mock `BinanceBroker.get_bars()`; call `_download_data("BTC/USDT")` → verify broker called, not yfinance |
| 6 | Unit | Mock `_is_bot_paused` with/without `logs_dir`; verify header state matches status.json |

## Migration / Rollout

No migration required. Each PR is independently revertible. PR #3 (Bugs 2, 5) needs manual smoke test against Binance Testnet before merging.

## Chained PR Map

| PR | Bugs | Changed Files | Est. Lines | Risk |
|----|-------|--------------|-----------|------|
| #1 | 1, 3, 4 | `app.py` | ~20 | Low |
| #2 | 6 | `app.py` | ~15 | Low |
| #3 | 2, 5 | `filters.py`, `backtesting.py` | ~50 | Medium |

## Scope Refinement from Proposal

The proposal listed 7 files; design narrowed to 3 + 1 inspect-only. Rationale:
- `main.py`: Conditional crypto LiquidityFilter params (`_crypto_mode`) are already correct — no code change needed.
- `schema.py`: Bug 4 fixed at call site (`config.setdefault("version", 1)` in `_quick_backtest`) rather than modifying the shared schema validator.
- `binance.py`: `get_bars()` already exists and works — no method visibility changes needed for the call-site wiring.

## Open Questions

- [ ] Bug 5: Should `run_backtest()` accept a `broker` parameter directly, or resolve it inside `_download_data()` via a module-level cache? Current design adds `broker=None` to `_download_data()` only — called from `run_backtest()` which would need to pass it through. **Resolution**: `run_backtest()` receives an optional `broker` param and forwards it to `_download_data()`. The caller (`_quick_backtest` or `_builder_flow`) creates a lightweight BinanceBroker from env vars when the symbol is crypto. This avoids adding a global cache.
