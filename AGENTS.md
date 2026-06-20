# Code Review Rules

## Python
- Use type hints for all function signatures
- Follow existing docstring style (Google/NumPy)
- Use `from X import Y` at function level for lazy imports
- 4-space indentation
- Prefer f-strings over .format() or % formatting

## Project Conventions
- Rich Console with `color_system="standard"` (16-color ANSI only)
- No 24-bit hex colors, no emoji in UI strings
- Spanish text for user-facing strings in menu app
- English for code identifiers, comments, documentation

## Architecture
- Monolithic app.py with `_show_*` / `_build_*` function naming
- StateLoader for file-based state reads
- Function-level imports to avoid module-load failures
- try/except KeyboardInterrupt for menu loops
- `_wait_enter()` pattern for pausing between screens

## Testing
- pytest for unit tests
- Keep tests independent — no shared state between test cases
- Mock external APIs (Alpaca, Redis) in tests
