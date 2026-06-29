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


def _is_strategy_enabled(
    config: dict[str, Any],
    enabled_list: list[str] | None = None,
    disabled_list: list[str] | None = None,
) -> bool:
    """Check if a strategy config is enabled.

    Operates on the **base strategy document** (before symbol expansion),
    so the name compared is the raw strategy name (e.g. ``scalping_momentum``),
    not an expanded cell name (e.g. ``scalping_momentum_BTCUSDT``).

    Priority (first match wins):
    1. If config has ``enabled: false`` explicitly → disabled
    2. If ``enabled_list`` is non-empty and strategy name is NOT in it → disabled
    3. If ``disabled_list`` is non-empty and strategy name IS in it → disabled
    4. Otherwise → enabled
    """
    name = config.get("name", "")

    # Rule 1 — explicit enabled flag in the YAML config
    enabled_flag = config.get("enabled", True)
    if not enabled_flag:
        return False

    # Rule 2 — enabled_list is a whitelist
    if enabled_list and name not in enabled_list:
        return False

    # Rule 3 — disabled_list is a blacklist
    if disabled_list and name in disabled_list:
        return False

    return True


def _load_cells_from_docs(
    documents: list[Any],
    inference_engine: Any,
    source_name: str,
    enabled_strategies: list[str] | None = None,
    disabled_strategies: list[str] | None = None,
) -> list[Cell]:
    """Parse a list of YAML documents into Cell objects.

    Each cell is tagged with ``_source_file`` so the :class:`HotReloader
    <royaltdn.core.hot_reload.HotReloader>` can swap cells
    granularly per file (M6).

    Filtering happens at the **document level** (before symbol expansion)
    so that ``enabled_strategies`` / ``disabled_strategies`` use the
    base strategy name.

    Args:
        documents: Parsed YAML documents from ``yaml.safe_load_all``.
        inference_engine: Shared InferenceEngine for new cells.
        source_name: Human-readable source name (file name) for logging.
        enabled_strategies: If non-empty, ONLY load strategies in this list.
        disabled_strategies: If non-empty, EXCLUDE strategies in this list.

    Returns:
        List of Cell instances.
    """
    cells: list[Cell] = []
    loaded = 0

    for doc in documents:
        if doc is None:
            continue
        if isinstance(doc, dict):
            # Filter at the document level (base strategy name)
            if not _is_strategy_enabled(doc, enabled_strategies, disabled_strategies):
                logger.debug("Estrategia deshabilitada: {} ({})", doc.get("name"), source_name)
                continue
            for expanded in _expand_strategy_config(doc):
                expanded["_source_file"] = source_name
                cell = Cell(expanded, inference_engine=inference_engine)
                cells.append(cell)
                logger.info("Celula cargada: {} ({}) desde {}", cell.name, cell.symbol, source_name)
                loaded += 1
        elif isinstance(doc, list):
            for item in doc:
                if isinstance(item, dict):
                    # Filter at the document level (base strategy name)
                    if not _is_strategy_enabled(item, enabled_strategies, disabled_strategies):
                        logger.debug("Estrategia deshabilitada: {} ({})", item.get("name"), source_name)
                        continue
                    for expanded in _expand_strategy_config(item):
                        expanded["_source_file"] = source_name
                        cell = Cell(expanded, inference_engine=inference_engine)
                        cells.append(cell)
                        logger.info("Celula cargada: {} ({}) desde {}", cell.name, cell.symbol, source_name)
                        loaded += 1
                else:
                    logger.warning("Elemento no-dict ignorado en {}: {}", source_name, type(item).__name__)
        else:
            logger.warning("Documento de tipo {} ignorado en {}", type(doc).__name__, source_name)

    if loaded == 0:
        logger.warning("{} — no se cargaron celulas", source_name)

    return cells


def load_cells_from_file(
    yaml_path: Path,
    inference_engine: Any,
    enabled_strategies: list[str] | None = None,
    disabled_strategies: list[str] | None = None,
) -> list[Cell]:
    """Load cell definitions from a single YAML file.

    Args:
        yaml_path: Path to the ``.yaml`` strategy file.
        inference_engine: Shared InferenceEngine for new cells.
        enabled_strategies: If non-empty, ONLY load strategies in this list.
        disabled_strategies: If non-empty, EXCLUDE strategies in this list.

    Returns:
        List of Cell instances parsed from the file.
    """
    try:
        with open(yaml_path) as f:
            documents = list(yaml.safe_load_all(f))
    except Exception:
        logger.exception("Error leyendo {} — se salta", yaml_path)
        return []

    return _load_cells_from_docs(
        documents, inference_engine, yaml_path.name,
        enabled_strategies=enabled_strategies,
        disabled_strategies=disabled_strategies,
    )


def load_cells(
    strategies_dir: str,
    inference_engine: Any,
    enabled_strategies: list[str] | None = None,
    disabled_strategies: list[str] | None = None,
) -> list[Cell]:
    """Load all cell definitions from YAML files in the given directory.

    Multi-symbol strategies (with a ``symbols`` list) are expanded into
    one Cell per symbol.  Backward-compatible with single-symbol configs.

    Args:
        strategies_dir: Path to the strategies templates directory.
        inference_engine: Shared InferenceEngine for new cells.
        enabled_strategies: If non-empty, ONLY load strategies in this list.
        disabled_strategies: If non-empty, EXCLUDE strategies in this list.

    Returns:
        List of Cell instances.
    """
    cells: list[Cell] = []
    dir_path = Path(strategies_dir)

    if not dir_path.is_dir():
        logger.warning("Directorio de estrategias no encontrado: {}", strategies_dir)
        return cells

    for yaml_path in sorted(dir_path.glob("*.yaml")):
        file_cells = load_cells_from_file(
            yaml_path, inference_engine,
            enabled_strategies=enabled_strategies,
            disabled_strategies=disabled_strategies,
        )
        cells.extend(file_cells)

    return cells
