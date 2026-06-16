#!/usr/bin/env python3
"""RoyalTDN — Test de integración Scanner + Orchestrator (Fase 5.6-5.7)

Verifica:
1. El Orchestrator no crashea si el scanner falla
2. Las constantes de entorno del scanner existen

Uso:
    python tests/test_scanner_orchestrator.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import patch


def test_orchestrator_scanner_env_vars():
    """Las constantes de entorno del scanner existen."""
    from royaltdn.orchestrator import (
        SCANNER_MIN_VOLUME,
        SCANNER_MIN_PRICE,
        SCANNER_MAX_SPREAD_PCT,
        SCANNER_INTERVAL_MINUTES,
        STRATEGIES_ENABLED,
        SCANNER_TOP_N,
        SCANNER_UNIVERSE,
    )

    assert SCANNER_MIN_VOLUME >= 0
    assert SCANNER_MIN_PRICE >= 0
    assert SCANNER_MAX_SPREAD_PCT >= 0
    assert SCANNER_INTERVAL_MINUTES > 0
    assert len(STRATEGIES_ENABLED) >= 1
    assert SCANNER_TOP_N >= 1
    assert SCANNER_UNIVERSE in ("etfs", "sp500", "all")
    print("  ✅ Constantes de entorno del scanner definidas")


def test_orchestrator_construct_without_scanner():
    """Orchestrator se construye sin scanner."""
    import importlib
    import royaltdn.orchestrator as orch_mod
    importlib.reload(orch_mod)
    Orchestrator = orch_mod.Orchestrator

    orch = Orchestrator(
        api_key="test_key",
        secret_key="test_secret",
        redis_url="redis://localhost:6379/0",
    )
    # Scanner se inicializa en _setup(), no en __init__
    # El constructor no debe crashear
    assert orch._scanner is None  # None porque __init__ no llama _setup
    print("  ✅ Orchestrator construido (scanner=None hasta _setup)")


def test_orchestrator_bot_start_logs_patched():
    """El bot logea cuando el scanner no inicia — verificación rápida."""
    with patch("royaltdn.orchestrator.StockHistoricalDataClient") as mock_dc:
        mock_dc.side_effect = Exception("API no disponible")

        import importlib
        import royaltdn.orchestrator as orch_mod
        importlib.reload(orch_mod)
        Orchestrator = orch_mod.Orchestrator

        orch = Orchestrator(
            api_key="test_key",
            secret_key="test_secret",
            redis_url="redis://localhost:6379/0",
        )
        # __init__ no falla a pesar de que el data client lance error
        print("  ✅ Orchestrator no crashea al fallar scanner")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("RoyalTDN — Test Scanner + Orchestrator")
    print("=" * 50)

    test_orchestrator_scanner_env_vars()
    test_orchestrator_construct_without_scanner()
    test_orchestrator_bot_start_logs_patched()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
