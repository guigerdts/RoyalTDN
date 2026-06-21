# Build Lifecycle Specification

## Purpose

Control Python bytecode cache behavior to ensure code changes are reflected immediately without manual cache clearing during development and testing.

## Requirements

### REQ-PYC-DISABLE — Disable bytecode cache writing

The system MUST disable Python bytecode cache writing by setting `sys.dont_write_bytecode = True` at module load time. This SHALL happen as the first executable statements in `src/royaltdn/__init__.py`, before any other imports or application code.

#### Scenario: Bytecode writing disabled on import

- GIVEN the `royaltdn` package is imported
- WHEN `import royaltdn` or `python -m royaltdn` is executed
- THEN `sys.dont_write_bytecode` MUST be `True`
- AND no `.pyc` files SHALL be created under `__pycache__/` directories

#### Scenario: Code changes reflected without stale cache

- GIVEN a source file in `src/royaltdn/` has been modified
- WHEN the module is re-imported or the package is re-run
- THEN the modified code executes without interference from stale bytecode cache

#### Scenario: No functional impact on production

- GIVEN the application runs in any environment (development, test, production)
- WHEN bytecode writing is disabled
- THEN the application SHALL function identically to when bytecode writing is enabled
- AND no behavioral differences SHALL arise from the absence of `.pyc` files
