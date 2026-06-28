"""Backtesting package for the CellMesh architecture.

Exports the orchestrator (:func:`run`), the enhanced
:func:`run_with_benchmark`, its result type (:class:`BacktestResult`),
and all metrics functions.
"""

from __future__ import annotations

from royaltdn.backtesting.backtester import BacktestResult, run, run_with_benchmark

__all__ = [
    "BacktestResult",
    "run",
    "run_with_benchmark",
]
