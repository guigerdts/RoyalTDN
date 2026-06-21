"""
RoyalTDN — Scanner: escáner multi-estrategia y multi-símbolo

Fase 5.7 — Scanner e Integración

Combina AssetUniverse + LiquidityFilter + estrategias para generar
señales rankeadas across múltiples símbolos.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from loguru import logger
import pandas as pd

from royaltdn.brokers.base import BaseBroker

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
        logger.warning("Error writing {}: {}", path, e)
        return False

from royaltdn.strategy.base import BaseStrategy
from royaltdn.scanner.universe import AssetUniverse, is_crypto_symbol
from royaltdn.scanner.filters import LiquidityFilter, TokenBucket


class Scanner:
    """Multi-strategy, multi-symbol scanner.

    Flow:
    1. Gets all symbols from the asset universe
    2. Filters by liquidity
    3. Downloads ~60 daily bars in batches of 100 symbols
    4. Runs each strategy on the data
    5. Ranks signals (FactorRotation by score first, then BUY before SELL)
    """

    def __init__(
        self,
        universe: AssetUniverse,
        liquidity_filter: LiquidityFilter,
        strategies: Dict[str, BaseStrategy],
        data_client: Any,
        crypto_data_client: Optional[Any] = None,
        brokers: Optional[Dict[str, BaseBroker]] = None,
    ):
        self.universe = universe
        self.liquidity_filter = liquidity_filter
        self.strategies = strategies
        self.data_client = data_client
        self.crypto_data_client = crypto_data_client
        self._brokers: Dict[str, BaseBroker] = brokers or {}
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._last_scan_results: List[dict] = []
        self._scan_history: List[dict] = []  # Fase 6 — last 10 scans
        self._auth_failed: bool = False
        self._token_bucket: TokenBucket = liquidity_filter.token_bucket

    def scan(self) -> List[dict]:
        """Runs a full scan and returns ranked signals.

        Returns:
            List of dicts with: symbol, strategy, action, price, score, metadata
            Ordered: FactorRotation (score desc) -> BUY before SELL -> rest
        """
        self._data_cache.clear()
        self._auth_failed = False

        # 1. Get all symbols
        all_symbols = self.universe.get_symbols()
        total_symbols = len(all_symbols)

        # 2. Filter by liquidity
        passed_symbols = self.liquidity_filter.filter(all_symbols, self.data_client, self.crypto_data_client)
        passed_count = len(passed_symbols)

        # 3. Download data in batches, then run strategies
        signals = []

        import sys
        import time as _time
        import math
        from tqdm import tqdm
        _start = _time.monotonic()
        if passed_symbols and not self._auth_failed:
            est_seconds = len(passed_symbols) * 0.3
            est_minutes = math.ceil(est_seconds / 60)
            tqdm.write(
                f"Escaneando {len(passed_symbols)} s\u00edmbolos... ~{est_minutes}min restante"
            )

            # Batch download data (reduces ~400 calls to ~4)
            symbol_data = self._batch_get_symbol_data(passed_symbols)

            # Process each symbol with strategies
            total = len(symbol_data)
            pbar = tqdm(
                list(symbol_data.keys()),
                desc="Analizando...",
                unit="sym",
                file=sys.stdout,
                bar_format="{desc}  {percentage:.0f}% completado.  ~{remaining}",
            )
            for idx, symbol in enumerate(pbar, start=1):
                if self._auth_failed:
                    logger.warning("Scanner: auth failure detected — aborting scan loop")
                    break
                pbar.set_description(f"Analizando {symbol} ({idx}/{total})")
                data = symbol_data.get(symbol)
                if data is None or len(data) < 60:
                    continue

                # Run each strategy on this symbol's data
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
                                "source": "scanner",
                                "metadata": metadata,
                            }
                            signals.append(signal_dict)

                    except Exception as e:
                        logger.debug("Scanner: strategy {} failed for {}: {}", strategy_name, symbol, e)
                        continue

        self._last_scan_elapsed = _time.monotonic() - _start

        # 4. Rank signals
        ranked = self._rank_signals(signals)
        self._last_scan_results = ranked

        # Track scan history
        scan_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_symbols": total_symbols,
            "passed_symbols": passed_count,
            "signals_count": len(ranked),
            "elapsed_seconds": round(self._last_scan_elapsed, 1),
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
            "Scanner: {} symbols -> {} passed filter -> {} signals generated",
            total_symbols, passed_count, len(ranked)
        )
        return ranked

    def _get_broker_for_symbol(self, symbol: str) -> Optional[BaseBroker]:
        """Route a symbol to its corresponding broker.

        Crypto symbols (containing ``"/"``) → crypto broker.
        Stock/ETF symbols → stock broker.

        Returns:
            BaseBroker instance, or ``None`` if no matching broker is configured.
        """
        if is_crypto_symbol(symbol) and "crypto" in self._brokers:
            return self._brokers["crypto"]
        return self._brokers.get("stocks")

    def _batch_get_symbol_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Downloads historical data for multiple symbols in batches of up to 100.

        Uses get_stock_bars / get_crypto_bars with batches of 100 symbols.
        Crypto symbols (containing '/') are processed separately via
        CryptoHistoricalDataClient or broker.get_bars() when available.
        Each batch consumes 1 token from the TokenBucket.

        Args:
            symbols: List of symbols to download data for.

        Returns:
            Dict mapping symbol -> DataFrame with 60 daily bars.
        """
        if not symbols:
            return {}

        result: Dict[str, pd.DataFrame] = {}

        # Check cache first — remove cached symbols from fetch list
        to_fetch = [s for s in symbols if s not in self._data_cache]
        # Return cached data for already-fetched symbols
        for s in symbols:
            if s in self._data_cache:
                result[s] = self._data_cache[s]

        if not to_fetch:
            return result

        batch_size = 100
        import math

        from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame

        # Split symbols into crypto and stock groups
        crypto_symbols = [s for s in to_fetch if is_crypto_symbol(s)]
        stock_symbols = [s for s in to_fetch if not is_crypto_symbol(s)]

        # Helper: process a group of symbols in batches using the given
        # request class and data_client method
        from datetime import datetime, timedelta
        _batch_end = datetime.now()
        _batch_start = _batch_end - timedelta(days=90)  # ~60 trading days

        def _process_group(
            group_symbols,
            request_cls,
            client_method,
            group_name,
        ):
            if not group_symbols:
                return
            n_batches = math.ceil(len(group_symbols) / batch_size)
            for i in range(n_batches):
                if self._auth_failed:
                    logger.warning("Scanner: auth failure — stopping {} batch download", group_name)
                    break

                batch = group_symbols[i * batch_size:(i + 1) * batch_size]
                try:
                    self._token_bucket.consume(1)

                    request = request_cls(
                        symbol_or_symbols=batch,
                        timeframe=TimeFrame.Day,
                        start=_batch_start,
                        end=_batch_end,
                    )
                    bars_response = client_method(request)

                    for symbol in batch:
                        symbol_bars = bars_response.data.get(symbol, [])
                        if not symbol_bars:
                            continue

                        df = pd.DataFrame([{
                            "timestamp": b.timestamp,
                            "open": float(b.open),
                            "high": float(b.high),
                            "low": float(b.low),
                            "close": float(b.close),
                            "volume": float(b.volume),
                        } for b in symbol_bars])

                        df = df.sort_values("timestamp").reset_index(drop=True)
                        self._data_cache[symbol] = df
                        result[symbol] = df

                except Exception as e:
                    err_str = str(e).lower()
                    if "401" in err_str or "403" in err_str:
                        self._auth_failed = True
                        logger.error(
                            "Scanner: auth error in {} batch {}: {} — aborting scan",
                            group_name, i, e,
                        )
                        break
                    logger.warning(
                        "Scanner: {} batch {} ({}/{}) failed: {}",
                        group_name, i + 1, len(batch), len(group_symbols), e,
                    )
                    continue

        # Process stock symbols (most common case)
        _process_group(stock_symbols, StockBarsRequest, self.data_client.get_stock_bars, "stock")

        # Process crypto symbols — prefer broker.get_bars() (FASE 17)
        crypto_broker = self._brokers.get("crypto")
        if crypto_broker is not None and crypto_symbols:
            for symbol in crypto_symbols:
                try:
                    self._token_bucket.consume(1)
                    df = crypto_broker.get_bars(
                        symbol, timeframe="1d",
                        start=_batch_start, end=_batch_end,
                    )
                    if df is not None and not df.empty:
                        # Ensure timestamp is a regular column
                        if df.index.name == "timestamp":
                            df = df.reset_index()
                        self._data_cache[symbol] = df
                        result[symbol] = df
                except Exception as e:
                    logger.warning(
                        "Scanner: crypto {} failed via broker: {} — skipping", symbol, e,
                    )
        elif self.crypto_data_client is not None:
            _process_group(
                crypto_symbols,
                CryptoBarsRequest,
                self.crypto_data_client.get_crypto_bars,
                "crypto",
            )
        elif crypto_symbols:
            logger.warning(
                "Scanner: {} crypto symbols skipped — no crypto broker/client configured",
                len(crypto_symbols),
            )

        return result

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

        scan_history = self._scan_history[-10:]
        # Ensure each scan_entry has elapsed_seconds; fill 0.0 for legacy entries
        for entry in scan_history:
            if "elapsed_seconds" not in entry:
                entry["elapsed_seconds"] = 0.0

        data = {
            "last_scan": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_signals": len(last_scan),
                "top_signals": top_list,
            },
            "scan_history": scan_history,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write(LOGS_DIR / "scanner_results.json", data)
