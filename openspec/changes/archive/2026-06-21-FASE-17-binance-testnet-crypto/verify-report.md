# Verification Report

**Change**: FASE-17-binance-testnet-crypto
**Version**: N/A
**Mode**: Standard (no Strict TDD)

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 20 |
| Tasks complete | 20 |
| Tasks incomplete | 0 |

All 20 tasks across 4 PRs are confirmed `[x]` in the apply-progress artifact.

## Build & Tests Execution

**Static analysis**: ✅ All 15 source/test files pass `py_compile` syntax check
**Logic verification**: ✅ HMAC signing, normalize_symbol, composite keys, symbol routing all pass inline verification

**Tests**: ⚠️ 60 tests total — **cannot execute on this environment** (pre-existing numpy C-extension incompatibility on Termux/Android)

```text
ERROR collecting: ImportError — numpy._core._multiarray_umath not found
This is a known environment issue: the numpy .so files were compiled for
glibc (manylinux) but Android/Termux uses a different C runtime.
```

The apply-progress confirms all tests passed in a proper environment:
- `test_alpaca_broker.py`: 14/14 PASSED (PR 1)
- `test_binance_broker.py`: 20/20 PASSED (PR 2)
- `test_multi_broker.py`: 26/26 PASSED (23 existing + 3 new for PR 4)

**Coverage**: ➖ Not available in this environment

## Spec Compliance Matrix

| Domain | Requirement | Scenario | Test | Result |
|--------|-------------|----------|------|--------|
| broker-interface | REQ-BROKER-BASE | BaseBroker ABC with 7 abstract methods | `test_alpaca_broker.py` > `TestBaseBrokerInterface` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-BASE | BaseBroker ABC with 7 abstract methods | `test_binance_broker.py` > `TestBaseBrokerInterface` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-ALPACA | AlpacaBroker submit_order returns OrderResult | `test_alpaca_broker.py` > `TestSubmitOrder` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-ALPACA | get_bars("BTC/USD") → CryptoHistoricalDataClient | `test_alpaca_broker.py` > `TestGetBars.test_crypto_symbol_uses_crypto_client` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-ALPACA | get_bars("SPY") → StockHistoricalDataClient | `test_alpaca_broker.py` > `TestGetBars.test_stock_symbol_uses_stock_client` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-ALPACA | is_market_open("BTC/USD") → True | `test_alpaca_broker.py` > `TestIsMarketOpen.test_crypto_always_open` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-ALPACA | is_market_open("SPY") → Clock API | `test_alpaca_broker.py` > `TestIsMarketOpen.test_stock_delegates_to_clock` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-ALPACA | normalize_symbol("SPY") → "SPY" | `test_alpaca_broker.py` > `TestNormalizeSymbol` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-ALPACA | normalize_symbol("BTC/USD") → "BTC/USD" | `test_alpaca_broker.py` > `TestNormalizeSymbol` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-BINANCE | BINANCE_TESTNET=true → testnet URL | `test_binance_broker.py` > `TestBedUrl.test_testnet_url` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-BINANCE | normalize_symbol("ETH/USD") → "ETHUSDT" | `test_binance_broker.py` > `TestNormalizeSymbol.test_eth_usd` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-BINANCE | get_bars → OHLCV DataFrame | `test_binance_broker.py` > `TestGetBars.test_returns_dataframe` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-BINANCE | submit_order → OrderResult(FILLED) | `test_binance_broker.py` > `TestSubmitOrder` | ✅ COMPLIANT |
| broker-interface | REQ-BROKER-BINANCE | is_market_open → True always | `test_binance_broker.py` > `TestIsMarketOpen` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Multi-Broker | broker param in open_position | `test_multi_broker.py` > `TestPPMCompositeKey.test_position_dataclass_has_broker_field` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Multi-Broker | Composite key broker:symbol | `test_multi_broker.py` > `TestPPMCompositeKey.test_ppm_composite_key` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Multi-Broker | Same symbol, different broker → no collision | `test_multi_broker.py` > `TestPPMCompositeKey.test_ppm_no_collision_same_symbol_different_broker` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Multi-Broker | get_positions_by_broker() filter | `test_multi_broker.py` > `TestPPMGetPositionsByBroker` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Multi-Broker | get_symbol_exposure with broker filter | `test_multi_broker.py` > `TestPPMTotalExposure` | ✅ COMPLIANT |
| scanner-auto-execution | EXEC-BROKER-ROUTING | BTC/USD → BinanceBroker | `test_multi_broker.py` > `TestGetBrokerForSymbol.test_crypto_routes_to_binance` | ✅ COMPLIANT |
| scanner-auto-execution | EXEC-BROKER-ROUTING | SPY → AlpacaBroker | `test_multi_broker.py` > `TestGetBrokerForSymbol.test_stock_routes_to_alpaca` | ✅ COMPLIANT |
| scanner-auto-execution | EXEC-BROKER-ROUTING | Fallback when no crypto broker | `test_multi_broker.py` > `TestGetBrokerForSymbol.test_fallback_to_stocks_when_no_crypto` | ✅ COMPLIANT |
| scanner-auto-execution | Risk Multi-Broker | Combined equity across brokers | `test_multi_broker.py` > `TestRiskManagerCombinedEquity` | ✅ COMPLIANT |
| scanner-auto-execution | Risk Multi-Broker | Kill switch iterates all brokers | `test_multi_broker.py` > `TestRiskManagerKillSwitch` | ✅ COMPLIANT |
| scanner-auto-execution | Risk Multi-Broker | get_atr() with broker param | `test_multi_broker.py` > `TestGetAtrWithBroker` | ✅ COMPLIANT |
| scanner-auto-execution | Risk Multi-Broker | ATR returns 0.0 on insufficient data | `test_multi_broker.py` > `TestGetAtrWithBroker.test_get_atr_with_broker_insufficient_data` | ✅ COMPLIANT |
| scanner-auto-execution | LEGACY-KILL-GLOBAL | Legacy loop uses stocks broker | `test_multi_broker.py` > `TestLegacyLoopUsesAlpaca` | ✅ COMPLIANT |
| scanner-auto-execution | LEGACY-KILL-GLOBAL | close_position delegates to stocks broker | `test_multi_broker.py` > `TestLegacyLoopUsesAlpaca.test_legacy_loop_close_position_uses_stocks_broker` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Backward Compat | open_position defaults to alpaca | `test_multi_broker.py` > `TestPPMBackwardCompat.test_open_position_defaults_to_alpaca` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Backward Compat | close_position without broker searches all | `test_multi_broker.py` > `TestPPMBackwardCompat.test_close_position_without_broker` | ✅ COMPLIANT |
| scanner-auto-execution | PPM Backward Compat | get_position without broker searches all | `test_multi_broker.py` > `TestPPMBackwardCompat.test_get_position_without_broker` | ✅ COMPLIANT |
| crypto-scanner | REQ-CRYPTO-LIQUIDITY | Crypto symbols use broker.get_bars() | Code verification: `LiquidityFilter.filter()` lines 144-163 | ✅ COMPLIANT |
| crypto-scanner | REQ-CRYPTO-SCANNER | Scanner routes crypto to broker.get_bars() | Code verification: `Scanner._batch_get_symbol_data` lines 311-340 | ✅ COMPLIANT |
| crypto-scanner | REQ-CRYPTO-MAIN | BinanceBroker created and passed to Scanner | Code verification: `main.py` lines 246-250, 296-300 | ✅ COMPLIANT |
| interactive-menu | Dashboard Broker column | "Broker" column after "Strategy" in positions | Code verification: `menu/app.py` `_build_positions()` line 1054 | ✅ COMPLIANT |
| textual-tui | Dashboard Broker column | "Broker" column after "P&L" in positions | Code verification: `dashboard.py` `_append_positions()` line 139 | ✅ COMPLIANT |
| UI | Position dict includes broker | broker key in _build_positions_list() | `test_multi_broker.py` > `TestUIPositionDictIncludesBroker` | ✅ COMPLIANT |
| Integration | Full pipeline mock | Both brokers, per-symbol delegation | `test_multi_broker.py` > `TestFullPipelineMock` | ✅ COMPLIANT |
| Integration | Invalid broker config | Empty/invalid brokers → no crash | `test_multi_broker.py` > `TestInvalidBrokerConfig` | ✅ COMPLIANT |

**Compliance summary**: 38/38 scenarios compliant

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| BaseBroker ABC with OrderResult dataclass | ✅ Implemented | 7 abstract methods, ABC from `abc`, NotImplementedError pattern |
| AlpacaBroker wraps TradingClient | ✅ Implemented | 3 lazy-imported SDK clients, all 7 methods wired |
| BinanceBroker pure requests+HMAC | ✅ Implemented | No SDK dependency, _sign/_signed_request pattern |
| Symbol routing "/" → crypto | ✅ Implemented | `_get_broker_for_symbol()` in orchestrator.py and scanner.py |
| PPM composite key broker:symbol | ✅ Implemented | `_make_key()` returns `f"{broker}:{symbol}"` |
| PPM backward compatibility | ✅ Implemented | broker=None searches all keys |
| Kill switch iterates all brokers | ✅ Implemented | Both `_execute_signal()` and `_execute_scanner_signals()` |
| get_atr() accepts broker param | ✅ Implemented | Uses `broker.get_bars()` when provided |
| Scanner crypto routing | ✅ Implemented | `_batch_get_symbol_data()` → crypto_broker.get_bars() |
| LiquidityFilter crypto routing | ✅ Implemented | `filter()` → broker.get_bars() for crypto |
| Menu Broker column | ✅ Implemented | Added after "Strategy" in `_build_positions()` |
| Textual Broker column | ✅ Implemented | Added after "P&L" in `_append_positions()` |
| Env vars for Binance | ✅ Implemented | BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_TESTNET in main.py |
| Main.py creates BinanceBroker | ✅ Implemented | When BINANCE_API_KEY is set |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| BaseBroker ABC with 7 abstract methods | ✅ Yes | ABC from `abc`, methods raise NotImplementedError |
| AlpacaBroker wraps TradingClient | ✅ Yes | Delegates orders, positions, balance to Alpaca SDK |
| BinanceBroker pure requests+HMAC | ✅ Yes | No SDK dependency, HMAC-SHA-256 signature |
| Symbol routing by "/" | ✅ Yes | "/" in symbol → BinanceBroker, else → AlpacaBroker |
| PPM composite key `broker:symbol` | ✅ Yes | Keys prefixed with broker name |
| Kill switch iterates all brokers | ✅ Yes | Both broker.close_position() called |
| Scanner uses broker.get_bars() for crypto | ✅ Yes | Crypto data via BinanceBroker, stocks via existing |
| Dashboard shows Broker column | ✅ Yes | Column added after Strategy (menu) / after P&L (textual) |
| Legacy loop preserved | ✅ Yes | Direct TradingClient for SPY kept intact |
| Feature Branch Chain (4 PRs) | ✅ Yes | PRs 1-4 implemented in order |
| Hybrid persistence | ✅ Yes | Both Engram and filesystem |

## Issues Found

**CRITICAL**: None
**WARNING**: 
- Pre-existing numpy C-extension incompatibility on Termux/Android prevents test execution in this environment — tests confirmed passed elsewhere (60/60)
**SUGGESTION**:
- Textual dashboard column position differs from original spec: spec said "after Strategy" but textual dashboard has no Strategy column; correctly placed after "P&L" instead

## Verdict

**PASS WITH WARNINGS**

All 20 tasks complete, all 38 spec scenarios compliant, all 8 key design decisions followed, all 15 implementation files pass syntax checking, core logic verified inline. The only caveat is a pre-existing environment limitation preventing test execution in this Termux session — tests were confirmed passing (60/60) in the apply-progress artifact.
