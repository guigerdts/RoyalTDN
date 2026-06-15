#!/usr/bin/env python3
"""RoyalTDN — Test del Orchestrator (módulos y construcción).

Verifica que:
1. Orchestrator importa correctamente
2. Se construye con parámetros por defecto
3. main.py redirige comandos correctamente
4. legacy_polling está accesible

Uso:
    python tests/test_orchestrator.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_orchestrator_import():
    from royaltdn.orchestrator import Orchestrator
    assert Orchestrator is not None
    assert Orchestrator.run is not None
    print("  ✅ Orchestrator importado")


def test_orchestrator_construction():
    from royaltdn.orchestrator import Orchestrator

    orch = Orchestrator(
        api_key="test_key",
        secret_key="test_secret",
        redis_url="redis://localhost:6379/0",
        symbol="SPY",
    )

    assert orch.api_key == "test_key"
    assert orch.symbol == "SPY"
    assert orch.sma_fast == 5
    assert orch.sma_slow == 20
    assert orch.feed == "iex"
    print("  ✅ Orchestrator construido correctamente")


def test_legacy_import():
    from royaltdn.legacy_polling import main, cmd_check, run_bot
    assert main is not None
    assert cmd_check is not None
    assert run_bot is not None
    print("  ✅ legacy_polling importado")


def test_main_commands():
    from royaltdn.main import cmd_check, cmd_run, main
    assert cmd_check is not None
    assert cmd_run is not None
    assert main is not None
    print("  ✅ main.py comandos disponibles")


def main():
    print("=" * 50)
    print("RoyalTDN — Test Orchestrator")
    print("Fase 4 — Arquitectura Modular")
    print("=" * 50)

    test_orchestrator_import()
    test_orchestrator_construction()
    test_legacy_import()
    test_main_commands()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
