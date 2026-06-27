"""NOTICE: bus persistence subscriber tests removed.

This file previously contained tests for ``run_persistence_subscriber``,
a function in ``royaltdn.core.bus`` that was specified in M5 tasks but
never implemented.

The M5 verify phase documented this as accepted dead code — the engine
handles persistence directly, not through a bus subscriber. Deleting
these tests eliminates noise from the test suite.

Removed on 2026-06-27 during M1-M4-M5-Telegram branch restructuring.
See architecture/merged-m1-m4-m5-telegram-chain-to-main in engram.
"""
