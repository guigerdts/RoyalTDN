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

- [x] 3.1 `src/royaltdn/frontend/components/builder_state.py` — session_state getters/setters for builder_indicators, entry/exit conditions, config, JSON view, save/deploy flags | Verified: init, add/remove indicator, add/remove conditions, build_config, validate, load_config_into_state, reset | Deps: 1.1
- [x] 3.2 `src/royaltdn/frontend/pages/builder.py` — 3-column Streamlit page (left=indicator palette + rules; center=JSON preview + backtest placeholder; right=save/load/deploy + risk mgmt) | Verified: imports correctly, integrated with StrategyStore + schema validation, 16 indicator defs with param forms, 30+ operators in 7 groups | Deps: 1.2, 1.3, 1.4, 2.1, 2.2, 3.1

## Phase 4 — Hito 4: Backtesting (~400 lines)

- [x] 4.1 `src/royaltdn/strategy/backtesting.py` — `run_backtest()` with yfinance data download, DynamicStrategy signal generation, portfolio simulation, metrics computation | Verified: import OK, invalid config returns error, no-trades config handled gracefully, metrics computed correctly | Deps: 1.2, 1.3
- [x] 4.2 `src/royaltdn/frontend/components/backtest_charts.py` — Plotly equity curve, drawdown, trade distribution, monthly heatmap, metrics cards | Verified: imports OK, all chart functions return valid figures | Deps: 4.1
- [x] 4.3 Builder integration — backtesting section in center column replaces placeholder; Run Backtest button triggers real backtest; metrics cards + charts displayed | Verified: button disabled when no entry conditions; results show metrics + 4 charts + trade table | Deps: 3.2, 4.1, 4.2

## Phase 5 — Hito 5: Integration (~200 lines)

- [ ] 5.1 Modify `src/royaltdn/orchestrator.py` — in `_run_legacy_loop()`: every 30th iteration after `_publish_status()`, call watcher to scan `user_strategies/*.json` (ignore .tmp), validate via schema, create/replace DynamicStrategy | Verify: new JSON loaded within 60s; corrupt JSON skipped with warning; .tmp ignored; missing .active → predefined only | Deps: 1.4, 2.1, 2.2, 2.3
- [ ] 5.2 Modify `src/royaltdn/frontend/app.py` — add builder page to `st.navigation` pages list | Verify: Builder appears in sidebar nav; clicking loads builder page | Deps: 3.2
- [ ] 5.3 Create `requirements/fase7.txt` — `pandas-ta`, `yfinance`, `vectorbt[full]` | Verify: `pip install -r requirements/fase7.txt` succeeds; imports work | Deps: none