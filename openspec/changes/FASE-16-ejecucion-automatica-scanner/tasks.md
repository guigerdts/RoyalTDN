# Tasks: FASE 16 — Ejecución Automática de Señales del Scanner

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450-550 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation) → PR 2 (Core) → PR 3 (UI + Tests) |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Base Branch |
|------|------|-----------|-------------|
| 1 | Foundation: PPM, RiskManager, Scanner source | PR 1 | feature/FASE-16-scanner-auto-exec |
| 2 | Core: Orchestrator refactor, main.py, DB migration | PR 2 | (PR 1 branch) |
| 3 | UI + Tests: Menu, Alerts, all tests | PR 3 | (PR 2 branch) |

## Phase 1: Foundation (PR 1 — base: feature/FASE-16-scanner-auto-exec)

- [x] **1.1** `src/royaltdn/risk/portfolio.py` — CREATE `Position` dataclass + `PortfolioPositionManager` class. Methods: `open_position` (reject dup, log), `close_position`, `get_position`, `get_all_positions`, `position_count`, `has_position`, `get_symbol_exposure`, `get_total_exposure`, `close_all_positions`. Exposure as fraction of equity. Verify: pytest covers all 10 methods + duplicate rejection + exposure math.
- [x] **1.2** `src/royaltdn/risk_manager.py` — ADD `check_portfolio_risk(portfolio, equity)` module-level function: max positions, total exposure cap (80%). MODIFY `get_atr()` to use `CryptoHistoricalDataClient` when `"/" in symbol`. `calculate_position_size()` and `check_risk_limits()` unchanged. Verify: portfolio gate rejects at cap, crypto ATR uses correct client.
- [x] **1.3** `src/royaltdn/scanner/scanner.py` — ADD `"source": "scanner"` to signal dict at line 132 in `scan()`. Verify: scan() output includes `source` key in every signal.

## Phase 2: Core Implementation (PR 2 — base: PR 1 branch)

- [ ] **2.1** `src/royaltdn/orchestrator.py` — REFACTOR `__init__`: remove `_position`, `_position_qty`, `_last_entry_price`, `_last_entry_order_id`, `_last_entry_at`. Add `self._portfolio = PortfolioPositionManager()`, `self.auto_execute`, `self.max_positions`, `self.scanner_top_n`. Add `_is_market_open(symbol)` helper (crypto bypass, stocks 9:30-16:00 ET). Verify: import works, new attrs present.
- [ ] **2.2** `src/royaltdn/orchestrator.py` — ADD `_execute_scanner_signals(signals)` with 7-gate pipeline: kill switch → has_position? → max positions? → SPY+legacy? → market closed? → exposure > 25%? → risk_limits? → ATR sizing → `_submit_order(symbol)` → PPM.open_position → DB record `source="scanner"` → Telegram. Verify: mock all gates, each skip path logged.
- [ ] **2.3** `src/royaltdn/orchestrator.py` — MODIFY `_submit_order()` to accept `symbol` parameter (default `self.symbol` for backward compat). MODIFY `_setup()` to sync ALL Alpaca positions into PPM (not just `self.symbol`). MODIFY `_build_positions_list()` to delegate to `PPM.get_all_positions()`. MODIFY `_run_legacy_loop()` scanner section to call `_execute_scanner_signals()` when `self.auto_execute` is True. Verify: legacy loop executes scanner signals via new method.
- [ ] **2.4** `src/royaltdn/main.py` — ADD env vars `AUTO_EXECUTE` (bool, default false), `MAX_POSITIONS` (int, default 5) in `cmd_run()`. Pass to `Orchestrator(..., auto_execute=AUTO_EXECUTE, max_positions=MAX_POSITIONS)`. Verify: defaults apply without env vars.
- [ ] **2.5** `src/royaltdn/storage/db.py` — ADD `source VARCHAR(20) NOT NULL DEFAULT 'sma_crossover'` column to trades table DDL (after `strategy`). Verify: DDL runs without error, `insert_trade()` accepts `source` param.

## Phase 3: UI + Tests (PR 3 — base: PR 2 branch)

- [ ] **3.1** `src/royaltdn/alerts.py` — ADD `notify_scanner_entry(signal, portfolio)` with symbol, action, qty, price + portfolio context (open count, total exposure). ADD `notify_scanner_rejection(symbol, reason)`. Verify: messages contain expected fields.
- [ ] **3.2** `src/royaltdn/frontend/menu/app.py` — MODIFY `_build_positions()` to handle multi-symbol position lists from PPM (already reads `open_positions` list, but verify display handles scanner + legacy positions). Verify: dashboard shows all open positions.
- [ ] **3.3** `tests/test_portfolio_manager.py` — Unit tests for PPM: open/close/get/all/count/has/exposure/close_all/dup-rejection/max-positions. Verify: 10+ test cases pass.
- [ ] **3.4** `tests/test_scanner_execution.py` — Integration tests for `_execute_scanner_signals()`: mock Alpaca, test 7-gate pipeline, legacy coexistence (SPY skip when legacy holds SPY), kill switch (`close_all_positions()` includes legacy SPY). Verify: all scenarios from spec pass.
- [ ] **3.5** `tests/test_risk_manager.py` — ADD tests for `check_portfolio_risk()` and crypto-aware `get_atr()`. Verify: portfolio gate, crypto ATR client dispatch.
