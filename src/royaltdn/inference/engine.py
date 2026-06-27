"""Inference engine for the CellMesh architecture.

Evaluates YAML-defined entry/exit rules against market data
by building a condition graph tree and evaluating it recursively.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from royaltdn.inference.graph import build_graph


class InferenceEngine:
    """Reactive inference engine.

    Takes an entry/exit rule config (from YAML), builds a condition
    graph, and evaluates it against live or historical market data.
    Stateless — safe to reuse across multiple evaluations.
    """

    def __init__(self) -> None:
        pass

    def evaluate(self, entry_config: dict[str, Any], data: dict[str, Any]) -> bool:
        """Evaluate an entry/exit rule set against market data.

        Args:
            entry_config: Rule config dict (the ``entry`` or ``exit``
                section from a cell YAML).
            data: Market data dict containing price series, volume
                series, etc. Expected keys include ``close``, ``volume``,
                and optionally ``high``/``low``.

        Returns:
            True if all conditions in the rule tree are satisfied,
            False otherwise.

        Raises:
            ValueError: If the config structure is invalid.
        """
        root = build_graph(entry_config)
        result = root.evaluate(data)
        return result
