"""Backtesting package for the CellMesh architecture.

Exports the orchestrator (:func:`run`) and its result type
(:class:`BacktestResult`).
"""

from __future__ import annotations

from royaltdn.backtesting.backtester import BacktestResult, run

__all__ = ["BacktestResult", "run"]
