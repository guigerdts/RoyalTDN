# SDD Explore — FASE 18.5: 5 Bugs Post-FASE 18.4

## Verification Prerequisites

| Item | Value |
|------|-------|
| **Branch** | `main` |
| **HEAD** | `b32fc89` — merge(fase-18.4): Scanner verbose + intervalo dinámico + validación dinero real |
| **Pending changes** | None (clean working tree) |
| **Untracked files** | `openspec/` dirs, `sdd/` dirs (documentation only, not code) |
| **.env state** | See §Bug 1 below |

### FASE 18.4 Test Files (6 files, 1685 lines, 78 tests)

| File | Lines | Tests |
|------|-------|-------|
| `test_fase18_4_pr1a.py` | 325 | 15 (explain base + sma + bollinger + scanner verbose) |
| `test_fase18_4_pr1b.py` | 190 | 9 (momentum_atr + swing_trend + swing_breakout explain) |
| `test_fase18_4_pr2.py` | 268 | 15 (5 scalping explain) |
| `test_fase18_4_pr3a.py` | 259 | 20 (5 intraday explain) |
| `test_fase18_4_pr3b.py` | 169 | 4 (swing_reversion explain + all-16 iteration) |
| `test_fase18_4_pr4.py` | 474 | 20 (dynamic interval + scalping disable + UI verbose + readiness) |

---

## Bug 1 — Universe "all" por defecto ignora SCANNER_UNIVERSE=crypto

### Confirmation: ✅ CONFIRMED (configuration issue)

### Root Cause

**Primary (blocking): `.env` file has 3 duplicate `SCANNER_UNIVERSE` entries.**

File: `/root/RoyalTDN/.env`, lines 24-26:
```
SCANNER_UNIVERSE=etfs
SCANNER_UNIVERSE=crypto
SCANNER_UNIVERSE=crypto
```

`python-dotenv`'s `load_dotenv()` (default: `override=False`) applies values **first-wins**: once `SCANNER_UNIVERSE=etfs` sets the env var, the subsequent `crypto` lines are ignored because the key already exists in `os.environ`. **Effective value: `etfs`, NOT `crypto`.**

**Secondary (confusion): Menu display always shows "all".**

File: `src/royaltdn/frontend/menu/app.py`, line 11:
```python
_current_universe: str = "all"
```

This global starts as `"all"` regardless of the actual `SCANNER_UNIVERSE` env var used to construct `AssetUniverse`. The menu header (line 138) displays this value:
```python
console.print(f"[cyan]Universe: {_current_universe}[/]")
```

There is **no sync from scanner → menu on startup**. The menu always shows "all" until the user presses `U` to cycle. Even if the scanner is correctly initialized with `crypto`, the user sees "Universe: all" and assumes their env var was ignored.

**Code IS correct for reading the env var:**
- `src/royaltdn/main.py` line 507: `universe_type=os.getenv("SCANNER_UNIVERSE", "all")` — correctly reads env var with fallback
- `AssetUniverse.__init__` validates the type (line 70-76): `"crypto"` IS in `VALID_UNIVERSE_TYPES`

### Affected Files

| File | Lines | Issue |
|------|-------|-------|
| `.env` | 24-26 | 3 duplicate `SCANNER_UNIVERSE` lines, `etfs` first |
| `app.py` | 11 | `_current_universe` hardcoded to `"all"` on init |

### Proposed Fix

1. **Fix `.env`:** Remove duplicate lines, keep single `SCANNER_UNIVERSE=crypto` at line 24, delete lines 25-26.
2. **Sync menu display on startup:** In `run_menu()` or via `set_universe_setter`, read `_scanner.universe.universe_type` (if scanner is wired) and set `_current_universe` accordingly.

### Fix Complexity: ~2 lines of code + .env cleanup

---

## Bug 3 — Flag --verbose no activa dashboard compacto

### Confirmation: ✅ CONFIRMED (missing initial scan + large interval delay)

### Root Cause

The `--verbose` flag IS correctly parsed and wired:

1. `main.py` line 431: `verbose = "--verbose" in sys.argv[2:]` — correct parsing
2. `main.py` line 568: `scanner.verbose = verbose` — sets scanner attribute
3. `scanner.py` line 90: `scan()` falls back to `self.verbose` when called without args

The problem is **the scanner never runs with verbose mode before the user opens the scanner screen.**

In `orchestrator.py` `_run_legacy_loop()` (lines 1422-1431):
```python
self._current_scan_interval = self._calc_scan_interval()  # 240 min for swing
scanner_iterations = int((self._current_scan_interval * 60) / poll_interval)
# = 240 * 60 / 60 = 240

scanner_cycle = 0  # starts at 0!

if scanner_cycle >= scanner_iterations:  # 0 >= 240 → False
    # scanner NEVER runs on first iteration
```

The first auto-scan runs after **240 loop iterations** (for swing strategies), which is ~4 hours. Until then, `_scanner._last_explanations` is empty, so `_show_scanner()` evaluates `verbose_active` as False (line 1714-1718):

```python
verbose_active = (
    _scanner is not None
    and _scanner.verbose            # True
    and bool(_scanner._last_explanations)  # False → no verbose dashboard!
)
```

Additionally, even after the first scan, the scanner publishes results to `scanner_results.json` via `_publish_scanner_results()`, but `_last_explanations` is only kept in-memory on the `Scanner` object. If the orchestrator thread is separate from the menu thread, there could be a race/visibility issue, though this is secondary.

### Affected Files

| File | Lines | Issue |
|------|-------|-------|
| `orchestrator.py` | 1383, 1422-1431 | No initial scan at loop start; `scanner_cycle` starts at 0 |
| `app.py` | 1714-1718 | `verbose_active` requires non-empty `_last_explanations` |

### Proposed Fix

**Option A (simple):** Run an initial scan at the start of `_run_legacy_loop()` before the main while loop.

**Option B (better):** In `cmd_run()` in `main.py`, after creating the scanner with `scanner.verbose = True`, call `scanner.scan()` once to pre-populate `_last_explanations`. Run it in a thread to avoid delaying startup.

Either approach ensures `_last_explanations` is populated when the user first opens the scanner screen.

### Fix Complexity: ~5-10 lines

---

## Bug 4 — Scanner se ejecuta automáticamente al arrancar

### Confirmation: ❌ REJECTED — scanner does NOT run automatically at startup

### Evidence

`_run_legacy_loop()` in `orchestrator.py`:

1. **No scan call before the main loop.** The first scan is inside the `while self._running` loop, gated by `scanner_cycle >= scanner_iterations`.

2. **`_pending_scan = False` initially** (set in `__init__` line 193). Only set True via `_check_signals()` when a signal file exists.

3. **`scanner_cycle = 0`** (line 1381). The increment happens inside the loop (line 1429): `scanner_cycle += 1`. First iteration: `1 >= 240` → False (for swing).

4. **`_setup()` does NOT call scan.** Line 220-223 only logs "Scanner recibido desde main.py".

5. **`main.py` `cmd_run()` does NOT call scan.** Line 568 just sets `scanner.verbose = verbose`.

### Why the user may have perceived this

- The orchestrator's **DataIngestor** starts immediately and begins polling (not the scanner)
- Log lines like "Scanner inicializado desde main" may have been misinterpreted as "scanner running"
- If they tested with `SCANNER_INTERVAL_MINUTES=1` and a short interval, the first scan would come within 1 minute, which feels "automatic"

### No fix needed

---

## Bug 5 — Tecla 'v' no activa verbose, vuelve al menú principal

### Confirmation: ✅ CONFIRMED — no 'v' handler exists anywhere

### Root Cause

There is **zero** 'v' key handling in the entire menu system:

1. **Main menu dispatcher** (`run_menu()`, lines 59-103): Handles keys `1-8`, `u`, `0`. No 'v'. Falls through to:
   ```python
   else:
       console.print("[bold red]Opción inválida...")
       _wait_enter()
   ```

2. **`_show_scanner()` standard mode** (line 1752): Only handles force scan prompt `(s/n)`. Pressing 'v' here is treated as input to this prompt → no match → falls through to `_wait_enter()` → returns to main menu.

3. **`_render_verbose_dashboard()` L1 dashboard** (lines 1488-1512): Handles `j/k/e/s/0`. No 'v':
   ```python
   if cmd == "j": ...
   elif cmd == "k": ...
   elif cmd == "e": ...
   elif cmd == "s": ...
   elif cmd == "0": ...
   return "_rerender"  # anything else re-renders
   ```
   Pressing 'v' here just re-renders the dashboard with `"_rerender"`.

4. **There is NO toggle mechanism** for verbose mode at runtime. The only way to enable/disable verbose is via the `--verbose` CLI flag at startup.

### Affected Files

| File | Lines | Issue |
|------|-------|-------|
| `app.py` | 59-103 | No 'v' case in main menu dispatcher |
| `app.py` | 1488-1512 | No 'v' case in verbose dashboard input |
| `app.py` | 1749-1761 | Standard scanner mode has no verbose toggle |

### Proposed Fix

Add a 'v' handler that toggles `_scanner.verbose` and re-enters the verbose dashboard:

```python
# In _show_scanner() verbose dashboard loop (around line 1727):
if action == "_toggle_verbose":
    _scanner.verbose = not _scanner.verbose
    if not _scanner.verbose:
        break  # fall back to standard scanner mode
    continue
```

And in `_render_verbose_dashboard()`, add:
```python
console.print("[bold cyan]v[/] Toggle verbose")
```

In the main menu, add 'v' to the dispatch table to jump directly to the scanner screen with verbose active.

### Fix Complexity: ~10-15 lines

---

## Risk Assessment

| Bug | Risk | Reasoning |
|-----|------|-----------|
| **Bug 1** | 🟢 Safe | Just `.env` cleanup + one line to sync menu display. No logic changes. |
| **Bug 3** | 🟡 Moderate | Adding an initial scan at startup increases startup latency by 30s-5min. Must run in thread/executor. If scan fails, should NOT block startup. |
| **Bug 4** | ❌ None | Not a bug — no fix needed. |
| **Bug 5** | 🟢 Safe | Pure UI addition. Adding a key handler has zero side effects on core logic. |

### Priority Order for Fixing:
1. **Bug 1** (configuration, quickest fix, clear user confusion)
2. **Bug 5** (UI, simple addition)
3. **Bug 3** (needs care to avoid blocking startup)

---

## Estimated Fix Complexity

| Bug | Lines of code | Files affected |
|-----|---------------|----------------|
| Bug 1 | ~2 | `.env`, `app.py:11` |
| Bug 3 | ~5-10 | `orchestrator.py` or `main.py` |
| Bug 4 | 0 | None (rejected) |
| Bug 5 | ~10-15 | `app.py` |
| **Total** | **~17-27** | **3-4 files** |
