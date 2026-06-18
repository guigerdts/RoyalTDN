# Rich Console Specification

## Purpose

Replace the Streamlit web frontend with a keyboard-navigable TUI dashboard using Rich `Live`. The console is a read-only consumer of `logs/*.json` — it renders 5 screens with live-updating data at 4 FPS.

## Requirements

### Requirement: Screen Layouts

The system MUST render 5 keyboard-navigable screens. Each screen SHALL re-read all JSON files each cycle and render data as described.

#### Dashboard Screen

- **Layout**: Header (3 rows) + body (2 cols, 60/40 ratio) + footer
- **Header**: "ROYALTDN" title, mode badge (LEGACY/MODULAR), status badge (ONLINE green/OFFLINE red/KILLED yellow), uptime clock, next-scan countdown
- **Left column (60%)**: KPI cards (Capital, P&L Day, Drawdown, Win Rate), open positions `Table`, last 5 signals `Table`
- **Right column (40%)**: Risk panel (daily drawdown progress bar, consecutive losses count), last 5 log lines `Panel`
- **Footer**: Keyboard shortcut bar (1-5 screens, p pause, r resume, s scan, i/w/e/a filters, q quit)

#### Scenario: Dashboard renders with valid JSON

- GIVEN `logs/status.json` and `logs/equity.json` contain valid data
- WHEN the dashboard screen is active
- THEN header shows ONLINE status, capital from equity.json, and uptime from status.json

#### Scenario: Dashboard with missing positions

- GIVEN `logs/positions.json` has `total_open: 0`
- WHEN dashboard renders
- THEN positions table shows "No open positions" empty state

#### Scenario: Terminal too small

- GIVEN terminal width < 80 columns or height < 24 rows
- WHEN any screen renders
- THEN display "Terminal too small — resize to 80x24 minimum" centered message

#### Scanner Screen

- **Data**: `logs/scanner_results.json`
- **Layout**: Last scan info header (timestamp, symbols filtered, signals generated) + signals Table (Time, Symbol, Action, Price, Score, Strategy) + last 5 scans history Table

#### Scenario: Scanner screen with scan data

- GIVEN `scanner_results.json` has `last_scan.total_signals > 0`
- WHEN scanner screen renders
- THEN signals table shows each signal as a row with colored action badge

#### Estrategias Screen

- **Data**: `logs/strategies.json`
- **Layout**: Predefined strategies Table (name, status ✅/❌, parameters) + user strategies Table (name, indicators, rules summary)

#### Scenario: Strategies with validation errors

- GIVEN `strategies.json` has a strategy with `validation: false`
- WHEN estrategias screen renders
- THEN that strategy's status shows ❌ with red styling

#### Trades Screen

- **Data**: `logs/trades.json`
- **Layout**: Summary metrics cards (Total Trades, Win Rate, P&L, Profit Factor) + trades Table (Entry Time, Exit Time, Symbol, Strategy, Entry Price, Exit Price, P&L, P&L%)

#### Scenario: Trades screen with empty trade list

- GIVEN `trades.json` has `total_trades: 0`
- WHEN trades screen renders
- THEN show "No trades recorded yet — the bot hasn't closed any positions" message

#### Logs Screen

- **Data**: `LogBuffer` in-memory circular buffer (200 lines), color-coded
- **Layout**: Filter bar (active level/module/text filters) + color-coded log panel
- **Colors**: INFO green, WARNING yellow, ERROR red, DEBUG blue
- **Filters**: `i` = INFO only, `w` = WARN only, `e` = ERROR only, `a` = All

### Requirement: Live Loop & Key Bindings

The console MUST run a Rich `Live` render loop at 4 FPS (0.25s refresh). Key capture MUST use non-blocking stdin polling with 0.25s timeout.

#### Scenario: Screen switching

- GIVEN console is running on screen 1 (Dashboard)
- WHEN user presses `3`
- THEN render switches to Estrategias screen within 0.5s

#### Scenario: Pause bot via key

- GIVEN console is running
- WHEN user presses `p`
- THEN system writes `logs/pause_signal.json` with `{"action": "pause", "timestamp": "..."}`
- AND status badge updates to show paused state on next refresh

#### Scenario: Quit cleanly

- GIVEN console is running
- WHEN user presses `q`
- THEN Live context manager exits cleanly
- AND orchestrator thread is joined
- AND process exits with code 0

### Requirement: StateLoader

A `StateLoader` class MUST read all JSON files, handle missing/corrupt files gracefully, and return typed dicts.

#### Scenario: Missing scanner_results.json

- GIVEN `logs/scanner_results.json` does not exist
- WHEN StateLoader loads all state
- THEN scanner field returns `{"last_scan": {}, "scan_history": [], "updated_at": null}`
- AND no exception is raised

## Acceptance Criteria

1. [CRITICAL] All 5 screens render error-free from live JSON data at 4 FPS
2. [CRITICAL] Keyboard navigation (1-5) switches screens with no lag > 0.5s
3. [CRITICAL] Missing/corrupt JSON files never crash the console — always show empty state
4. [MAJOR] Key bindings p/r/s/q execute their signal file I/O correctly
5. [MAJOR] Quit (q) performs clean shutdown — Live exit, thread join, no orphan processes
6. [MINOR] Terminal below 80x24 shows resize message
