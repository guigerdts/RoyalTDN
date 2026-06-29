# Delta: smf-cloud-strategies

## Purpose

SMF cells cannot exit positions: (1) debug log hides ATR attributes showing only `None`, (2) BinanceFeed streams 24h ticker inflating ATR, (3) SMF cells lack pct fallback exits. This delta fixes all three and adds pct fallback exits to every SMF cell.

## ADDED Requirements

### R1: Debug log reveals ATR attributes

The `_check_exit()` debug log MUST print ALL exit attributes: `exit_stop_loss`, `exit_trailing_stop`, `exit_trailing_min_mult`, `exit_trailing_max_mult`, `exit_zscore_threshold`, and the current ATR value — alongside existing pct attributes.

#### Scenario: SMF cell logged with ATR values

- GIVEN an SMF cell configured with `atr_multiplier` exits only (no pct)
- WHEN `_check_exit()` evaluates
- THEN the debug log SHOWs non-None values for `SL`, `TS`, `TS_min_mult`, `TS_max_mult`, `ATR`

### R2: BinanceFeed streams kline_1m

The feed SHALL switch from `@ticker` (24h rolling stats) to `@kline_1m` (per-candle OHLCV) for real candle data.

#### R2.1: URL generates kline streams

- `_build_url()` MUST produce `{symbol@lowercase}@kline_1m` streams
- URL format: `wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m`
- The `__init__` SHOULD accept an optional `interval` param (default `1m`) for future flexibility

#### R2.2: Message parser handles kline schema

- `_handle_message()` MUST detect kline messages via `data.get("e") == "kline"` or presence of `k` key
- OHLCV SHALL be extracted from the nested `k` object: `k.o`, `k.h`, `k.l`, `k.c`, `k.v`, `k.q`, `k.n`
- ALL kline updates SHALL be processed (ignoring `k.x` candle-closed flag) for real-time reactivity
- The emitted event MUST preserve the same shape: `{type, symbol, price, timestamp, data{high, low, open, close, volume, quote_volume, count}}`

#### Scenario: Kline message becomes tick event

- GIVEN a WS message `{"e":"kline","E":123,"s":"BTCUSDT","k":{"t":1,"T":2,"o":"50000","h":"50200","l":"49900","c":"50100","v":"100","q":"5000000","n":300}}`
- WHEN `_handle_message()` parses it
- THEN it emits `{type:"tick", symbol:"BTCUSDT", price:50100.0, data:{high:50200.0, low:49900.0, open:50000.0, close:50100.0, volume:100.0, quote_volume:5000000.0, count:300}}`

#### Scenario: Non-kline message skipped gracefully

- GIVEN a WS message without `k` key (e.g. ping keepalive)
- WHEN `_handle_message()` runs
- THEN no event is emitted and no exception propagates

### R3: SMF cells include pct fallback exits

Every SMF cell SHALL include a `stop_loss.pct` and `take_profit.pct` exit rule BEFORE the existing ATR rules. Trend cells also include `trailing_stop.pct`. Values SHALL follow strategy type and timeframe per table below.

The pct rules fire first in the `if/elif` chain (pct stop-loss → pct take-profit → pct trailing → ATR stop → ATR trailing). ATR-only cells (non-SMF) are unaffected.

| Cell Category | Cells | SL pct | TP pct | TS pct |
|---|---|---|---|---|
| Swing trend | `swing_smf_trend_bollinger`, `swing_smf_momentum_adx` | 3.0% | 5.0% | 2.0% |
| Swing reversion | `swing_smf_reversion_zscore`, `swing_smf_retest_rsi` | 2.0% | 3.0% | — (ATR only) |
| Intraday trend | `intraday_smf_trend_adx`, `intraday_smf_momentum_volume` | 1.5% | 2.5% | 1.0% |
| Intraday reversion | `intraday_smf_retest_bollinger`, `intraday_smf_zscore_reversion` | 1.0% | 2.0% | — (ATR only) |
| Scalping momentum | `scalping_smf_momentum`, `scalping_smf_breakout` | 0.8% | 1.5% | 0.5% |
| Scalping reversion | `scalping_smf_retest_rsi`, `scalping_smf_reversion` | 0.6% | 1.2% | — (ATR only) |

#### Scenario: SMF cell exits via pct when ATR inflated

- GIVEN an SMF cell with both `stop_loss.pct: 3.0` and `stop_loss.atr_multiplier: 3.0`
- WHEN price drops 3.5% from entry
- THEN the cell emits SELL via pct stop-loss before ATR check runs

#### Scenario: Take-profit fires before trailing

- GIVEN a trend SMF cell with `take_profit.pct: 5.0` and adaptive trailing
- WHEN price rises 5.0% from entry
- THEN the cell emits SELL via pct take-profit before trailing logic runs

#### Scenario: Reversion cell exits via take-profit

- GIVEN a reversion SMF cell with `take_profit.pct: 3.0` and no trailing pct
- WHEN price moves 3.0% to target
- THEN the cell emits exit via pct take-profit

#### Scenario: Cell with only ATR mode unchanged

- GIVEN a non-SMF cell with no pct exits (e.g. `swing_reversion`)
- WHEN `_check_exit()` evaluates
- THEN only its existing pct-based (or ATR-based) rules apply — SMF-only change

## Edge Cases

- **ATR = 0 or None**: pct exits fire first; ATR branch skipped. No code change needed.
- **Kline WS disconnection**: existing exponential backoff reconnects automatically. No new error handling required.
- **Both pct and ATR thresholds breached simultaneously**: the FIRST condition matched in the `if` chain (pct stop-loss → pct take-profit → pct trailing → ATR stop → ATR trailing) wins and generates exactly one exit signal.
- **`_kline_start` field**: added at event root as `event["_kline_start"]` for future candle dedup. No current consumer reads it.
- **Interval param future use**: adding `interval="1m"` to `__init__` is non-breaking. Feed behavior unchanged until the param is user-configurable.
- **Non-SMF cells unaffected**: `swing_reversion`, `swing_momentum`, `intraday_volume_breakout`, `scalping_reversion` keep their existing pct exits — no YAML changes to these cells.
