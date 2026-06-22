"""Cell loader — scans a YAML directory and instantiates Cell objects.

Looks for ``.yaml`` files under ``strategies_dir``, parses each one,
and creates a Cell wired to the shared InferenceEngine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from cells.base import Cell


def load_cells(
    strategies_dir: str,
    inference_engine: Any,
) -> list[Cell]:
    """Load all cell definitions from YAML files in the given directory.

    Args:
        strategies_dir: Path to the directory containing strategy ``.yaml``
            files.
        inference_engine: Shared InferenceEngine instance passed to every
            cell for rule evaluation.

    Returns:
        List of Cell instances, one per YAML file.
    """
    cells: list[Cell] = []
    dir_path = Path(strategies_dir)

    if not dir_path.is_dir():
        logger.warning("Directorio de estrategias no encontrado: {}", strategies_dir)
        return cells

    for yaml_path in sorted(dir_path.glob("*.yaml")):
        try:
            with open(yaml_path) as f:
                config: dict[str, Any] = yaml.safe_load(f)
        except Exception:
            logger.exception("Error leyendo {} — se salta", yaml_path)
            continue

        if not isinstance(config, dict):
            logger.warning("{} no contiene un dict valido — se salta", yaml_path)
            continue

        cell = Cell(config, inference_engine=inference_engine)
        cells.append(cell)
        logger.info("Celula cargada: {} ({}) desde {}", cell.name, cell.symbol, yaml_path.name)

    return cells
