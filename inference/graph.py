"""Reactive condition graph for the inference engine.

Builds a tree of ConditionNode and LogicNode from YAML-derived
dicts so that entry/exit rules can be evaluated recursively.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from inference.conditions import evaluate as eval_condition


class ConditionNode:
    """Leaf node that evaluates a single indicator condition."""

    def __init__(self, condition: dict[str, Any]) -> None:
        """Initialise from a condition config dict.

        Args:
            condition: Dict with keys ``indicator``, ``params``, ``operator``.
        """
        self.indicator: str = condition["indicator"]
        self.params: dict[str, Any] = condition.get("params", {})
        self.operator: str = condition.get("operator", "> 0")

    def evaluate(self, data: Any) -> bool:
        """Evaluate this single condition against market data.

        Args:
            data: Price/volume series or dict to evaluate against.

        Returns:
            True if the condition holds, False otherwise.
        """
        return eval_condition(self.indicator, self.params, self.operator, data)


class LogicNode:
    """Composite node that combines child nodes with AND/OR/NOT logic."""

    def __init__(self, logic: str, children: list) -> None:
        """Initialise with logical operator and child nodes.

        Args:
            logic: One of ``AND``, ``OR``, or ``NOT``.
            children: List of ConditionNode or LogicNode instances.

        Raises:
            ValueError: If logic is invalid or NOT has != 1 child.
        """
        logic_upper = logic.upper()
        if logic_upper not in {"AND", "OR", "NOT"}:
            raise ValueError(f"Unsupported logic operator: {logic}")
        if logic_upper == "NOT" and len(children) != 1:
            raise ValueError("NOT logic requires exactly one child node")

        self.logic: str = logic_upper
        self.children: list = children

    def evaluate(self, data: Any) -> bool:
        """Evaluate the composite logic tree against market data.

        Args:
            data: Price/volume series or dict to evaluate against.

        Returns:
            True if the combined logic holds, False otherwise.
        """
        if self.logic == "AND":
            return all(child.evaluate(data) for child in self.children)
        if self.logic == "OR":
            return any(child.evaluate(data) for child in self.children)
        # NOT
        return not self.children[0].evaluate(data)


def _build_node(config: dict[str, Any]) -> ConditionNode | LogicNode:
    """Recursively build a node from a config dict.

    If the dict has a ``logic`` key it becomes a LogicNode;
    otherwise it is treated as a ConditionNode.

    Args:
        config: Condition or logic config dict from YAML.

    Returns:
        A ConditionNode or LogicNode ready for evaluation.

    Raises:
        ValueError: If the config structure is invalid.
    """
    if "logic" in config:
        logic: str = config["logic"]
        raw_children: list[dict[str, Any]] = config.get("conditions", [])
        if not raw_children:
            raise ValueError(f"Logic node '{logic}' has no conditions")
        children: list[ConditionNode | LogicNode] = [
            _build_node(child) for child in raw_children
        ]
        return LogicNode(logic, children)
    if "indicator" in config:
        return ConditionNode(config)

    raise ValueError("Node config must contain 'logic' or 'indicator'")


def build_graph(entry_config: dict[str, Any]) -> LogicNode:
    """Build a logic tree from a YAML-derived entry/exit config.

    Args:
        entry_config: Dict representing the entry (or exit) rules.
            Expected structure::

                {
                    "logic": "AND",
                    "conditions": [
                        {"indicator": "rsi", "params": {"period": 7},
                         "operator": "< 30"},
                        {"logic": "OR",
                         "conditions": [
                             {"indicator": "momentum", "params": {},
                              "operator": "> 0.02"},
                         ]},
                    ]
                }

    Returns:
        The root LogicNode of the condition tree.

    Raises:
        ValueError: If the root node is not a LogicNode.
    """
    root = _build_node(entry_config)
    if not isinstance(root, LogicNode):
        raise ValueError("Root of entry config must be a logic node")
    logger.trace("Condition graph built with root logic={}", root.logic)
    return root
