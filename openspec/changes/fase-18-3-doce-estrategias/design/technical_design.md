# Technical Design: FASE 18.3 — 12 (13) New Strategies

## Technical Approach

Add 13 `BaseStrategy` implementations across 3 categories (`scalping`, `intraday`, `swing`) following the proven dual-`_PROFILES` template from `momentum_atr.py`. Fix the orchestrator to propagate `category` into `strategies.json`. Register all strategies in `main.py` with feature-flag gating.

## Architecture Decisions

### Decision: Template strategy pattern

| Option | Tradeoff | Decision |
|--------|----------|----------|
| One file per strategy, copy-paste template | High boilerplate but testable in isolation, easy to review per-file | **Chosen** — matches existing convention |
| Single file with all scalping strategies | Less DRY code but harder to review (big file), breaks existing pattern | Rejected |
| Auto-discovery via module scan | Less manual registration but existing code uses manual dict | Rejected — "manual registration in main.py" is an explicit constraint |

**Template** (primary reference: `momentum_atr.py`, lines 54-221):
- `_PROFILES: Dict[str, Dict[str, Any]]` — crypto + stocks profiles with `timeframe` per profile
- `__init__(self, ..., timeframe="1d", category="swing")` — defaults match stocks profile
- `generate_signal(data, symbol=None)` — local variable resolution from `_PROFILES` when `symbol` is not `None`; uses `self.*` defaults otherwise
- `get_parameters(symbol=None)` — three-way branch: `None` → prefixed dict, crypto → `_PROFILES["crypto"]`, stocks → `_PROFILES["stocks"]`
- `name` property — unique snake_case string (checked against existing: `sma_crossover`, `bollinger_rsi`, `momentum_atr`, `factor_rotation`)
- `validate()` — each numeric param > 0

### Decision: Orchestrator category fix

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `getattr(strategy, 'category', 'swing')` in scanner loop | Handles missing attr (DynamicStrategy), minimal diff | **Chosen** — 3 insertion points, same 1-liner |
| Add `category` to BaseStrategy as concrete property | Cleaner but modifies base class; DynamicStrategy may not use BaseStrategy | Rejected — larger blast radius |
| Move category logic to menu/app.py | Wrong layer — orchestrator owns `_build_strategies_list()` | Rejected |

**Insertion points** in `_build_strategies_list()`:
1. Scanner strategies loop (line ~482): `strategy_info["category"] = getattr(strategy, 'category', 'swing')`
2. Fallback single-entry (line ~493): `"category": "swing"`
3. User strategies loop (line ~509): `"category": getattr(strat, 'category', 'swing')`

### Decision: PR chaining (400-line budget)

See `file_change_map.md` for exact split. PR3 is ~200 lines because swing strategies have simpler logic (no helper functions).

## Strategy Inventory

| Class | File | Category | Crypto params | Stocks params | Signal logic |
|-------|------|----------|--------------|--------------|--------------|
| `ScalpingMomentumStrategy` | `scalping_momentum.py` | scalping | mom_period=5, min_pct=1.0, TF=1min | mom_period=10, min_pct=0.5, TF=3min | close return > threshold → BUY; return < -threshold → SELL |
| `ScalpingBreakoutStrategy` | `scalping_breakout.py` | scalping | period=10, mult=2.0, TF=1min | period=20, mult=1.5, TF=5min | close > max(high[-N:]) AND range > ATR * mult → BUY |
| `ScalpingReversionStrategy` | `scalping_reversion.py` | scalping | period=10, dev=2.0, TF=1min | period=14, dev=1.5, TF=3min | close vs SMA ± SMA_STD * threshold → BUY/SELL |
| `ScalpingOrderFlowStrategy` | `scalping_orderflow.py` | scalping | vol_thresh=1_000_000, imb=2.0, TF=1min | vol_thresh=500_000, imb=1.5, TF=5min | tick vol > threshold AND buy/sell ratio > imb → BUY |
| `ScalpingSpreadStrategy` | `scalping_spread.py` | scalping | spread_period=10, thresh=2.0, TF=1min | spread_period=20, thresh=1.5, TF=5min | spread > SMA(spread)*thresh → BUY; spread < SMA/thresh → SELL |
| `IntradayTrendStrategy` | `intraday_trend.py` | intraday | trend_period=14, adx=25, TF=15min | trend_period=20, adx=20, TF=1H | ADX > threshold AND EMA(fast) > EMA(slow) → BUY/SELL |
| `IntradayVWAPStrategy` | `intraday_vwap.py` | intraday | vwap_mult=2.0, period=14, TF=15min | vwap_mult=1.5, period=20, TF=1H | close near VWAP bands → mean reversion BUY/SELL |
| `IntradayVolumeBreakoutStrategy` | `intraday_volume_breakout.py` | intraday | surge=200%, period=10, TF=15min | surge=150%, period=20, TF=1H | vol > SMA(vol)*surge AND price breaks range → BUY |
| `IntradaySupportResistanceStrategy` | `intraday_support_resistance.py` | intraday | sr_period=20, bounce=0.5%, TF=15min | sr_period=30, bounce=0.3%, TF=1H | touch S/R zone + bounce → BUY/SELL |
| `IntradayMACDDivergenceStrategy` | `intraday_macd_divergence.py` | intraday | fast=12, slow=26, sig=9, TF=15min | fast=12, slow=26, sig=9, TF=1H | price vs MACD divergence → BUY (bullish) / SELL (bearish) |
| `SwingTrendFollowingStrategy` | `swing_trend_following.py` | swing | fast_ema=7, slow=25, adx=25, TF=1d | fast_ema=10, slow=30, adx=20, TF=1d | EMA cross + ADX strength → BUY/SELL |
| `SwingReversionStrategy` | `swing_reversion.py` | swing | lookback=20, z=2.0, TF=1d | lookback=30, z=1.5, TF=1d | z-score > |threshold| → mean reversion BUY/SELL |
| `SwingBreakoutStrategy` | `swing_breakout.py` | swing | period=20, vol_confirm=True, TF=1d | period=30, vol_confirm=True, TF=1d | price breaks range + volume confirmation → BUY/SELL |

## Data Flow

```
main.py cmd_run()
    │
    ├── Scanner(scanner.py) — holds `strategies: Dict[str, BaseStrategy]`
    │       │
    │       └── Scanner.scan() → iterates strategies → strategy.generate_signal(data, symbol)
    │
    ├── Orchestrator.start()
    │       │
    │       └── Orchestrator._build_strategies_list()
    │               │
    │               └── strategies.json → (now includes "category") → frontend menu
    │
    └── Menu (app.py _show_estrategias())
            │
            └── Groups by "category": 🟢 SCALPING / 🟡 INTRADÍA / 🔵 SWING
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit — instantiation | 13 classes x 1 strategy | Assert `strategy.name`, `strategy.category`, defaults |
| Unit — generate_signal | 13 x 3 cases (None data, crypto data, stocks data) | Synthetic OHLCV fixture; assert dict or None, no crash |
| Unit — get_parameters | 13 x 3 branches (None, crypto, stocks) | Assert prefixed keys for `None`, matching profile for symbol |
| Unit — validate | 13 x 2 cases (valid params, zero param) | `True` with defaults, `False` with invalid |
| Unit — orchestrator fix | `_build_strategies_list()` | Mock scanner strategies; assert `"category"` in output dict |
| Unit — category fallback | Strategy without `category` attr | `getattr(strat, 'category', 'swing')` returns `"swing"` |

All tests live in `tests/test_fase18_3_doce_estrategias.py` with `@pytest.mark.parametrize`. No live API keys, Redis, or broker connections required.

## Migration / Rollout

No migration required. Feature-flag gated via `STRATEGIES_ENABLED` env var — new strategies are inactive until explicitly enabled. Rollback by PR: PR3 → PR2 → PR1. orchestrator.py fix (PR1) must merge first for correct menu display.

## Open Questions

None.
