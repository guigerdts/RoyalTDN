# Check-Readiness Specification

## Purpose

Provide a `check-readiness` command that validates the bot is ready for real-money trading through 6 independent checks and a Rich Panel output with a final verdict.

## Requirements

### Requirement 1: Six readiness checks

The system MUST implement exactly 6 checks, each returning a dict with `name` (str), `passed` (bool), `detail` (str), and `severity` (`"critical"` or `"warning"`):

| # | Check | Source | Pass Condition | Severity |
|---|-------|--------|----------------|----------|
| 1 | Trades suficientes | `logs/trades.json` | trades count >= 50 | critical |
| 2 | Sharpe reciente | `logs/equity.json` | 30-day Sharpe > 0.5 | critical |
| 3 | Slippage aceptable | `logs/trades.json` | avg slippage < 50 bps | critical |
| 4 | Kill switch probado | `bot.log` | grep "KILL SWITCH" or "drawdown >" found | critical |
| 5 | Telegram funciona | `bot.log` | "Telegram enviado" found within last 24h | warning |
| 6 | Broker conectividad | Alpaca + Binance API | both respond to ping/status endpoint | critical |

#### Scenario: all checks pass
- GIVEN trades.json has 52 trades, equity.json shows Sharpe 0.8, slippage 20bps, bot.log has kill switch and Telegram entries, brokers respond
- WHEN `check-readiness` runs
- THEN all 6 checks return `passed: True`

#### Scenario: insufficient trades
- GIVEN trades.json has 30 trades
- WHEN check 1 runs
- THEN `passed: False` with detail showing "30/50 trades"
- AND severity is `"critical"`

#### Scenario: Telegram not tested
- GIVEN bot.log has no "Telegram enviado" in last 24h
- WHEN check 5 runs
- THEN `passed: False` with detail indicating Telegram not verified
- AND severity is `"warning"` (non-blocking)

#### Scenario: broker disconnects
- GIVEN Alpaca API is unreachable
- WHEN check 6 runs
- THEN `passed: False` with detail showing "Alpaca: timeout"
- AND severity is `"critical"`

### Requirement 2: Rich Panel output

The output SHALL render as a Rich `Panel` with title `"🔍 Verificación de Readiness"`.

Each check SHALL be rendered as a row:
- `✅ {name}` (green) when passed
- `❌ {name}` (red) when failed, with the `detail` shown in `[dim]` below

The panel SHALL use `color_system="standard"` (16-color ANSI).

#### Scenario: panel renders correctly
- GIVEN all checks processed
- WHEN `check-readiness` outputs
- THEN a Rich Panel is rendered with all 6 checks as rows, colored appropriately

### Requirement 3: Verdict system

After the 6 checks, the system SHALL display a final verdict line:

| Condition | Verdict |
|-----------|---------|
| All 6 passed | `"✅ READY — Todas las verificaciones OK"` (green) |
| 0 critical + 1+ warning failed | `"⚠️ CASI LISTO — {N} pendiente(s)"` (yellow) |
| 1+ critical failed | `"❌ NO RECOMENDADO — Pruebas insuficientes"` (red) |

#### Scenario: verdict READY
- GIVEN all 6 checks pass
- WHEN verdict is computed
- THEN display `"✅ READY — Todas las verificaciones OK"` in green

#### Scenario: verdict CASI LISTO
- GIVEN only Telegram check failed (severity warning)
- WHEN verdict is computed
- THEN display `"⚠️ CASI LISTO — 1 pendiente(s)"` in yellow

#### Scenario: verdict NO RECOMENDADO
- GIVEN trades check failed (severity critical)
- WHEN verdict is computed
- THEN display `"❌ NO RECOMENDADO — Pruebas insuficientes"` in red

### Requirement 4: CLI command

The system SHALL support `python -m royaltdn check-readiness` as a standalone CLI command.

The command SHALL NOT start the bot — it runs the checks, prints the result, and exits with exit code 0 (READY), 1 (CASI LISTO), or 2 (NO RECOMENDADO).

#### Scenario: CLI command standalone
- GIVEN all checks pass
- WHEN `python -m royaltdn check-readiness` is executed
- THEN the panel is printed AND exit code is 0 AND the bot does NOT start

#### Scenario: CLI command returns exit code 2
- GIVEN trades check fails (critical)
- WHEN `python -m royaltdn check-readiness` is executed
- THEN exit code is 2
