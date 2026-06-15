#!/usr/bin/env python3
"""RoyalTDN — Test TCA (Transaction Cost Analysis)

Verifica que calculate_slippage funciona correctamente.

Uso:
    python tests/test_tca.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from royaltdn.monitoring.tca import calculate_slippage


def test_slippage_zero():
    """Sin deslizamiento → 0 bps."""
    result = calculate_slippage(execution_price=100.0, arrival_price=100.0)
    assert result == 0.0
    print("  ✅ Slippage cero")


def test_slippage_positive():
    """Compra más cara que arrival → slippage positivo."""
    result = calculate_slippage(execution_price=101.0, arrival_price=100.0)
    # 101 - 100 / 100 * 10000 = 100 bps
    assert result == 100.0
    print("  ✅ Slippage positivo (100 bps)")


def test_slippage_negative():
    """Compra más barata que arrival → slippage negativo (mejor precio)."""
    result = calculate_slippage(execution_price=99.50, arrival_price=100.0)
    # (99.5 - 100) / 100 * 10000 = -50 bps
    assert result == -50.0
    print("  ✅ Slippage negativo (-50 bps)")


def test_slippage_invalid():
    """Precios inválidos → None."""
    assert calculate_slippage(0, 100) is None
    assert calculate_slippage(100, 0) is None
    assert calculate_slippage(100, -1) is None
    assert calculate_slippage(-1, 100) is None
    print("  ✅ Slippage inválido → None")


def test_slippage_small():
    """Slippage pequeño (decimal)."""
    result = calculate_slippage(execution_price=150.05, arrival_price=150.00)
    # (150.05 - 150) / 150 * 10000 = 3.33 bps
    assert abs(result - 3.33) < 0.01
    print("  ✅ Slippage pequeño (3.33 bps)")


def main():
    print("=" * 50)
    print("RoyalTDN — Test TCA")
    print("Fase 4 — Transaction Cost Analysis")
    print("=" * 50)

    test_slippage_zero()
    test_slippage_positive()
    test_slippage_negative()
    test_slippage_invalid()
    test_slippage_small()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
