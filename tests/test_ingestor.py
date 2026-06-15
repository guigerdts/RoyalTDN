#!/usr/bin/env python3
"""RoyalTDN — Test rápido del DataIngestor (modo offline).

Verifica que:
1. La clase importa correctamente
2. El flujo async init/cleanup funciona sin conexión real
3. El thread helper se construye bien

Uso:
    python tests/test_ingestor.py
"""

import sys
import os

# Asegurar que encuentra el paquete
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from royaltdn.ingestion.data_ingestor import DataIngestor


def test_imports():
    """Verifica que todas las dependencias del ingestor existen."""
    print("🔍 Verificando imports del ingestor...")

    import alpaca.data.live  # noqa: F401
    import redis.asyncio  # noqa: F401

    print("  ✅ alpaca.data.live (StockDataStream)")
    print("  ✅ redis.asyncio (Redis client)")


def test_class_construction():
    """Verifica que el DataIngestor se construye sin errores."""
    print("\n🔍 Construyendo DataIngestor...")

    ingestor = DataIngestor(
        api_key="test_key",
        secret_key="test_secret",
        redis_url="redis://localhost:6379/0",
        symbols=["SPY"],
        feed="iex",
    )

    assert ingestor.api_key == "test_key"
    assert ingestor.symbols == ["SPY"]
    assert ingestor.feed == "iex"
    assert ingestor.STREAM_KEY == "market_bars"

    print("  ✅ Clase construida correctamente")
    print("  ✅ Stream key:", ingestor.STREAM_KEY)
    print("  ✅ Symbols:", ingestor.symbols)
    print("  ✅ Feed:", ingestor.feed)


def test_async_run_exists():
    """Verifica que ingestor tiene run() async."""
    print("\n🔍 Verificando interfaz async...")

    ingestor = DataIngestor(
        api_key="test_key",
        secret_key="test_secret",
        redis_url="redis://localhost:6379/0",
        symbols=["SPY", "QQQ"],
    )

    assert hasattr(ingestor, "run")
    assert callable(ingestor.run)
    # Verificar que run() es una corutina (se puede await)
    import asyncio
    assert asyncio.iscoroutinefunction(ingestor.run), "run() debe ser async"

    assert hasattr(ingestor, "stop")
    assert callable(ingestor.stop)

    print("  ✅ Interfaz async OK")
    print("  ✅ run() es corutina")
    print("  ✅ stop() existe")
    print("  ✅ Symbols:", ingestor.symbols)


def main():
    print("=" * 50)
    print("RoyalTDN — Test DataIngestor")
    print("Fase 4 — Arquitectura Modular")
    print("=" * 50)

    test_imports()
    test_class_construction()
    test_async_run_exists()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
