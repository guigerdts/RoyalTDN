"""Cell loader — scans a YAML directory and instantiates Cell objects.

Looks for ``.yaml`` files under ``strategies_dir``, parses each one,
and creates a Cell wired to the shared InferenceEngine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from royaltdn.cells.base import Cell


def _get_available_symbols() -> list[str]:
    """Read available trading symbols from project config.yaml."""
    from pathlib import Path

    import yaml

    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("symbols", [])


def _expand_strategy_config(config: dict) -> list[dict]:
    """Expand a strategy config dict into one dict per symbol.

    Returns a list of config dicts (modified copies), one per symbol.
    Returns an empty list if the config should be skipped (no symbols).
    """
    name = config.get("name", "unnamed")

    # Case 1 — explicit symbols list
    symbols = config.get("symbols")
    if symbols is not None:
        if not isinstance(symbols, list) or len(symbols) == 0:
            logger.warning("Lista de symbols vacia o invalida para {} — se salta", name)
            return []
        result = []
        for sym in symbols:
            cell_config = dict(config)
            cell_config["symbol"] = sym
            cell_config["name"] = f"{name}_{sym}"
            result.append(cell_config)
        return result

    # Case 2 — single symbol (backward compatible)
    if "symbol" in config:
        return [dict(config)]

    # Case 3 — auto-assign based on category
    available = _get_available_symbols()
    if not available:
        logger.warning("No hay symbols disponibles en config.yaml para auto-asignar a {}", name)
        return []

    if name.startswith("scalping_"):
        selected = list(available)
    elif name.startswith("intraday_"):
        selected = available[:3]
    elif name.startswith("swing_"):
        selected = available[:1]
    else:
        logger.warning(
            "No se pudo auto-asignar symbol para {} (sin categoria conocida) — se salta",
            name,
        )
        return []

    if not selected:
        logger.warning("No hay symbols disponibles para auto-asignar a {}", name)
        return []

    result = []
    for sym in selected:
        cell_config = dict(config)
        cell_config["symbol"] = sym
        cell_config["name"] = f"{name}_{sym}"
        result.append(cell_config)
    return result


def load_cells(
    strategies_dir: str,
    inference_engine: Any,
) -> list[Cell]:
    """Load all cell definitions from YAML files in the given directory.

    Multi-symbol strategies (with a ``symbols`` list) are expanded into
    one Cell per symbol.  Backward-compatible with single-symbol configs.
    """
    cells: list[Cell] = []
    dir_path = Path(strategies_dir)

    if not dir_path.is_dir():
        logger.warning("Directorio de estrategias no encontrado: {}", strategies_dir)
        return cells

    for yaml_path in sorted(dir_path.glob("*.yaml")):
        try:
            with open(yaml_path) as f:
                documents = list(yaml.safe_load_all(f))
        except Exception:
            logger.exception("Error leyendo {} — se salta", yaml_path)
            continue

        loaded = 0
        for doc in documents:
            if doc is None:
                continue  # skip empty documents
            if isinstance(doc, dict):
                for expanded in _expand_strategy_config(doc):
                    cell = Cell(expanded, inference_engine=inference_engine)
                    cells.append(cell)
                    logger.info("Celula cargada: {} ({}) desde {}", cell.name, cell.symbol, yaml_path.name)
                    loaded += 1
            elif isinstance(doc, list):
                for item in doc:
                    if isinstance(item, dict):
                        for expanded in _expand_strategy_config(item):
                            cell = Cell(expanded, inference_engine=inference_engine)
                            cells.append(cell)
                            logger.info("Celula cargada: {} ({}) desde {}", cell.name, cell.symbol, yaml_path.name)
                            loaded += 1
                    else:
                        logger.warning("Elemento no-dict ignorado en {}: {}", yaml_path.name, type(item).__name__)
            else:
                logger.warning("Documento de tipo {} ignorado en {}", type(doc).__name__, yaml_path.name)

        if loaded == 0:
            logger.warning("{} — no se cargaron celulas", yaml_path.name)

    return cells
