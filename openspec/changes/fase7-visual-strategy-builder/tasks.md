# SDD Tasks: fase7-visual-strategy-builder

## Review Workload Forecast
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- Chain strategy: feature-branch-chain
- 400-line budget risk: High

## Phase 1 — Hito 1: Foundation (~600 lines)

- [x] 1.1 `src/royaltdn/strategy/__init__.py` updated with package exports | Verified: `from strategy.indicators import SMA` works | Deps: none
- [x] 1.2 `src/royaltdn/strategy/indicators.py` — 16 functions (SMA, EMA, RSI, MACD, BollingerBands, ATR, Volume, Ichimoku, SuperTrend, VWAP, ZScore, ADX, OBV, Stochastic, ParabolicSAR via pandas-ta; SmartMoneyFlowCloud manual) | Verified: each returns Series/DataFrame matching input length on 200-bar OHLCV; SMF returns 9 columns | Deps: 1.1
- [x] 1.3 `src/royaltdn/strategy/rule_engine.py` — `evaluate(tree, indicators, data) -> bool` + `validate_tree(tree) -> bool` | Verified: AND(RSI>30, ADX>15) returns True; nested AND/OR at depth 2 works; validate_tree catches missing operator; empty conditions evaluate to False | Deps: 1.1
- [x] 1.4 `src/royaltdn/strategy/schema.py` — `validate_config(config) -> (bool, str)` for JSON v1 | Verified: valid config returns (True, ""); invalid version/name/symbols/timeframe/indicator/risk_management all fail correctly; nested rules validated | Deps: 1.1

## Phase 2 — Hito 2: Core Strategy (~400 lines)

- [x] 2.1 `src/royaltdn/strategy/strategy_store.py` — StrategyStore CRUD class (save atomic, load, load_all, list_names, delete, get_history) | Verified: save with timestamp+ms atomic write; load returns latest; delete removes all; history returns 2 versions | Deps: 1.1, 1.4
- [x] 2.2 `src/royaltdn/strategy/dynamic.py` — DynamicStrategy(BaseStrategy) with generate_signal, from_file, get_parameters, validate | Verified: BUY on RSI>30 entry; SELL on RSI<70 exit; impossible rules return None; invalid config returns validate()=False; empty data returns None | Deps: 1.2, 1.3, 1.4
- [x] 2.3 `user_strategies/` dir + `.gitkeep` + tests | Verified: 11 tests pass (5 dynamic + 4 store + 2 integration); all old tests still pass | Deps: 2.1

## Phase 3 — Hito 3: Builder UI (~500 lines)

- [ ] 3.1 Create `src/royaltdn/frontend/components/builder_state.py` — session_state getters/setters for `strategy_config`, `indicators_added`, `rules`, `backtest_results`, `strategy_deployed` | Verify: state persists across reruns; sliders trigger update; initial values empty | Deps: 1.1
- [ ] 3.2 Create `src/royaltdn/frontend/pages/builder.py` — 3-column layout (30/40/30): left=indicator picker (16) + param sliders + rule tree editor (max 2 levels); center=auto-backtest + Plotly equity + metrics table; right=JSON preview + Save/Deploy buttons + error toasts | Verify: page renders 3 columns; selecting SMA shows Period+Source; 3rd nesting level blocked with toast; param change triggers backtest; Save writes timestamped JSON; Deploy updates .active | Deps: 1.2, 1.3, 1.4, 2.1, 2.2, 3.1

## Phase 4 — Hito 4: Backtesting (~400 lines)

- [ ] 4.1 Create `src/royaltdn/strategy/backtesting.py` — `BacktestEngine` with `__init__(config)`, `run() -> dict`, `config_hash` (SHA-256); yfinance mapping (1m=7d, 5m/15m=60d, 1H=730d, 1D=5y); VectorBT Portfolio; `@st.cache_data` by hash | Verify: SPY 1D + RSI>70 returns all 7 result fields; empty rules → 0 trades + flat equity; cache hit skips yfinance; invalid ticker returns error field | Deps: 1.2, 1.3
- [ ] 4.2 Create `src/royaltdn/frontend/components/backtest_charts.py` — Plotly equity curve (green/red return), drawdown area, monthly heatmap, metrics table (Return/Sharpe/WinRate/MaxDD/Trades) | Verify: positive return green; max DD always red; 0 trades shows "No signals generated" annotation | Deps: 4.1

## Phase 5 — Hito 5: Integration (~200 lines)

- [ ] 5.1 Modify `src/royaltdn/orchestrator.py` — in `_run_legacy_loop()`: every 30th iteration after `_publish_status()`, call watcher to scan `user_strategies/*.json` (ignore .tmp), validate via schema, create/replace DynamicStrategy | Verify: new JSON loaded within 60s; corrupt JSON skipped with warning; .tmp ignored; missing .active → predefined only | Deps: 1.4, 2.1, 2.2, 2.3
- [ ] 5.2 Modify `src/royaltdn/frontend/app.py` — add builder page to `st.navigation` pages list | Verify: Builder appears in sidebar nav; clicking loads builder page | Deps: 3.2
- [ ] 5.3 Create `requirements/fase7.txt` — `pandas-ta`, `yfinance`, `vectorbt[full]` | Verify: `pip install -r requirements/fase7.txt` succeeds; imports work | Deps: none