"""Hot-reload watcher for CellMesh strategy YAML files.

Polls the strategies directory every 60 seconds for file modification
times. When a change is detected, reloads only the **changed** YAML
file's cells (M6 — granular reload) and atomically swaps them into
the EventEngine without restarting the bot or touching cells from
other files.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger


class HotReloader:
    """Asyncio-based YAML file watcher with granular cell swap.

    Usage::

        reloader = HotReloader(strategies_dir, engine, inference_engine)
        asyncio.create_task(reloader.watch())
    """

    def __init__(
        self,
        strategies_dir: str,
        engine: Any,
        inference_engine: Any,
        poll_interval: int = 60,
    ) -> None:
        """Initialise the watcher.

        Args:
            strategies_dir: Path to directory containing strategy ``.yaml``
                files.
            engine: The running ``EventEngine`` instance whose ``cells``
                list will be swapped on change.
            inference_engine: Shared ``InferenceEngine`` for new cells.
            poll_interval: Seconds between mtime polls (default 60).
        """
        self._strategies_dir = Path(strategies_dir)
        self._engine = engine
        self._inference_engine = inference_engine
        self._poll_interval = poll_interval
        self._last_mtimes: dict[str, float] = {}

    async def watch(self) -> None:
        """Continuously poll YAML files for changes.

        Runs until cancelled. On each tick, compares current mtime
        against the last known value.  On change, reloads only the
        affected file and swaps its cells atomically (M6).
        """
        logger.info(
            "HotReloader iniciado — vigilando {} cada {}s",
            self._strategies_dir,
            self._poll_interval,
        )

        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                logger.info("HotReloader detenido")
                break
            except Exception:
                logger.exception("Error en HotReloader — se reanuda en {}s",
                                 self._poll_interval)

            await asyncio.sleep(self._poll_interval)

    async def _poll(self) -> None:
        """Check each YAML file for mtime changes.  Granular reload per file."""
        from royaltdn.cells.loader import load_cells_from_file

        for yaml_path in sorted(self._strategies_dir.glob("*.yaml")):
            try:
                current_mtime = yaml_path.stat().st_mtime
            except FileNotFoundError:
                continue

            prev_mtime = self._last_mtimes.get(yaml_path.name)

            if prev_mtime is not None and current_mtime > prev_mtime:
                logger.info("HotReload: detectado cambio en {}", yaml_path.name)

                # Granular reload: only cells from the changed file
                new_cells = load_cells_from_file(yaml_path, self._inference_engine)
                if not new_cells:
                    logger.warning(
                        "HotReload: no se cargaron celulas desde {} — "
                        "se mantienen las actuales de este archivo",
                        yaml_path.name,
                    )
                    self._last_mtimes[yaml_path.name] = current_mtime
                    continue

                # Replace only cells that came from this file
                old_list = self._engine.cells
                new_list = [
                    c for c in old_list
                    if c.source_file != yaml_path.name
                ]
                new_list.extend(new_cells)

                self._engine.cells = new_list
                logger.info(
                    "HotReload: {} — {} celula(s) reemplazada(s), "
                    "{} celula(s) totales",
                    yaml_path.name,
                    len(old_list) - (len(new_list) - len(new_cells)),
                    len(new_list),
                )

            self._last_mtimes[yaml_path.name] = current_mtime
