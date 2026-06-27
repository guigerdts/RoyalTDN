"""Hot-reload watcher for CellMesh strategy YAML files.

Polls the strategies directory every 60 seconds for file modification
times. When a change is detected, reloads ALL cells from all YAML
files and atomically swaps them into the EventEngine without restarting
the bot.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger


class HotReloader:
    """Asyncio-based YAML file watcher with atomic cell swap.

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
        against the last known value.  On change, rebuilds ALL cells
        from all YAML files and atomically swaps them into the engine.
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
        """Check each YAML file for mtime changes.  Full reload on any change."""
        from cells.loader import load_cells

        any_change = False
        for yaml_path in sorted(self._strategies_dir.glob("*.yaml")):
            try:
                current_mtime = yaml_path.stat().st_mtime
            except FileNotFoundError:
                continue

            prev_mtime = self._last_mtimes.get(yaml_path.name)

            if prev_mtime is not None and current_mtime > prev_mtime:
                logger.info("HotReload: detectado cambio en {}", yaml_path.name)
                any_change = True

            self._last_mtimes[yaml_path.name] = current_mtime

        if not any_change:
            return

        # Full reload: load ALL cells from all YAML files
        try:
            new_cells = load_cells(str(self._strategies_dir), self._inference_engine)
        except Exception as exc:
            logger.exception("HotReload: error recargando celulas: {}", exc)
            return

        if not new_cells:
            logger.warning("HotReload: no se cargaron celulas — manteniendo las actuales")
            return

        # Atomic swap — asyncio is single-threaded, so this
        # assignment is safe (the engine's _process_event will
        # see either the old list or the new list).
        old_count = len(self._engine.cells)
        self._engine.cells = new_cells

        logger.info(
            "HotReload: recarga completa — {} celula(s) reemplazada(s), "
            "{} celula(s) activa(s)",
            old_count,
            len(new_cells),
        )
