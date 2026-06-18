# Proposal: Fase 7 — Visual Strategy Builder

## Intent

Non-programmer users can't create strategies — 4 are hardcoded. This adds a visual rule builder + DynamicStrategy engine to compose 15 indicators with AND/OR rules, backtest, and deploy without touching code.

## Scope

**In Scope**: Indicators module (pandas-ta, 15 indicators) · Rule engine (JSON trees, 2-level nesting) · DynamicStrategy (generate BUY/SELL from JSON) · Builder UI (Streamlit) · Strategy store (`logs/strategies_user/`, schema v1) · Backtesting (VectorBT + Yahoo Finance, cached by hash) · Hot-deploy (30s polling watcher)
**Out of Scope**: Fase 8 · VPS · Modifying bot behavior beyond watcher · Removing existing strategies

## Capabilities

- `visual-strategy-builder`: Builder page + indicator picker + rule editor
- `dynamic-strategy-engine`: DynamicStrategy + indicators + recursive eval
- `user-strategy-deployment`: JSON schema, save/load, 30s polling watcher
- `strategy-backtesting`: VectorBT + Yahoo Finance + `@st.cache_data` by JSON hash

## Approach

pandas-ta computes all 15 indicators from OHLCV. Rule engine evaluates JSON trees (depth ≤ 2). DynamicStrategy wraps config dict → `generate_signal()`. Backtesting: VectorBT + Yahoo Finance, cached by hash. Watcher polls `logs/strategies_user/` every 30s. 5 milestones (Hito 1–5).

## Affected Areas

| Area | | |
|------|---|---|
| `indicators.py`, `rule_engine.py`, `dynamic_strategy.py` | New | Indicators + rules + strategy |
| `strategy_schema.py`, `strategy_store.py` | New | JSON schema + CRUD |
| `watcher.py` | New | 30s polling |
| `backtesting/engine.py`, `backtesting/data.py` | New | VectorBT + yfinance |
| `frontend/pages/builder.py` | New | Builder UI |
| `orchestrator.py`, `frontend/app.py` | Modified | Watcher + nav |
| `requirements/fase7.txt` | New | pandas-ta, yfinance |

## Risks

| Risk | Like. | Mitigation |
|------|-------|------------|
| Ichimoku needs 52+ periods | Med | Skip indicator, warn user |
| VectorBT slow in Streamlit | Med | `@st.cache_data` by config hash |
| JSON schema drift | Low | Version field on every file |
| Watcher misses file mid-write | Low | Atomic write + 30s window |

## Rollback Plan

Remove watcher from `orchestrator.py`, delete `logs/strategies_user/`. Existing strategies intact.

## Milestones

- **Hito 1**: indicators.py, rule_engine.py, strategy_schema.py
- **Hito 2**: DynamicStrategy — consume JSON, generate signals
- **Hito 3**: Builder UI — indicator picker, params, rules, preview
- **Hito 4**: Strategy store + backtesting — save/load JSON, VectorBT
- **Hito 5**: Integration — watcher, orchestrator wiring, navigation, deps

## Success Criteria

- [ ] Builder page loads, selects all 15 indicators
- [ ] Strategy JSON saves to `logs/strategies_user/` and reloads
- [ ] Backtesting shows equity curve, P&L, win rate, Sharpe
- [ ] DynamicStrategy generates BUY/SELL matching rules
- [ ] Hot-deploy detects new file within 30s
- [ ] All Fase 6 pages continue working unchanged
