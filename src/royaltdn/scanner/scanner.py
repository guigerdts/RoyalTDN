"""
RoyalTDN — Scanner: escáner multi-estrategia y multi-símbolo

Fase 5.7 — Scanner e Integración

Combina AssetUniverse + LiquidityFilter + estrategias para generar
señales rankeadas across múltiples símbolos.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd

# ── Atomic write helper (same pattern as orchestrator) ────────────────

LOGS_DIR = Path("logs")

def _atomic_write(path: Path, data: dict) -> bool:
    """Write dict as JSON atomically via .tmp + os.replace."""
    try:
        tmp_path = path.with_suffix(".tmp")
        content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(path))
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Error writing %s: %s", path, e)
        return False

from royaltdn.strategy.base import BaseStrategy
from royaltdn.scanner.universe import AssetUniverse
from royaltdn.scanner.filters import LiquidityFilter

logger = logging.getLogger("royaltdn.scanner.scanner")


class Scanner:
    """Escáner multi-estrategia y multi-símbolo.

    Flujo:
    1. Obtiene todos los símbolos del universo
    2. Filtra por liquidez
    3. Para cada símbolo que pasa: descarga ~60 barras diarias
    4. Ejecuta cada estrategia sobre los datos
    5. Rankea señales (FactorRotation primero por score, luego BUY antes SELL)
    """

    def __init__(
        self,
        universe: AssetUniverse,
        liquidity_filter: LiquidityFilter,
        strategies: Dict[str, BaseStrategy],
        data_client: Any,
    ):
        self.universe = universe
        self.liquidity_filter = liquidity_filter
        self.strategies = strategies
        self.data_client = data_client
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._last_scan_results: List[dict] = []
        self._scan_history: List[dict] = []  # Fase 6 — last 10 scans

    def scan(self) -> List[dict]:
        """Ejecuta escaneo completo y retorna señales rankeadas.

        Returns:
            Lista de dicts con: symbol, strategy, action, price, score, metadata
            Ordenados: FactorRotation (score desc) → BUY antes SELL → resto
        """
        self._data_cache.clear()

        # 1. Obtener todos los símbolos
        all_symbols = self.universe.get_all_symbols()
        total_symbols = len(all_symbols)

        # 2. Filtrar por liquidez
        passed_symbols = self.liquidity_filter.filter(all_symbols, self.data_client)
        passed_count = len(passed_symbols)

        # 3. Para cada símbolo que pasa, descargar datos y ejecutar estrategias
        signals = []

        for symbol in passed_symbols:
            try:
                # Descargar datos (cachear por símbolo)
                data = self._get_symbol_data(symbol)
                if data is None or len(data) < 60:
                    continue

                # Ejecutar cada estrategia
                for strategy_name, strategy in self.strategies.items():
                    try:
                        signal = strategy.generate_signal(data)
                        if signal is not None:
                            metadata = signal.get("metadata", {})
                            score = metadata.get("score")

                            signal_dict = {
                                "symbol": symbol,
                                "strategy": strategy_name,
                                "action": signal.get("action"),
                                "price": signal.get("price"),
                                "score": score,
                                "metadata": metadata,
                            }
                            signals.append(signal_dict)

                    except Exception as e:
                        logger.debug("Scanner: estrategia %s falló para %s: %s", strategy_name, symbol, e)
                        continue

            except Exception as e:
                logger.debug("Scanner: error procesando %s: %s", symbol, e)
                continue

        # 4. Rankear señales
        ranked = self._rank_signals(signals)
        self._last_scan_results = ranked

        # Track scan history (Fase 6)
        scan_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_symbols": total_symbols,
            "passed_symbols": passed_count,
            "signals_count": len(ranked),
            "top_signals": [
                {
                    "symbol": s.get("symbol"),
                    "strategy": s.get("strategy"),
                    "action": s.get("action"),
                    "price": s.get("price"),
                    "score": s.get("score"),
                }
                for s in ranked[:5]
            ],
        }
        self._scan_history.append(scan_entry)
        if len(self._scan_history) > 10:
            self._scan_history = self._scan_history[-10:]

        # Publish scanner results to logs/
        try:
            self._publish_scanner_results()
        except Exception:
            pass

        logger.info(
            "Scanner: %d símbolos → %d pasaron filtro → %d señales generadas",
            total_symbols, passed_count, len(ranked)
        )
        return ranked

    def _get_symbol_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Descarga ~60 barras diarias para un símbolo (con cache)."""
        if symbol in self._data_cache:
            return self._data_cache[symbol]

        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                limit=60,
            )
            bars = self.data_client.get_stock_bars(request)

            # bars.data es dict[str, list[Bar]]
            symbol_bars = bars.data.get(symbol, [])
            if not symbol_bars:
                return None

            # Convertir a DataFrame
            df = pd.DataFrame([{
                "timestamp": b.timestamp,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": int(b.volume),
            } for b in symbol_bars])

            df = df.sort_values("timestamp").reset_index(drop=True)
            self._data_cache[symbol] = df
            return df

        except Exception as e:
            logger.debug("Scanner: error descargando datos para %s: %s", symbol, e)
            return None

    def _rank_signals(self, signals: List[dict]) -> List[dict]:
        """Rankear señales: FactorRotation (score desc) → BUY antes SELL → resto."""
        if not signals:
            return []

        def sort_key(s: dict) -> tuple:
            strategy = s.get("strategy", "")
            action = s.get("action", "")
            score = s.get("score")

            # FactorRotation con score: primero, por score descendente
            if strategy == "factor_rotation" and score is not None:
                return (0, -score, 0 if action == "BUY" else 1)

            # Otras estrategias: BUY antes que SELL
            if action == "BUY":
                return (1, 0, 0)
            elif action == "SELL":
                return (1, 1, 0)

            # RANK u otras acciones
            return (2, 0, 0)

        return sorted(signals, key=sort_key)

    def get_top_signals(self, n: int = 5) -> List[dict]:
        """Retorna las top N señales del último scan.

        Args:
            n: Número de señales a retornar.

        Returns:
            Lista de las mejores N señales.
        """
        return self._last_scan_results[:n]

    # ── Status publishing (Fase 6) ───────────────────────────────────

    def _publish_scanner_results(self) -> None:
        """Write scanner results to logs/scanner_results.json atomically."""
        last_scan = self._last_scan_results
        # Flatten top signals for the JSON output
        top_list = []
        for s in last_scan[:10]:
            top_list.append({
                "symbol": s.get("symbol"),
                "strategy": s.get("strategy"),
                "action": s.get("action"),
                "price": s.get("price"),
                "score": s.get("score"),
            })

        data = {
            "last_scan": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_signals": len(last_scan),
                "top_signals": top_list,
            },
            "scan_history": self._scan_history[-10:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write(LOGS_DIR / "scanner_results.json", data)
