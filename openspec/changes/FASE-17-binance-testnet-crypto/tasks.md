# Tasks: FASE-17-binance-testnet-crypto

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~660-810 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Work Unit Map

| Unit | Goal | Branch | Base Branch |
|------|------|--------|-------------|
| 1 | BaseBroker ABC + AlpacaBroker refactor + tests | feature/FASE-17-binance-testnet-crypto | tracker branch |
| 2 | BinanceBroker + symbol normalization + tests | PR 1 branch | PR 1 branch |
| 3 | Orchestrator + PPM + RiskManager + Scanner multi-broker routing | PR 2 branch | PR 2 branch |
| 4 | UI Broker column (menu + textual) + integration tests | PR 3 branch | PR 3 branch |

## PR 1: BaseBroker + AlpacaBroker refactor (~150-200 lines, ~6 files)

**Base**: tracker branch
**Scope**: Broker interface definition and Alpaca extraction without behavioral change.

- [x] **1.1** Create `src/royaltdn/brokers/__init__.py` — package init, exports BaseBroker, OrderResult, AlpacaBroker
- [x] **1.2** Create `src/royaltdn/brokers/base.py` — BaseBroker ABC with 7 abstract methods + OrderResult dataclass
- [x] **1.3** Create `src/royaltdn/brokers/alpaca.py` — AlpacaBroker refactoring all existing TradingClient logic
- [x] **1.4** Modify `src/royaltdn/main.py` — import AlpacaBroker, pass brokers dict to Orchestrator
- [x] **1.5** Modify `src/royaltdn/orchestrator.py` — accept brokers: Dict[str, BaseBroker] in __init__, refactor _submit_order/_get_current_equity/_get_order_id/_get_filled_price to use self._broker, add close_position()
- [x] **1.6** Create `tests/test_alpaca_broker.py` — mock TradingClient/StockHistoricalDataClient/CryptoHistoricalDataClient, test all 7 methods + routing

## PR 2: BinanceBroker + symbol normalization (~200-250 lines, ~4 files)

**Base**: PR 1 branch

- [x] **2.1** Create `src/royaltdn/brokers/binance.py` — BinanceBroker with HMAC-SHA-256, all 7 methods (no external SDK)
- [x] **2.2** Update `src/royaltdn/brokers/__init__.py` — add BinanceBroker export
- [x] **2.3** Modify `.env.example` — add Binance Testnet env vars section
- [x] **2.4** Create `tests/test_binance_broker.py` — 20 tests covering HMAC signing, symbol normalization, all methods

> **Note**: `main.py` BinanceBroker wiring deferred to PR 3 per delivery guard (Orchestrator routing).

## PR 3: Orchestrator multi-broker + PPM + RiskManager + Scanner (~150-200 lines, ~6 files)

**Base**: PR 2 branch

- [x] **3.1** Add `_get_broker_for_symbol(symbol)` to Orchestrator — "/" in symbol → crypto broker, else stocks
- [x] **3.2** Refactor ALL broker calls in Orchestrator (_submit_order, _execute_scanner_signals, _execute_signal, _get_current_equity, close_position, _get_atr_value, _is_market_open, _setup, _build_positions_list)
- [x] **3.3** Refactor `_execute_scanner_signals()` for per-symbol broker routing + multi-broker kill switch
- [x] **3.4** Add `broker: str = "alpaca"` field to Position dataclass
- [x] **3.5** PPM composite key f"{broker}:{symbol}", add get_positions_by_broker(), backward-compat helpers
- [x] **3.6** RiskManager check_portfolio_risk combined equity across all brokers
- [x] **3.7** Kill switch iterates all brokers for close_position (both PPM + direct broker safety net)
- [x] **3.8** get_atr() accepts `broker: BaseBroker` param, uses broker.get_bars() for ATR calculation
- [x] **3.9** Scanner._batch_get_symbol_data routes crypto to brokers["crypto"].get_bars()
- [x] **3.10** LiquidityFilter.filter() uses broker.get_bars() for crypto symbols

## PR 4: UI Broker column + integration tests (~70-100 lines, ~3 files)

**Base**: PR 3 branch

- [x] **4.1** Menu `_build_positions()` add "Broker" column after "Strategy"
- [x] **4.2** Textual `_append_positions()` add "Broker" column after "P&L"
- [x] **4.3** Add tests to `tests/test_multi_broker.py` — UI broker dict, full pipeline mock, invalid broker config

## Risk Summary

| Risk | Impact | Mitigation |
|------|--------|------------|
| Symbol format mismatch (BTC/USD vs BTCUSDT) | Orders fail silently | normalize_symbol() per broker; spec scenarios |
| Composite key collision (PPM) | Wrong position closed | f"{broker}:{symbol}" format |
| Alpaca refactor breaks tests | Regression | PR 1 isolated; existing tests must pass |
| Legacy loop uses TradingClient directly | Inconsistent | Deliberate; legacy mode deprecated |
| Binance Testnet API differs from production | Surprises | testnet URL; BINANCE_TESTNET=true for dev |
