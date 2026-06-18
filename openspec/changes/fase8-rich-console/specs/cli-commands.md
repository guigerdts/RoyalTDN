# CLI Subcommands Specification

## Purpose

Replace the 3-command CLI (`check`, `run`, `run-legacy`) with a 6-command interface. Each command MUST be accessible via `python -m royaltdn <command>`. Running with no subcommand or `--help` SHALL print usage.

## Requirements

### Requirement: `royaltdn run`

Starts Orchestrator in a daemon thread, starts interactive Rich console in main thread. On `q` key or Ctrl+C: stop orchestrator, clean exit.

#### Scenario: Run launches both orchestrator and console

- GIVEN valid `.env` credentials
- WHEN `python -m royaltdn run` executes
- THEN orchestrator async loop starts in a daemon thread
- AND Rich `Live` console starts in main thread
- AND logs/status.json is being published

#### Scenario: Run terminates on q

- GIVEN `run` console is active
- WHEN user presses `q`
- THEN console Live stops
- AND orchestrator thread is joined
- AND process exits with code 0

### Requirement: `royaltdn status`

One-shot dashboard render. Loads all state from `logs/*.json`, renders dashboard once with Rich Layout, prints to stdout, exits.

#### Scenario: Status with all files present

- GIVEN all `logs/*.json` files exist with valid data
- WHEN `python -m royaltdn status` executes
- THEN a one-shot Rich dashboard is rendered to stdout
- AND exit code is 0

#### Scenario: Status with missing files

- GIVEN `logs/status.json` is missing
- WHEN status command runs
- THEN prints "Bot OFFLINE — no status published" to stderr
- AND exit code is 1

### Requirement: `royaltdn logs`

Reads `logs/bot.log`, displays last 50 lines with Rich syntax highlighting by log level, exits. Colors: INFO cyan, WARNING yellow, ERROR red, DEBUG blue.

#### Scenario: Logs with file present

- GIVEN `logs/bot.log` exists and has content
- WHEN `python -m royaltdn logs` executes
- THEN last 50 lines are printed with Rich markup
- AND exit code is 0

#### Scenario: Logs with missing file

- GIVEN `logs/bot.log` does not exist
- WHEN logs command runs
- THEN prints "No log file found at logs/bot.log"
- AND exit code is 1

### Requirement: `royaltdn pause`

Writes `logs/pause_signal.json`: `{"action": "pause", "timestamp": "<ISO-8601>"}`. Prints confirmation.

#### Scenario: Pause writes signal file

- GIVEN no pause_signal.json exists
- WHEN `python -m royaltdn pause` executes
- THEN `logs/pause_signal.json` is created with valid JSON
- AND stdout shows "⏸️ Pause signal sent"
- AND exit code is 0

### Requirement: `royaltdn resume`

Writes `logs/pause_signal.json`: `{"action": "resume", "timestamp": "<ISO-8601>"}`. Prints confirmation.

#### Scenario: Resume writes signal file

- GIVEN any state
- WHEN `python -m royaltdn resume` executes
- THEN `logs/pause_signal.json` is overwritten with `action: "resume"`
- AND stdout shows "▶️ Resume signal sent"
- AND exit code is 0

### Requirement: `royaltdn scanner`

Writes `logs/scanner_trigger.json`: `{"action": "scan_now", "timestamp": "<ISO-8601>"}`. Prints confirmation.

#### Scenario: Scanner trigger writes signal file

- GIVEN any state
- WHEN `python -m royaltdn scanner` executes
- THEN `logs/scanner_trigger.json` is created
- AND stdout shows "🔍 Scanner trigger sent"
- AND exit code is 0

### Requirement: IPC Signal File Handling in Orchestrator

The Orchestrator MUST check for signal files at top of each loop iteration and process them.

#### Requirement: Pause/Resume from signal file

(Previously: Orchestrator ran continuously with no pause/resume mechanism)

The Orchestrator SHALL check `logs/pause_signal.json` at the start of each main loop iteration:
- If file exists and `action == "pause"`: set `self.paused = True`
- If file exists and `action == "resume"`: set `self.paused = False`
- Delete file after processing
- If `self.paused` is True: skip signal execution loop body (skip signal processing, still publish status JSON)

#### Scenario: Pause during legacy loop

- GIVEN Orchestrator is running in legacy mode
- WHEN pause_signal.json with `action: "pause"` appears in logs/
- THEN on next loop iteration, `self.paused` becomes True
- AND signal execution is skipped
- BUT status.json is still published
- AND pause_signal.json is deleted

#### Scenario: Resume from paused state

- GIVEN Orchestrator is paused (`self.paused = True`)
- WHEN pause_signal.json with `action: "resume"` appears
- THEN `self.paused` becomes False
- AND normal signal execution resumes
- AND pause_signal.json is deleted

#### Requirement: Scanner trigger from signal file

The Orchestrator SHALL check `logs/scanner_trigger.json` at start of each loop iteration:
- If file exists and `action == "scan_now"`: execute `self._scanner.scan()` immediately
- Delete file after processing

#### Scenario: Scanner triggered mid-cycle

- GIVEN Orchestrator is in a long-running legacy loop
- WHEN scanner_trigger.json is created
- THEN scanner.scan() executes out-of-cycle
- AND scanner_trigger.json is deleted
- AND scanner_results.json is updated

## Acceptance Criteria

1. [CRITICAL] All 6 subcommands exit cleanly (code 0 or documented error code)
2. [CRITICAL] `pause`/`resume`/`scanner` signal files are read and processed by Orchestrator within 1 cycle
3. [CRITICAL] Signal files are deleted after processing (no stale signals)
4. [MAJOR] `run` launches both orchestrator thread and console without deadlock
5. [MAJOR] `status` and `logs` are one-shot commands — exit immediately after output
6. [MINOR] `python -m royaltdn` with no args prints help listing all 6 subcommands
