# Proposal: FASE 17.5 — Corrección de 6 bugs detectados en pruebas con Binance Testnet

## Intent

Fix 6 confirmed bugs discovered during Binance Testnet testing that block crypto trading: scanner displays mock entries as real signals, liquidity filter rejects all crypto pairs, backtest defaults to SPY in crypto mode, predefined strategy crashes on missing version field, backtest uses Yahoo Finance for crypto symbols, and menu header doesn't update after bot resume.

## Scope

### In Scope
- Bug 1: Filter mock entries (strategy == "mock") from scanner display
- Bug 2: Handle empty/NaN DataFrames in crypto liquidity filter + logging
- Bug 3: Default quick-backtest symbol to BTC/USDT when SCANNER_UNIVERSE=crypto
- Bug 4: Add `config.setdefault("version", 1)` before strategy validation
- Bug 5: Route crypto symbols (containing "/") to BinanceBroker.get_bars()
- Bug 6: Thread logs_dir parameter + immediate status.json rewrite on resume
- Verification: pytest per fix + manual smoke test on Binance Testnet

### Out of Scope
- New features or optimization beyond these 6 bugs
- Binance Testnet connection stability or rate-limit tuning
- Additional exchange support (Binance only)

## Capabilities

### New Capabilities
None — all fixes are internal corrections with no new spec-level behavior.

### Modified Capabilities
- `scanner-display`: Signal filtering logic (mock vs. real separation)
- `backtesting-engine`: Data source routing (yfinance vs. broker)
- `bot-lifecycle`: Status refresh timing on resume

## Approach

Grouped by risk and affected layer:
1. **UI + schema** (Bugs 1, 3, 4): Minute filtering, conditional default, single setdefault() — low risk, < 20 lines total
2. **Header timing** (Bug 6): Thread logs_dir param + synchronous status.json rewrite — isolated UI fix
3. **Data + broker routing** (Bugs 2, 5): NaN handling in crypto pipeline + symbol-based broker dispatch — medium effort, needs testing

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/royaltdn/frontend/menu/app.py` | Modified | Scanner filter, default symbol, header timing |
| `src/royaltdn/scanner/filters.py` | Modified | NaN handling in crypto volume |
| `src/royaltdn/main.py` | Modified | Crypto broker error logging |
| `src/royaltdn/orchestrator.py` | Modified | Strategy version setdefault |
| `src/royaltdn/strategy/schema.py` | Modified | Version default in schema |
| `src/royaltdn/strategy/backtesting.py` | Modified | Data source routing |
| `src/royaltdn/brokers/binance.py` | Modified | get_bars() method visibility |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Bug 5 broker wiring breaks existing stocks path | Low | Keep yfinance as fallback; test both universes |
| Bug 6 timing fix doesn't fully resolve race | Med | Add small sleep + verify status.json after write |
| Bug 2 fix masks underlying broker config issue | Med | Log detailed error before applying fallback |

## Rollback Plan

Each bug fix is an isolated commit. If any fix breaks production, revert its commit and open a separate re-fix PR. For Bug 5 (largest surface area), test both `stocks` and `crypto` SCANNER_UNIVERSE before merging.

## Delivery Strategy

Feature-branch-chain from `main` (3 chained PRs):
- **PR #1** (Bugs 1, 3, 4): UI filter + symbol default + schema fix — low risk, ~30 lines
- **PR #2** (Bug 6): Header refresh timing — isolated, ~15 lines
- **PR #3** (Bugs 2, 5): Crypto data path fix — medium risk, ~60 lines, needs testing

## Success Criteria

- [ ] Scanner shows "Sin señales" when only mock strategies exist
- [ ] Liquidity filter accepts crypto pairs with valid Binance data
- [ ] Quick backtest defaults to BTC/USDT when SCANNER_UNIVERSE=crypto
- [ ] Predefined strategy loads without "version must be 1" error
- [ ] Crypto backtest downloads from Binance, not Yahoo Finance
- [ ] Menu header reflects correct bot status immediately after resume
