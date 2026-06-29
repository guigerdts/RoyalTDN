# Proposal: Fix ticker-data ATR exits

## Intent

SMF strategy cells never exit positions — all debug logs show `SL_pct=None TP_pct=None TS_pct=None`. Three interrelated bugs cause this: (1) the debug log only prints pct attributes, hiding ATR-based exits; (2) BinanceFeed streams `@ticker` (24h rolling stats, not real candles), inflating ATR to ~5% for BTC; (3) SMF cells have no pct fallback when ATR is unavailable or broken.

## Scope

### In Scope

1. **Fix debug log** — `_check_exit()` shows both pct and ATR attributes
2. **Fix BinanceFeed** — switch from `@ticker` to `@kline_1m` for real OHLCV candles
3. **Add pct fallbacks** — `stop_loss.pct` + `trailing_stop.pct` to all SMF cells in 3 YAML templates

### Out of Scope

- Full feed pipeline rewrite (multi-timeframe, historical backfill)
- Cell architecture refactor
- Adding take_profit to SMF cells (changes strategy intent)
- Adding tests for existing ATR logic

## Capabilities

### New Capabilities

None

### Modified Capabilities

- `smf-cloud-strategies`: SMF cells now include pct-based fallback exits in addition to ATR-based exits. Delta spec covers fallback values per timeframe (scalping / intraday / swing).

## Approach

1. **Log fix** (`base.py:419-426`): Add `exit_stop_loss`, `exit_trailing_stop`, `exit_trailing_min_mult`, `exit_trailing_max_mult`, and current ATR value to the debug line. Mechanical change.
2. **Feed switch** (`binance_feed.py`): Change `_build_url()` from `@ticker` to `@kline_1m`. Update `_handle_message()` to parse kline schema (nested `k` object: `k.t`, `k.o`, `k.h`, `k.l`, `k.c`, `k.v`). Add `interval` param to `__init__` for future flexibility.
3. **Pct fallbacks** (3 YAML files): Add pct-stop alongside existing ATR exits. Values by timeframe: scalping (stop: 1.5%, trail: 0.8%), intraday (stop: 2.5%, trail: 1.2%), swing (stop: 5.0%, trail: 2.0%). Pct check fires first in the `elif` chain; ATR mode runs when pct is None.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/cells/base.py` | Modified | Debug log shows ATR attributes |
| `src/royaltdn/data/binance_feed.py` | Modified | `@kline_1m` feed, kline parser, interval param |
| `src/royaltdn/cells/templates/swing.yaml` | Modified | 4 SMF cells + pct fallback exits |
| `src/royaltdn/cells/templates/intraday.yaml` | Modified | 4 SMF cells + pct fallback exits |
| `src/royaltdn/cells/templates/scalping.yaml` | Modified | 4 SMF cells + pct fallback exits |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Kline schema is nested object vs flat ticker | Low | Verify with Binance WS docs before deploy |
| Pct fallback fires when ATR would have been fine | Medium | `elif` hierarchy: pct checked first, ATR skipped only if pct is set. ATR-first cells unaffected. |
| Some pairs lack 1m kline stream | Low | Binance supports kline_1m for all USDT pairs |

## Rollback Plan

Revert each file independently in reverse order: (1) revert 3 YAMLs, (2) revert `binance_feed.py`, (3) revert `base.py`. No migration needed — no DB/state changes.

## Dependencies

- Binance WebSocket API docs to confirm kline message structure

## Success Criteria

- [ ] Debug log shows ATR multiplier values when ATR-based exits are configured
- [ ] Feed emits real per-candle OHLCV (high/low reflect individual candlesticks, not 24h range)
- [ ] Every SMF cell in scalping/intraday/swing templates has pct-based stop_loss and trailing_stop fallback
- [ ] `SL_pct` and `TS_pct` are non-None in debug logs for SMF cells after fix #3
