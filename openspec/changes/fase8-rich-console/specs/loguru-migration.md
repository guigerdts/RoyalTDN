# Loguru Migration Specification

## Purpose

Replace stdlib `logging` with Loguru across all non-frontend modules. Remove all `logging.basicConfig()` and `FileHandler` setup from `main.py`. Single configuration point in `main.py` with 3 sinks: file rotation, stderr (colorized), and in-memory LogBuffer for console.

## Requirements

### Requirement: LogBuffer (in-memory circular buffer for console log screen)

A `LogBuffer` class SHALL be implemented in `src/royaltdn/console/log_buffer.py`. It acts as a Loguru sink — a callable that accepts a log record string.

#### Scenario: LogBuffer adds and trims

- GIVEN a LogBuffer with `max_lines=200`
- WHEN 250 records are added
- THEN `len(buffer.get_lines())` is 200 (oldest 50 trimmed)

#### Scenario: LogBuffer filters by level

- GIVEN LogBuffer has records at INFO, WARNING, ERROR, DEBUG levels
- WHEN `get_lines(level_filter="WARNING")` is called
- THEN only WARNING-level records are returned
- AND count matches the number of WARNING records

#### Scenario: LogBuffer returns recent N

- GIVEN LogBuffer has 100 records
- WHEN `get_recent(n=5)` is called
- THEN the last 5 records are returned in order

### Requirement: Loguru Configuration

`main.py` MUST be the single Loguru configuration point. The configuration initializes 3 sinks:

#### Scenario: File sink configured with rotation

- GIVEN `main.py` starts
- WHEN Loguru is configured
- THEN `logs/bot.log` is created with 10 MB rotation and 7-day retention
- AND format matches `{time} | {level} | {name}:{function}:{line} | {message}`

#### Scenario: Console sink with colors

- GIVEN `main.py` starts
- WHEN Loguru is configured
- THEN stderr sink has `colorize=True` at DEBUG level
- AND format includes Rich markup tags: `<green>`, `<level>`, `<cyan>`

#### Scenario: LogBuffer sink attached

- GIVEN `main.py` starts
- WHEN Loguru is configured
- THEN `logger.add(log_buffer.add, level="DEBUG")` is called
- AND LogBuffer is accessible from the console module

### Requirement: Migration Pattern — All 15 Production Modules

The following files MUST be migrated from `import logging` + `logging.getLogger()` to `from loguru import logger`. Replace `import logging` with `from loguru import logger`. Remove the `logger = logging.getLogger(...)` line. Keep all logger call sites unchanged (syntax-compatible for `.info()`, `.warning()`, `.error()`, `.debug()`, `.critical()`).

Files to migrate (frontend files to be deleted — excluded):

| # | Module | Current Pattern | Action |
|---|--------|----------------|--------|
| 1 | `src/royaltdn/main.py` | `import logging` + `basicConfig` + `getLogger` | Replace + configure sinks |
| 2 | `src/royaltdn/orchestrator.py` | `import logging` + `getLogger` | Replace |
| 3 | `src/royaltdn/ingestion/data_ingestor.py` | `import logging` + `getLogger` | Replace |
| 4 | `src/royaltdn/strategy/sma_strategy.py` | `import logging` + `getLogger` | Replace |
| 5 | `src/royaltdn/strategy/bollinger_rsi.py` | `import logging` + `getLogger` | Replace |
| 6 | `src/royaltdn/strategy/momentum_atr.py` | `import logging` + `getLogger` | Replace |
| 7 | `src/royaltdn/strategy/factor_rotation.py` | `import logging` + `getLogger` | Replace |
| 8 | `src/royaltdn/execution/twap.py` | `import logging` + `getLogger` | Replace |
| 9 | `src/royaltdn/storage/db.py` | `import logging` + `getLogger` | Replace |
| 10 | `src/royaltdn/monitoring/tca.py` | `import logging` + `getLogger` | Replace |
| 11 | `src/royaltdn/scanner/scanner.py` | `import logging` + `getLogger` | Replace |
| 12 | `src/royaltdn/scanner/filters.py` | `import logging` + `getLogger` | Replace |
| 13 | `src/royaltdn/scanner/universe.py` | `import logging` + `getLogger` | Replace |
| 14 | `src/royaltdn/risk_manager.py` | `import logging` + `getLogger` | Replace |
| 15 | `src/royaltdn/alerts.py` | `import logging` + `getLogger` | Replace |
| 16 | `src/royaltdn/legacy_polling.py` | `import logging` + `getLogger` | Replace |

#### Scenario: Migration produces identical log output format

- GIVEN a module before and after migration
- WHEN the module logs `logger.info("Test %s", "value")`
- THEN the Loguru output format matches the original `logging` format (same datetime precision, same field order)
- AND the level field is right-aligned to 8 characters

#### Scenario: Zero stdlib logging calls remain

- GIVEN all 16 files are migrated
- WHEN searching for `import logging` or `logging.getLogger` across `src/royaltdn/` (excluding `__pycache__`, frontend/)
- THEN zero matches are found

## Acceptance Criteria

1. [CRITICAL] Zero `import logging` or `logging.getLogger` calls remain in non-frontend production code
2. [CRITICAL] `logs/bot.log` rotation works at 10 MB — no unbounded log growth
3. [CRITICAL] LogBuffer provides last 200 lines for console log screen
4. [MAJOR] Loguru sink config is in exactly one place (`main.py`)
5. [MAJOR] All log format strings in `%` style are converted to `{}` style for Loguru
6. [MINOR] Console stderr output is colorized per log level
