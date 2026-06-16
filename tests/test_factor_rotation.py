#!/usr/bin/env python3
"""RoyalTDN — Test FactorRotationStrategy

Verifica:
1. Import y construcción
2. validate() con parámetros válidos e inválidos
3. generate_signal() → RANK con score calculado
4. generate_signal() → None con datos insuficientes
5. get_parameters()

Uso:
    python tests/test_factor_rotation.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.factor_rotation import FactorRotationStrategy


def test_import_and_construction():
    """Clase importa y construye."""
    s = FactorRotationStrategy()
    assert s.name == "factor_rotation"
    assert s.timeframe == "1d"
    assert len(s.etf_universe) == 10
    assert isinstance(s, BaseStrategy)
    print("  ✅ Import y construcción")


def test_validate_ok():
    """Parámetros válidos."""
    s = FactorRotationStrategy(momentum_period=126, top_n=3)
    assert s.validate() is True
    print("  ✅ validate() OK")


def test_validate_invalid():
    """top_n > len(universe) → False."""
    s = FactorRotationStrategy(top_n=100)
    assert s.validate() is False
    print("  ✅ validate() rechaza top_n > universe")


def test_generate_signal_rank():
    """Datos suficientes → RANK con score."""
    s = FactorRotationStrategy(momentum_period=10, volatility_period=5)

    # Tendencia alcista sostenida
    vals = [100.0 + i * 0.5 for i in range(15)]
    data = pd.DataFrame({"close": vals})

    signal = s.generate_signal(data)
    assert signal is not None, "Esperaba RANK"
    assert signal["action"] == "RANK", f"Esperaba RANK, obtuve {signal['action']}"
    assert "score" in signal["metadata"]
    assert "momentum" in signal["metadata"]
    assert "volatility" in signal["metadata"]
    assert signal["metadata"]["score"] > 0, "Score debería ser positivo (tendencia alcista)"
    print(f"  ✅ RANK score={signal['metadata']['score']:.4f}")


def test_generate_signal_rank_negative():
    """Tendencia bajista → score negativo."""
    s = FactorRotationStrategy(momentum_period=10, volatility_period=5)

    # Tendencia bajista
    vals = [100.0 - i * 0.5 for i in range(15)]
    data = pd.DataFrame({"close": vals})

    signal = s.generate_signal(data)
    assert signal is not None, "Esperaba RANK"
    assert signal["action"] == "RANK"
    assert signal["metadata"]["score"] < 0, "Score debería ser negativo (tendencia bajista)"
    print(f"  ✅ RANK score={signal['metadata']['score']:.4f} (negativo)")


def test_generate_signal_insufficient_data():
    """Menos datos que momentum_period → None."""
    s = FactorRotationStrategy(momentum_period=126)
    data = pd.DataFrame({"close": [100] * 50})
    signal = s.generate_signal(data)
    assert signal is None
    print("  ✅ None con datos insuficientes")


def test_get_parameters():
    """get_parameters devuelve dict completo."""
    s = FactorRotationStrategy(momentum_period=126, top_n=3)
    params = s.get_parameters()
    assert params["momentum_period"] == 126
    assert params["top_n"] == 3
    assert len(params["etf_universe"]) == 10
    assert "timeframe" in params
    print("  ✅ get_parameters()")


def main():
    print("=" * 50)
    print("RoyalTDN — Test FactorRotationStrategy")
    print("Fase 5.5 — Rotación de ETFs")
    print("=" * 50)

    test_import_and_construction()
    test_validate_ok()
    test_validate_invalid()
    test_generate_signal_rank()
    test_generate_signal_rank_negative()
    test_generate_signal_insufficient_data()
    test_get_parameters()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
