# Tasks: Fix ticker-data ATR exits

## Overview

Three interrelated fixes across 5 files: (1) BinanceFeed switches from `@ticker` to `@kline_1m`, (2) 3 YAML templates get pct-based fallback exits on all SMF cells, (3) debug log in `_check_exit()` reveals ATR attributes.

---

## Task List

### Phase 1 — kline data source (binance_feed.py)

#### [x] T1: Add `interval` param to BinanceFeed.__init__

| Field | Value |
|---|---|
| **File** | `src/royaltdn/data/binance_feed.py` |
| **Type** | Edit |
| **Risk** | None (default param, backward compatible) |

**Changes:**
- Add `interval: str = "1m"` parameter after `testnet`
- Store as `self.interval`
- Update docstring to document the new param

**Acceptance criteria:**
- `BinanceFeed(symbols, bus)` works unchanged (default `"1m"`)
- `BinanceFeed(symbols, bus, interval="5m")` overrides interval
- Caller at `main.py:249` requires no change

---

#### [x] T2: Update `_build_url()` to stream `@kline_{interval}`

| Field | Value |
|---|---|
| **File** | `src/royaltdn/data/binance_feed.py` |
| **Type** | Edit |
| **Risk** | Low — URL structure identical, only stream name changes |
| **Depends on** | T1 |

**Changes:**
- Line ~60: change `f"{s.lower().replace('/', '')}@ticker"` to `f"{s.lower().replace('/', '')}@kline_{self.interval}"`

**Acceptance criteria:**
- URL becomes `wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m` (not `@ticker`)
- Custom interval produces correct URL: `@kline_5m`

---

#### [x] T3: Rewrite `_handle_message()` for kline schema

| Field | Value |
|---|---|
| **File** | `src/royaltdn/data/binance_feed.py` |
| **Type** | Edit (replace lines 135-167 body) |
| **Risk** | Medium — new message schema, but same event shape downstream |
| **Depends on** | T2 |

**Changes:**
- Detect kline message: `if "k" not in msg: return` (skip non-kline)
- Extract OHLCV from nested `k` object: `k["o"]`, `k["h"]`, `k["l"]`, `k["c"]`, `k["v"]`, `k["q"]`, `k["n"]`
- Add `_kline_start` field with `k["t"]` value
- Process ALL kline updates (ignore `k.x` closed flag)
- Update exception message from `"ticker message"` to `"kline message"`
- Keep exact same event shape: `{type, symbol, price, volume, timestamp, data{high, low, open, close, volume, quote_volume, count}}`

**Acceptance criteria:**
- Kline message → emits correct event with `price=float(k.c)`, `data.high=float(k.h)`, etc.
- Non-kline message (e.g. keepalive ping) → silently skipped, no exception, no event
- All kline updates processed regardless of `k.x` flag
- `_kline_start` present in event with `k.t` value
- Combined stream wrapper (`data` key) handled correctly

---

### Phase 2 — pct fallback exits (3 YAML templates)

#### [x] T4: Add pct fallback exits to swing.yaml SMF cells

| Field | Value |
|---|---|
| **File** | `src/royaltdn/cells/templates/swing.yaml` |
| **Type** | Edit (4 cells) |
| **Risk** | Low — YAML only, no logic change |
| **Depends on** | — (independent of Phase 1) |

**Cells to modify:**
1. `swing_smf_trend_bollinger` (trend)
2. `swing_smf_momentum_adx` (trend)
3. `swing_smf_reversion_zscore` (reversion)
4. `swing_smf_retest_rsi` (reversion)

**Cells NOT modified** (non-SMF, already have pct exits):
- `swing_reversion` — unchanged
- `swing_momentum` — unchanged

**Pct values:**

| Cell | Category | SL.pct | TP.pct | TS.pct |
|---|---|---|---|---|
| `swing_smf_trend_bollinger` | trend | 3.0 | 5.0 | 2.0 |
| `swing_smf_momentum_adx` | trend | 3.0 | 5.0 | 2.0 |
| `swing_smf_reversion_zscore` | reversion | 2.0 | 3.0 | — (stays ATR) |
| `swing_smf_retest_rsi` | reversion | 2.0 | 3.0 | — (stays ATR) |

**YAML insertion pattern** (trend cell example):
```yaml
exit:
  - type: stop_loss              # NEW: pct fallback
    params:
      pct: 3.0
  - type: take_profit            # NEW: profit target
    params:
      pct: 5.0
  - type: trailing_stop          # NEW: pct fallback
    params:
      pct: 2.0
  - type: trailing_stop          # EXISTING: ATR adaptive
    params:
      atr_multiplier: 2.0
      min_mult: 0.5
      max_mult: 1.5
  - type: stop_loss              # EXISTING: ATR-based
    params:
      atr_multiplier: 3.0
```

Reversion cells omit the pct trailing_stop entry (keep only SL + TP pct entries before existing ATR rules).

**Acceptance criteria:**
- All 4 SMF cells have `stop_loss.pct` and `take_profit.pct` entries before existing ATR entries
- Trend cells also have `trailing_stop.pct` entry
- `swing_reversion` and `swing_momentum` output identical to current
- YAML is valid (parseable by `yaml.safe_load`)

---

#### [x] T5: Add pct fallback exits to intraday.yaml SMF cells

| Field | Value |
|---|---|
| **File** | `src/royaltdn/cells/templates/intraday.yaml` |
| **Type** | Edit (4 cells) |
| **Risk** | Low — YAML only, no logic change |
| **Depends on** | — (independent) |

**Cells to modify:**
1. `intraday_smf_trend_adx` (trend)
2. `intraday_smf_momentum_volume` (trend)
3. `intraday_smf_retest_bollinger` (reversion)
4. `intraday_smf_zscore_reversion` (reversion)

**Cells NOT modified:**
- `intraday_volume_breakout` — unchanged

**Pct values:**

| Cell | Category | SL.pct | TP.pct | TS.pct |
|---|---|---|---|---|
| `intraday_smf_trend_adx` | trend | 1.5 | 2.5 | 1.0 |
| `intraday_smf_momentum_volume` | trend | 1.5 | 2.5 | 1.0 |
| `intraday_smf_retest_bollinger` | reversion | 1.0 | 2.0 | — (stays ATR) |
| `intraday_smf_zscore_reversion` | reversion | 1.0 | 2.0 | — (stays ATR) |

**Acceptance criteria:**
- All 4 SMF cells have pct entries before existing ATR entries
- `intraday_volume_breakout` output identical to current
- YAML is valid

---

#### [x] T6: Add pct fallback exits to scalping.yaml SMF cells

| Field | Value |
|---|---|
| **File** | `src/royaltdn/cells/templates/scalping.yaml` |
| **Type** | Edit (4 cells) |
| **Risk** | Low — YAML only, no logic change |
| **Depends on** | — (independent) |

**Cells to modify:**
1. `scalping_smf_retest_rsi` (reversion)
2. `scalping_smf_momentum` (trend/momentum)
3. `scalping_smf_breakout` (trend/momentum)
4. `scalping_smf_reversion` (reversion)

**Cells NOT modified:**
- `scalping_reversion` — unchanged

**Pct values:**

| Cell | Category | SL.pct | TP.pct | TS.pct |
|---|---|---|---|---|
| `scalping_smf_retest_rsi` | reversion | 0.6 | 1.2 | — (stays ATR) |
| `scalping_smf_momentum` | trend | 0.8 | 1.5 | 0.5 |
| `scalping_smf_breakout` | trend | 0.8 | 1.5 | 0.5 |
| `scalping_smf_reversion` | reversion | 0.6 | 1.2 | — (stays ATR) |

**Acceptance criteria:**
- All 4 SMF cells have pct entries before existing ATR entries
- `scalping_reversion` output identical to current
- YAML is valid

---

### Phase 3 — debug log fix

#### [x] T7: Expand debug log in `_check_exit()` with ATR attributes

| Field | Value |
|---|---|
| **File** | `src/royaltdn/cells/base.py` |
| **Type** | Edit (lines 419-426) |
| **Risk** | None — log-only, no logic change |
| **Depends on** | — (independent) |

**Changes:**
Replace the current `logger.debug()` format string (lines 419-426) with:

```python
logger.debug(
    "{} {} CHECK-EXIT price=${:.4f} entry=${:.4f} state={} "
    "SL_pct={} SL_ATR={} TP_pct={} TS_pct={} TS_ATR={} "
    "TS_min={} TS_max={} Z={} ATR={:.2f}",
    self.symbol, self.name, current_price, self.entry_price,
    self.state,
    self.exit_stop_loss_pct, self.exit_stop_loss,
    self.exit_take_profit_pct,
    self.exit_trailing_stop_pct, self.exit_trailing_stop,
    self.exit_trailing_min_mult, self.exit_trailing_max_mult,
    self.exit_zscore_threshold, atr if atr else 0.0,
)
```

Note: `atr` is already computed at line 428 in the current code — the log line needs to move AFTER `atr = self._calc_atr()` (currently it's before ATR computation at line 419-426). The `atr` variable must be available for the format args.

**Acceptance criteria:**
- Debug log shows `SL_ATR=3.0` for ATR-configured cells
- Debug log shows `SL_pct=0.04` for pct-configured cells
- Both visible when both configured (SMF after T4-T6)
- `atr` variable is defined before the log call (move log after `_calc_atr()`)
- Log line is a single line (no broken format)
- No logic change to exit evaluation

---

### Testing & Validation

#### [x] T8: Write unit test for kline parser

| Field | Value |
|---|---|
| **File** | `tests/test_binance_feed.py` (new) |
| **Type** | Create |
| **Risk** | Low |
| **Depends on** | T3 |

**Test cases:**

1. **test_kline_message_parses_correctly**
   - Input: kline message with known values
   - Assert: event has correct `type`, `symbol`, `price`, `volume`, `timestamp`
   - Assert: `data.high`, `data.low`, `data.open`, `data.close`, `data.volume`, `data.quote_volume`, `data.count`
   - Assert: `_kline_start` is present

2. **test_non_kline_message_skipped**
   - Input: message without `k` key
   - Assert: no event emitted, no exception raised

3. **test_combined_stream_format**
   - Input: message with `{"stream": "...", "data": {...kline...}}` wrapper
   - Assert: parsed correctly (combined stream sends `data` wrapper)

4. **test_all_candle_updates_processed**
   - Input: kline message with `x: false` (unclosed candle)
   - Assert: event emitted (not filtered by `x` flag)

**Acceptance criteria:**
- All 4 tests pass with `pytest tests/test_binance_feed.py -v`
- Tests use mocked `EventBus` to capture emitted events
- Tests do not require network

---

#### [x] T9: Validate syntax of all changed files

| Field | Value |
|---|---|
| **Type** | Validation |
| **Risk** | Low |
| **Depends on** | T1-T7 |

**Checks:**

```bash
# YAML validation
python -c "import yaml; yaml.safe_load(open('src/royaltdn/cells/templates/swing.yaml'))"
python -c "import yaml; yaml.safe_load(open('src/royaltdn/cells/templates/intraday.yaml'))"
python -c "import yaml; yaml.safe_load(open('src/royaltdn/cells/templates/scalping.yaml'))"

# Python syntax validation
python -m py_compile src/royaltdn/data/binance_feed.py
python -m py_compile src/royaltdn/cells/base.py

# Test pass
pytest tests/test_binance_feed.py -v
```

**Acceptance criteria:**
- All 3 YAML files parsed without error
- Both Python files compile without error
- All 4 test cases pass

---

## Dependencies

```
T1 (interval param) → T2 (url kline) → T3 (handle_message)
                                             ↓
                                          T8 (kline tests)
                                             ↓
T4 (swing yaml) ─┐                          
T5 (intraday yaml) ─┤  →  T9 (validation)
T6 (scalping yaml) ─┘
                  ↓
T7 (debug log) ────→  T9 (validation)
```

### Phase ordering

| Phase | Tasks | Files | Rationale |
|---|---|---|---|
| Phase 1 | T1 → T2 → T3 → T8 | `binance_feed.py` + test | Foundation — kline data must flow before exits make sense |
| Phase 2 | T4, T5, T6 (parallel) | 3 YAML templates | Independent of each other; add pct fallback exits |
| Phase 3 | T7 | `base.py` | Log-only; truly independent but ordered last for review clarity |
| Validation | T9 | All | Final gate |

### Execution order recommendation

For `sdd-apply`: execute **T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9** (sequential with T4/T5/T6 parallelizable).

---

## Review Workload Forecast

### Estimated changed lines

| File | Lines changed | Type |
|---|---|---|
| `src/royaltdn/data/binance_feed.py` | ~15 | Edit |
| `src/royaltdn/cells/templates/swing.yaml` | ~40 | Edit |
| `src/royaltdn/cells/templates/intraday.yaml` | ~40 | Edit |
| `src/royaltdn/cells/templates/scalping.yaml` | ~40 | Edit |
| `src/royaltdn/cells/base.py` | ~5 | Edit |
| `tests/test_binance_feed.py` | ~60 | Create |
| **Total** | **~200** | |

### Chained PR recommendation

**Single PR** (~200 lines). Well under the 400-line chained PR threshold. The changes are:
- **Independent in source** (5 different files)
- **Logically cohesive** (all part of one fix — cells can't exit positions)
- **No schema/DB changes** (zero migration risk)

**Decision**: Ship as one PR. The review surface is modest, and splitting would create artificial dependencies (YAML pct exits without kline data = no real benefit; kline data without pct exits = ATR works on non-SMF cells but SMF cells still broken).

### Review focus areas

| Area | Attention needed | Why |
|---|---|---|
| `_handle_message()` kline parser | High | New message schema — verify KeyError path and edge cases |
| YAML pct values | Medium | Verify each cell gets correct values per category/timeframe |
| Non-SMF cells unchanged | Medium | Grep-confirm no changes to `swing_reversion`, `swing_momentum`, `intraday_volume_breakout`, `scalping_reversion` |
| Log line position | Low | Confirm `atr` variable is defined before the log line (moved after `_calc_atr()`) |
| `_kline_start` underscore convention | Low | Verify underscore prefix signals internal field |
