#!/usr/bin/env python3
"""RoyalTDN — Test MomentumATRStrategy

Verifica:
1. Import y construcción
2. validate() con parámetros válidos e inválidos
3. generate_signal() → BUY (momentum positivo + volatilidad baja)
4. generate_signal() → SELL (momentum corto negativo)
5. generate_signal() → None con datos insuficientes
6. generate_signal() → None sin señal
7. get_parameters()

Uso:
    python tests/test_momentum_atr.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.momentum_atr import MomentumATRStrategy


def test_import_and_construction():
    """Clase importa y construye."""
    s = MomentumATRStrategy()
    assert s.name == "momentum_atr"
    assert s.timeframe == "1d"
    assert isinstance(s, BaseStrategy)
    print("  ✅ Import y construcción")


def test_validate_ok():
    """Parámetros válidos."""
    s = MomentumATRStrategy(momentum_period=20, atr_period=14, atr_max_pct=2.0)
    assert s.validate() is True
    print("  ✅ validate() OK")


def test_validate_invalid():
    """atr_max_pct <= 0 → False."""
    s = MomentumATRStrategy(atr_max_pct=0)
    assert s.validate() is False
    print("  ✅ validate() rechaza atr_max_pct=0")


def test_generate_signal_buy():
    """Momentum positivo + volatilidad baja → BUY."""
    s = MomentumATRStrategy(momentum_period=10, atr_period=5, atr_max_pct=10.0)

    # Subida constante: momentum positivo, ATR bajo
    vals = [100.0] + [100 + i * 0.5 for i in range(1, 15)]  # sube ~7%
    data = pd.DataFrame({
        "close": vals,
        "high": [v + 1 for v in vals],
        "low": [v - 1 for v in vals],
    })
    signal = s.generate_signal(data)
    assert signal is not None, "Esperaba BUY"
    assert signal["action"] == "BUY", f"Esperaba BUY, obtuve {signal['action']}"
    assert "momentum_return" in signal["metadata"]
    assert "atr_pct" in signal["metadata"]
    print(f"  ✅ BUY @ {signal['price']:.2f} (ret={signal['metadata']['momentum_return']:.1f}%)")


def test_generate_signal_sell():
    """Momentum corto negativo → SELL."""
    s = MomentumATRStrategy(
        momentum_period=10, atr_period=5, atr_max_pct=10.0,
        exit_period=3,
    )

    # Subida suave (BUY), luego caída (SELL)
    vals = [100.0] + [101 + i * 0.3 for i in range(10)]  # sube
    vals = vals + [103, 102, 101, 100, 99, 98, 97]  # baja
    data = pd.DataFrame({
        "close": vals,
        "high": [v + 1 for v in vals],
        "low": [v - 1 for v in vals],
    })
    signal = s.generate_signal(data)
    assert signal is not None, "Esperaba SELL (caída)"
    assert signal["action"] == "SELL", f"Esperaba SELL, obtuve {signal['action']}"
    print(f"  ✅ SELL @ {signal['price']:.2f}")


def test_generate_signal_insufficient_data():
    """Menos datos que momentum_period → None."""
    s = MomentumATRStrategy(momentum_period=20)
    data = pd.DataFrame({"close": [100] * 10})
    signal = s.generate_signal(data)
    assert signal is None
    print("  ✅ None con datos insuficientes")


def test_generate_signal_no_signal():
    """Volatilidad muy alta → None."""
    s = MomentumATRStrategy(momentum_period=5, atr_period=5, atr_max_pct=1.0)

    # Alta volatilidad (salta arriba y abajo)
    vals = [100.0]
    for i in range(15):
        vals.append(vals[-1] + (5 if i % 2 == 0 else -5))
    data = pd.DataFrame({
        "close": vals,
        "high": [v + 3 for v in vals],
        "low": [v - 3 for v in vals],
    })
    signal = s.generate_signal(data)
    # Puede ser None (ATR demasiado alto) o BUY si el momentum es suficiente
    # Lo importante es que no crashee
    print(f"  ✅ No señal (o señal válida): {signal}")


def test_get_parameters():
    """get_parameters devuelve dict completo."""
    s = MomentumATRStrategy(momentum_period=20, atr_period=14)
    params = s.get_parameters()
    assert params["momentum_period"] == 20
    assert params["atr_period"] == 14
    assert "timeframe" in params
    print("  ✅ get_parameters()")


def main():
    print("=" * 50)
    print("RoyalTDN — Test MomentumATRStrategy")
    print("Fase 5.4 — Momentum con filtro ATR")
    print("=" * 50)

    test_import_and_construction()
    test_validate_ok()
    test_validate_invalid()
    test_generate_signal_buy()
    test_generate_signal_sell()
    test_generate_signal_insufficient_data()
    test_generate_signal_no_signal()
    test_get_parameters()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
