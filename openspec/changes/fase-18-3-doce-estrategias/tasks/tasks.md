# Tasks: FASE 18.3 — 12 nuevas estrategias (13 files)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1073 (353 + 350 + 370) |
| 400-line budget risk | **High** |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (orchestrator fix + scalping) → PR 2 (intraday) → PR 3 (swing + registration + tests) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Base branch | Est. lines |
|------|------|-------------|-----------|
| 1 | Fix orchestrator `category` propagation + 5 scalping strategies | `fase-18-3-doce-estrategias` (tracker) | ~353 |
| 2 | 5 intraday strategies | PR 1 branch | ~350 |
| 3 | 3 swing strategies + main.py registration + parametrized tests | PR 2 branch | ~370 |

**Chain topology**: PR 1 → tracker. PR 2 → PR 1. PR 3 → PR 2. Only tracker merges to `main`.

---

## PR 1: Orchestrator fix + 5 Scalping Strategies (~353 lines)

### 1.1 Fix orchestrator: `_build_strategies_list()` category propagation

- [ ] 1.1.1 `src/royaltdn/orchestrator.py` L482: add `"category": getattr(strategy, 'category', 'swing')` after `"timeframe"` in scanner strategies loop
- [ ] 1.1.2 `src/royaltdn/orchestrator.py` L493: add `"category": "swing"` to fallback single-entry dict
- [ ] 1.1.3 `src/royaltdn/orchestrator.py` L509: add `"category": getattr(strat, 'category', 'swing')` after `"timeframe"` in user strategies loop

### 1.2 Create `ScalpingMomentumStrategy` — `scalping_momentum.py`

- [ ] Create file with class `ScalpingMomentumStrategy(BaseStrategy)`, crypto `{momentum_period:5, min_momentum_pct:1.0, timeframe:1min}`, stocks `{momentum_period:10, min_momentum_pct:0.5, timeframe:3min}`, signal: close return > min_pct → BUY, negative → SELL

### 1.3 Create `ScalpingBreakoutStrategy` — `scalping_breakout.py`

- [ ] Create file with class `ScalpingBreakoutStrategy(BaseStrategy)`, crypto `{period:10, mult:2.0, timeframe:1min}`, stocks `{period:20, mult:1.5, timeframe:5min}`, signal: close > max(high[-N:]) AND range > ATR * mult → BUY

### 1.4 Create `ScalpingReversionStrategy` — `scalping_reversion.py`

- [ ] Create file with class `ScalpingReversionStrategy(BaseStrategy)`, crypto `{period:10, dev:2.0, timeframe:1min}`, stocks `{period:14, dev:1.5, timeframe:3min}`, signal: close vs SMA ± dev*STD → BUY/SELL

### 1.5 Create `ScalpingOrderFlowStrategy` — `scalping_orderflow.py`

- [ ] Create file with class `ScalpingOrderFlowStrategy(BaseStrategy)`, crypto `{vol_thresh:1_000_000, imb:2.0, timeframe:1min}`, stocks `{vol_thresh:500_000, imb:1.5, timeframe:5min}`, signal: volume > threshold AND buy/sell ratio > imb → BUY

### 1.6 Create `ScalpingSpreadStrategy` — `scalping_spread.py`

- [ ] Create file with class `ScalpingSpreadStrategy(BaseStrategy)`, crypto `{spread_period:10, thresh:2.0, timeframe:1min}`, stocks `{spread_period:20, thresh:1.5, timeframe:5min}`, signal: spread > SMA*thresh → BUY, spread < SMA/thresh → SELL

---

## PR 2: 5 Intraday Strategies (~350 lines)

### 2.1 Create `IntradayTrendStrategy` — `intraday_trend.py`

- [ ] Create file with class `IntradayTrendStrategy(BaseStrategy)`, crypto `{trend_period:14, adx_threshold:25, timeframe:15min}`, stocks `{trend_period:20, adx_threshold:20, timeframe:1H}`, signal: ADX > threshold AND EMA(fast) > EMA(slow) → BUY/SELL

### 2.2 Create `IntradayVWAPStrategy` — `intraday_vwap.py`

- [ ] Create file with class `IntradayVWAPStrategy(BaseStrategy)`, crypto `{vwap_mult:2.0, period:14, timeframe:15min}`, stocks `{vwap_mult:1.5, period:20, timeframe:1H}`, signal: close near VWAP deviation bands → mean reversion BUY/SELL

### 2.3 Create `IntradayVolumeBreakoutStrategy` — `intraday_volume_breakout.py`

- [ ] Create file with class `IntradayVolumeBreakoutStrategy(BaseStrategy)`, crypto `{surge:2.0, period:10, timeframe:15min}`, stocks `{surge:1.5, period:20, timeframe:1H}`, signal: vol > SMA(vol)*surge AND price breaks range → BUY

### 2.4 Create `IntradaySupportResistanceStrategy` — `intraday_support_resistance.py`

- [ ] Create file with class `IntradaySupportResistanceStrategy(BaseStrategy)`, crypto `{sr_period:20, bounce_pct:0.5, timeframe:15min}`, stocks `{sr_period:30, bounce_pct:0.3, timeframe:1H}`, signal: touch S/R zone + bounce → BUY/SELL

### 2.5 Create `IntradayMACDDivergenceStrategy` — `intraday_macd_divergence.py`

- [ ] Create file with class `IntradayMACDDivergenceStrategy(BaseStrategy)`, crypto `{fast:12, slow:26, sig:9, timeframe:15min}`, stocks `{fast:12, slow:26, sig:9, timeframe:1H}`, signal: price high ≠ MACD high → divergence BUY (bullish) / SELL (bearish)

---

## PR 3: 3 Swing Strategies + Registration + Tests (~370 lines)

### 3.1 Create `SwingTrendFollowingStrategy` — `swing_trend_following.py`

- [ ] Create file with class `SwingTrendFollowingStrategy(BaseStrategy)`, crypto `{fast_ema:7, slow_ema:25, adx:25, timeframe:1d}`, stocks `{fast_ema:10, slow_ema:30, adx:20, timeframe:1d}`, signal: EMA cross + ADX strength → BUY/SELL

### 3.2 Create `SwingReversionStrategy` — `swing_reversion.py`

- [ ] Create file with class `SwingReversionStrategy(BaseStrategy)`, crypto `{lookback:20, z_threshold:2.0, timeframe:1d}`, stocks `{lookback:30, z_threshold:1.5, timeframe:1d}`, signal: z-score > |threshold| → mean reversion BUY/SELL

### 3.3 Create `SwingBreakoutStrategy` — `swing_breakout.py`

- [ ] Create file with class `SwingBreakoutStrategy(BaseStrategy)`, crypto `{period:20, vol_confirm:true, timeframe:1d}`, stocks `{period:30, vol_confirm:true, timeframe:1d}`, signal: price breaks multi-day range + volume confirmation → BUY/SELL

### 3.4 Register all strategies in `main.py`

- [ ] Add 13 imports in the `try` block at L287 (alphabetical: intraday, scalping, swing)
- [ ] Add 13 instantiation gates after L325 with `if "name" in strategies_enabled: strategies["name"] = ClassName(category="...")`
- [ ] Update `STRATEGIES_ENABLED` default at L316 to include all 13 names in addition to existing 4

### 3.5 Create parametrized tests — `tests/test_fase18_3_doce_estrategias.py`

- [ ] Create test file with `@pytest.mark.parametrize` over all 13 strategies x 8 test functions: instantiation, generate_signal (None data / crypto data / stocks data), get_parameters (None / crypto / stocks), validate, and category property
- [ ] Provide synthetic OHLCV fixture (100-row DataFrame with deterministic sequences)

---

## Dependencies

```
PR 1 (orchestrator fix + scalping) → PR 2 (intraday) → PR 3 (swing + registration + tests)
                                                         └── must have all 13 strategy files
                                                         └── test file imports every class
```

- PR 3 test file imports all 13 classes → all strategy files must exist before PR 3
- PR 2 and PR 3 include no new strategy categories → no conflict with existing menu
- Orchestrator fix (PR 1) is prerequisite for correct menu display in any PR verification

## Review Workload Detail

| PR | Files | New | Modified | Est. lines | Budget risk |
|----|-------|-----|----------|-----------|-------------|
| 1 | 6 | 5 | 1 (+3 lines) | ~353 | **Low** (under 400) |
| 2 | 5 | 5 | 0 | ~350 | **Low** (under 400) |
| 3 | 5 | 4 | 1 | ~370 | **Low** (under 400) |
| **Total** | **16** | **14** | **2** | **~1073** | **High** (chained required) |

Each PR independently under 400 lines. Chain protects reviewer cognitive load.
