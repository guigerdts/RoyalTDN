# Design: Fix Ticker Data ATR Exits

## 1. Technical Approach

Three independent fixes, each in a single file. No architectural refactor, no schema migration, no new dependencies.

### Fix 1: Debug log reveals ATR attributes (`base.py`)
**Strategy**: Add ATR-related fields to the existing single-line debug log. Use conditional display — when the cell has ATR-based exits configured, show `SL_ATR`, `TS_ATR`, `TS_min`, `TS_max`, and the computed ATR value. When pct-based exits are configured, keep the existing pct fields. Show both when both are set (which is the case for SMF cells after Fix 3).

The current log hides ATR attributes because it only prints `SL_pct`, `TP_pct`, `TS_pct` — all `None` for SMF cells. The fix adds the full set of exit attributes to the same format string.

### Fix 2: BinanceFeed streams real candles (`binance_feed.py`)
**Strategy**: Change the stream subscription from `@ticker` (24h rolling window) to `@kline_1m` (per-candle OHLCV). The kline message has a nested `k` object where OHLCV fields live. The event shape emitted to the EventBus stays identical — downstream code (`cells`, `engine`, `dashboard`) does NOT change. An `interval` parameter is added to `__init__` for future flexibility but defaults to `"1m"`.

### Fix 3: SMF cells get pct fallback exits (3 YAML files)
**Strategy**: Add a `stop_loss.pct` and `trailing_stop.pct` entry before each SMF cell's existing ATR exit entries. The `_check_exit()` method uses `if`/`elif` chains where pct is checked first — so pct fires when configured, effectively replacing ATR mode for that exit type. This is deliberate: pct is the defense when ATR is broken/inflated. ATR exits remain for non-SMF cells that have no pct configured.

---

## 2. Component Changes

### 2.1 `src/royaltdn/cells/base.py` — Debug log only

#### What changes
Line ~419-426: Expand the `logger.debug()` format string to include all exit attributes.

#### Current code
```python
logger.debug(
    "{} {} CHECK-EXIT price=${:.4f} entry=${:.4f} state={} "
    "SL_pct={} TP_pct={} TS_pct={}",
    self.symbol, self.name, current_price, self.entry_price,
    self.state,
    self.exit_stop_loss_pct, self.exit_take_profit_pct,
    self.exit_trailing_stop_pct,
)
```

#### New code
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

#### Why this works
- For SMF cells (after Fix 3): `SL_pct=0.04 SL_ATR=3.0` — both visible, engineer sees pct is active
- For non-SMF ATR-only cells: `SL_pct=None SL_ATR=3.0` — shows ATR is the active mode
- For non-SMF pct-only cells: `SL_pct=0.01 SL_ATR=None` — shows pct mode
- `atr` is already computed at line 428, so it's available for logging

#### What does NOT change
- No logic change in `_check_exit()` — only the log line
- No new attributes or configuration

---

### 2.2 `src/royaltdn/data/binance_feed.py` — Stream switch + kline parser

#### 2.2.1 `__init__` — new `interval` parameter

```python
def __init__(
    self,
    symbols: list[str],
    bus: EventBus,
    testnet: bool = False,
    interval: str = "1m",
) -> None:
    ...
    self.interval = interval
```

The call site in `main.py:249`:
```python
feed = BinanceFeed(cfg.symbols, bus, testnet=cfg.testnet)
```
This continues to work — `interval` defaults to `"1m"`, so no caller change needed.

#### 2.2.2 `_build_url()` — `@ticker` → `@kline_1m`

```python
def _build_url(self) -> str:
    streams = "/".join(
        f"{s.lower().replace('/', '')}@kline_{self.interval}"
        for s in self.symbols
    )
    return f"wss://stream.binance.com:9443/stream?streams={streams}"
```

#### 2.2.3 `_handle_message()` — kline schema parser

```python
async def _handle_message(self, raw: str) -> None:
    try:
        data = json.loads(raw)

        # Combined stream: {"stream": "...", "data": {...}}
        # Direct stream: just {...}
        msg = data.get("data", data)

        # Reject non-kline messages (keepalive pings, etc.)
        if "k" not in msg:
            return

        k = msg["k"]
        event = {
            "type": "tick",
            "symbol": msg["s"],
            "price": float(k["c"]),
            "volume": float(k["v"]),
            "timestamp": datetime.fromtimestamp(
                msg["E"] / 1000, tz=timezone.utc
            ),
            "data": {
                "high": float(k["h"]),
                "low": float(k["l"]),
                "open": float(k["o"]),
                "close": float(k["c"]),
                "volume": float(k["v"]),
                "quote_volume": float(k["q"]),
                "count": k["n"],
            },
            # Optional: kline_start_time for potential dedup
            "_kline_start": k["t"],
        }
        await self.bus.emit(event)

    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to parse kline message: {} — {}", exc, raw[:200]
        )
```

#### Key design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Interval | `1m` | Best balance of granularity and ATR responsiveness. 1m candles capture enough volatility for meaningful ATR while being frequent enough for intraday/scalping cells. |
| Process unclosed candles | Yes (`k.x` ignored) | Real-time reactivity requires seeing price movement within the candle, not just at close. ATR calculation uses the full OHLC range anyway. |
| `_kline_start` field | Added | Preserves `k.t` (epoch ms of candle open) for optional dedup in future. The underscore prefix signals it's an internal field. |
| Non-kline messages | Silently skipped | `if "k" not in msg: return` — handles pings and other WS control frames without exceptions. |

#### Event shape contract (unchanged downstream)

```python
# BEFORE (ticker):                             # AFTER (kline):
event = {                                       event = {
    "type": "tick",                                 "type": "tick",
    "symbol": ticker["s"],                          "symbol": msg["s"],
    "price": float(ticker["c"]),                    "price": float(k["c"]),
    "volume": float(ticker["v"]),                   "volume": float(k["v"]),
    "timestamp": ...,                               "timestamp": ...,
    "data": {                                       "data": {
        "high": float(ticker["h"]),                     "high": float(k["h"]),
        "low": float(ticker["l"]),                      "low": float(k["l"]),
        "open": float(ticker["o"]),                     "open": float(k["o"]),
        "close": float(ticker["c"]),                    "close": float(k["c"]),
        "volume": float(ticker["v"]),                   "volume": float(k["v"]),
        "quote_volume": float(ticker["q"]),             "quote_volume": float(k["q"]),
        "count": ticker["n"],                           "count": k["n"],
    },                                              },
}                                                   }
```

Every downstream consumer (`cells/base.py`, `engine`, `dashboard`) accesses the same keys. The only difference is that `high` and `low` now reflect a 1-minute candle instead of a 24h window — ATR becomes meaningful.

---

### 2.3 Three YAML templates — pct fallback exits

#### 2.3.1 SMF cell exit list transformation

Every SMF cell currently has this pattern:
```yaml
exit:
  - type: trailing_stop
    params:
      atr_multiplier: 2.0
      min_mult: 0.5
      max_mult: 1.5
  - type: stop_loss
    params:
      atr_multiplier: 3.0
```

The new pattern adds pct fallback entries FIRST:
```yaml
exit:
  - type: stop_loss
    params:
      pct: <VALUE>
  - type: trailing_stop
    params:
      pct: <VALUE>
  - type: trailing_stop
    params:
      atr_multiplier: 2.0
      min_mult: 0.5
      max_mult: 1.5
  - type: stop_loss
    params:
      atr_multiplier: 3.0
```

#### 2.3.2 Parser behavior with both pct and ATR

In `_parse_exit_rules()`, the YAML exit list is iterated sequentially:

1. **First stop_loss** (has `pct`) → sets `self.exit_stop_loss_pct = pct/100`
2. **First trailing_stop** (has `pct`) → sets `self.exit_trailing_stop_pct = pct/100`
3. **Second trailing_stop** (has `atr_multiplier`, no `pct`) → sets `self.exit_trailing_stop = 2.0`, `min_mult = 0.5`, `max_mult = 1.5`
4. **Second stop_loss** (has `atr_multiplier`, no `pct`) → sets `self.exit_stop_loss = 3.0`

After parsing, both pct and ATR attributes are non-None. In `_check_exit()`:
- `if self.exit_stop_loss_pct is not None` → always True → pct stop-loss checked first
- `elif self.exit_stop_loss is not None and has_atr` → NEVER evaluated (if was taken)
- Same pattern for trailing_stop

**Net effect**: pct replaces ATR for SMF cells. ATR mode only runs for cells where pct is `None` (non-SMF cells like `swing_reversion`, `intraday_volume_breakout`, `scalping_reversion`, plus any custom cells).

---

## 3. Data Flow

### Before (broken)

```
Binance WS @ticker  →  BinanceFeed._handle_message()
                         ↓
                       event{type:"tick", high, low, open, close}
                         ↓  <-- high/low are 24h ROLLING extremes
                       EventBus.emit(event)
                         ↓
                       Cell._check_exit()
                         ↓
                       ATR = _calc_atr()
                         ↓  <-- ATR inflated ~5% because high-low spans 24h
                       ATR exit threshold NOT breached
                         ↓
                       No signal (cell never exits)
```

### After (fixed)

```
Binance WS @kline_1m  →  BinanceFeed._handle_message()
                           ↓
                         event{type:"tick", high, low, open, close}
                           ↓  <-- high/low are 1-minute candle extremes
                         EventBus.emit(event)
                           ↓
                         Cell._check_exit()
                           ↓
                         ATR = _calc_atr()
                           ↓  <-- ATR now reflects 1m volatility (~0.1-0.3%)
                         pct exit check (if configured): fires first
                           OR
                         ATR exit check (if pct is None): fires when threshold breached
                           ↓
                         Signal generated → Engine → RiskManager → Broker
```

### Key behavioral changes

| Aspect | Before (@ticker) | After (@kline_1m) | Impact |
|---|---|---|---|
| Update frequency | ~1s per symbol | ~1s per symbol (same) | None — both fire on every tick |
| high/low scope | 24h window | 1-minute candle | ATR drops from ~5% to ~0.2% — exits start working |
| Entry rate | Every tick creates a bar | Every tick creates a bar (same) | None — same accumulation |
| Time to first ATR | 14 ticks (~14s) | 15 bars = 15 min (need 14 + 1) | Slower initial ATR. Mitigation: this was a pre-existing requirement for all cells. |
| Dedup potential | No kline_start_time | `_kline_start` available | Future-proofing, not used now |

---

## 4. Proposed pct Values Table

### Design principles

1. **Trend-following cells** need wider stops to allow trends room to develop without premature exit.
2. **Reversion cells** can use tighter stops because they mean-revert to a band.
3. **Timeframe scaling**: swing (1d) > intraday (1h) > scalping (15m) — longer timeframes need wider stops.
4. **Values are wider than ATR at correct operation**: when ATR is working on real 1m candles, the ATR-based exits (3.0 × ATR ≈ 0.9% for BTC) are tighter than these pct values. So pct acts as a catastrophic safety net, not the primary exit — except when ATR is broken, in which case pct becomes the primary.
5. **Reference values** from existing non-SMF cells validate the scale:

| Reference cell | Timeframe | SL pct | TP/TS pct |
|---|---|---|---|
| `swing_reversion` | 1d | 1.0% | 3.0% (TP) |
| `swing_momentum` | 1d | 0.9% | 1.2% (TS) |
| `intraday_volume_breakout` | 30m | 0.8% | 1.5% (TP) |
| `scalping_reversion` | 1m | 0.9% | 1.0% (TP) |

### Implemented SMF fallback values

| Category | Timeframe | Cells | SL pct | TP pct | TS pct | Rationale |
|---|---|---|---|---|---|---|
| **Swing trend** | 1d | `swing_smf_trend_bollinger`, `swing_smf_momentum_adx` | **3.0%** | **5.0%** | **2.0%** | 1d trends move 2-4% daily; 3% SL + 5% TP allows trend development with clear gain target. Trail at 2% captures retracements. |
| **Swing reversion** | 1d | `swing_smf_reversion_zscore`, `swing_smf_retest_rsi` | **2.0%** | **3.0%** | — (ATR) | Mean-reverting entries need tighter control. 2% SL + 3% TP pairs with typical zscore/RSI retest move. |
| **Intraday trend** | 1h | `intraday_smf_trend_adx`, `intraday_smf_momentum_volume` | **1.5%** | **2.5%** | **1.0%** | 1h moves 1-2%. 1.5% SL allows intraday trends to develop. TP at 2.5%, trail at 1.0% locks in gains. |
| **Intraday reversion** | 1h | `intraday_smf_retest_bollinger`, `intraday_smf_zscore_reversion` | **1.0%** | **2.0%** | — (ATR) | Reversion on 1h: tighter bands. 1% SL + 2% TP, trail stays ATR-based adaptative. |
| **Scalping momentum** | 15m | `scalping_smf_momentum`, `scalping_smf_breakout` | **0.8%** | **1.5%** | **0.5%** | Momentum scalps on 15m. 0.8% SL + 1.5% TP, 0.5% trail captures breakout runs. |
| **Scalping reversion** | 15m | `scalping_smf_retest_rsi`, `scalping_smf_reversion` | **0.6%** | **1.2%** | — (ATR) | Tightest — reversion on 15m candles. 0.6% SL + 1.2% TP, trail stays ATR adaptative. |

### YAML addition per cell

Taking `swing_smf_trend_bollinger` as the example:

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
  - type: trailing_stop          # existing ATR (now secondary)
    params:
      atr_multiplier: 2.0
      min_mult: 0.5
      max_mult: 1.5
  - type: stop_loss               # existing ATR (now secondary)
    params:
      atr_multiplier: 3.0
```

### Cells NOT modified

These non-SMF cells keep their existing YAML unchanged:
- `swing_reversion` (already has pct-only exits)
- `swing_momentum` (already has pct-only exits)
- `intraday_volume_breakout` (already has pct-only exits)
- `scalping_reversion` (already has pct-only exits)

---

## 5. Backward Compatibility

### 5.1 EventBus consumers

| Consumer | Impact | Details |
|---|---|---|
| `Cell.handle()` | None | Reads `event["price"]`, `event["data"]["high/low/close"]` — same keys |
| `EventEngine` | None | Routes events by symbol — no change |
| `Dashboard` | None | Displays price from event — no change |
| `InferenceEngine` | None | Uses `_build_data()` which reads from accumulated bars — no change |
| `TelegramAlerts` | None | Reads `event` fields — no change |

### 5.2 Cell state

No migration needed. On restart:
- Bars start accumulating fresh (as always)
- First ATR available after 15 bars (same as before)
- SMF cells now have pct exits configured — they'll fire earlier than before (which is the fix)

### 5.3 YAML loading

The parser iterates the exit list in order and overwrites attributes of the same type. Adding new entries before existing ones is a no-op for the existing entries — they still get parsed and set their respective attributes.

### 5.4 Existing tests

No tests exist for binance_feed (confirmed by grep). No test changes needed for this design. Tests should be added as part of the implementation (see Recommendations).

### 5.5 Rollback

Per proposal: revert files in reverse order — YAMLs → binance_feed.py → base.py. No DB/state migration required.

---

## 6. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Both pct and ATR set but only pct fires** | Certain-by-design | Medium | ATR is effectively disabled for SMF cells when pct is configured. Mitigation: this is intentional. ATR exits remain working for all non-SMF cells. If ATR-based exits are needed alongside pct in the future, the if/elif chain in `_check_exit()` would need restructuring to `if/if` (independent checks with dedup). |
| **Pct fires prematurely on volatile swing cells** | Low | Medium | 3% SL on swing cells is ~1× daily ATR for BTC — absorbs normal wick noise. If premature exits appear, values can be tuned per cell without code changes. |
| **1m kline not available for some pairs** | Very low | High | All USDT pairs on Binance support kline_1m. This is a core Binance API offering. |
| **k.t dedup field ignored** | None | Low | `_kline_start` is added to events but consumed by nothing yet. No risk — it's optional metadata. |
| **WS disconnection → gap in kline stream** | Medium | Medium | Existing exponential backoff reconnects automatically. The gap means missing 1m candles = stale ATR. Mitigation: ATR recalculates from accumulated bars after reconnection. Historical backfill is out of scope. |
| **ATR needs 15 bars → no exits for first 15 min** | High | Low | This is a pre-existing condition (not introduced by this change). The cell's `_calc_atr()` returns `None` for < 15 bars, and ATR exits already handle `None` gracefully. With pct fallback added, cells now have exits during the first 15 minutes. **This change actually improves the situation.** |
| **Pct exit fires when ATR would have been fine** | Medium | Low | Because pct replaces ATR (if/elif chain), a cell might exit at 4% when ATR would have given it 6% room. Mitigation: the pct values are calibrated to be wider than normal ATR-based exits. If ATR is working (BTC ~0.2% on 1m), ATR×3 = 0.6%, so pct at 4% is much wider — it only fires first when ATR is broken. |

---

## 7. Recommendations for Implementation

### Priority order
1. `binance_feed.py` — needs to be deployed first to feed real candles
2. `base.py` — the log change is standalone, deploy anytime
3. 3 YAML files — needs kline data flowing before pct exits make sense

### Testing before merge
- [ ] Unit test: `_handle_message()` parses a kline JSON → produces correct event shape
- [ ] Unit test: non-kline message is silently skipped
- [ ] Unit test: cell with both pct and ATR exits → pct if fires, ATR elif skipped
- [ ] Unit test: cell with only ATR exits → ATR elif still works
- [ ] Integration test: BinanceFeed → EventBus → Cell → _check_exit with real kline data

### Future enhancements (out of scope)
- Multi-timeframe feed (subscribe to multiple kline intervals per symbol)
- Historical backfill on reconnect
- Configurable kline interval per cell (e.g., 5m cells use @kline_5m)
- Restructure if/elif to allow pct + ATR independent checks with dedup
