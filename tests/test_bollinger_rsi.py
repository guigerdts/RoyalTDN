#!/usr/bin/env python3
"""RoyalTDN — Test BollingerRSIStrategy

Verifica:
1. Import y construcción
2. validate() con parámetros válidos e inválidos
3. generate_signal() → BUY (precio en banda inferior + RSI bajo)
4. generate_signal() → SELL (precio en banda media)
5. generate_signal() → None con datos insuficientes
6. generate_signal() → None sin señal
7. get_parameters()

Uso:
    python tests/test_bollinger_rsi.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from royaltdn.strategy.base import BaseStrategy
from royaltdn.strategy.bollinger_rsi import BollingerRSIStrategy


def test_import_and_construction():
    """Clase importa y construye."""
    s = BollingerRSIStrategy()
    assert s.name == "bollinger_rsi"
    assert s.timeframe == "5min"
    assert isinstance(s, BaseStrategy)
    print("  ✅ Import y construcción")


def test_validate_ok():
    """Parámetros válidos."""
    s = BollingerRSIStrategy(bb_period=20, bb_std=2.0, rsi_oversold=30, rsi_overbought=70)
    assert s.validate() is True
    print("  ✅ validate() OK")


def test_validate_invalid():
    """bb_period <= 0 → False."""
    s = BollingerRSIStrategy(bb_period=0)
    assert s.validate() is False
    print("  ✅ validate() rechaza bb_period=0")


def test_validate_oversold_overbought():
    """rsi_oversold >= rsi_overbought → False."""
    s = BollingerRSIStrategy(rsi_oversold=70, rsi_overbought=30)
    assert s.validate() is False
    print("  ✅ validate() rechaza oversold >= overbought")


def test_generate_signal_buy():
    """Precio en banda inferior + RSI bajo → BUY."""
    s = BollingerRSIStrategy(bb_period=10, bb_std=2.0, rsi_period=10, rsi_oversold=40)

    # Plano prolongado, luego crash fuerte (precio perfora banda inferior)
    vals = [100.0] * 20 + [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 80, 70]
    data = pd.DataFrame({"close": vals})
    signal = s.generate_signal(data)
    assert signal is not None, "Esperaba BUY"
    assert signal["action"] == "BUY", f"Esperaba BUY, obtuve {signal['action']}"
    assert "bb_lower" in signal["metadata"]
    assert "rsi" in signal["metadata"]
    print(f"  ✅ BUY @ {signal['price']:.2f} (RSI={signal['metadata']['rsi']:.1f})")


def test_generate_signal_sell():
    """Precio alcanza banda media → SELL."""
    s = BollingerRSIStrategy(
        bb_period=10, bb_std=2.0, rsi_period=10,
        rsi_oversold=20, rsi_overbought=80,
        exit_bb_middle=True,
    )

    # Subida fuerte después de crash → precio recupera banda media
    vals = [100.0] * 20 + [80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92]
    data = pd.DataFrame({"close": vals})
    signal = s.generate_signal(data)
    assert signal is not None, "Esperaba SELL"
    assert signal["action"] == "SELL", f"Esperaba SELL, obtuve {signal['action']}"
    print(f"  ✅ SELL @ {signal['price']:.2f}")


def test_generate_signal_insufficient_data():
    """Menos datos que bb_period → None."""
    s = BollingerRSIStrategy(bb_period=20)
    data = pd.DataFrame({"close": [100] * 10})
    signal = s.generate_signal(data)
    assert signal is None
    print("  ✅ None con datos insuficientes")


def test_generate_signal_no_signal():
    """Mercado neutral → None."""
    s = BollingerRSIStrategy(bb_period=10, rsi_period=10, rsi_oversold=30, rsi_overbought=70)
    # Plano con ruido mínimo — no activa ni BUY ni SELL
    np.random.seed(42)
    vals = [100.0] + list(100 + np.random.normal(0, 0.3, 24))
    data = pd.DataFrame({"close": vals})
    signal = s.generate_signal(data)
    assert signal is None
    print("  ✅ None en mercado neutral")


def test_get_parameters():
    """get_parameters devuelve perfiles duales con prefijos cuando no hay symbol."""
    s = BollingerRSIStrategy(bb_period=20, bb_std=2.0)
    params = s.get_parameters()
    # Sin symbol → retorna ambos perfiles con prefijos crypto_* / stocks_*
    assert params["crypto_bb_period"] == 15
    assert params["stocks_bb_period"] == 20
    assert params["crypto_bb_std"] == 2.5
    assert params["stocks_bb_std"] == 2.0
    assert params["crypto_timeframe"] == "5min"
    assert params["stocks_timeframe"] == "15min"
    print("  ✅ get_parameters()")

def test_get_parameters_with_symbol():
    """get_parameters(symbol) retorna perfil único."""
    s = BollingerRSIStrategy(bb_period=20, bb_std=2.0)
    crypto = s.get_parameters("BTCUSDT")
    assert crypto["bb_period"] == 15
    assert crypto["bb_std"] == 2.5
    stock = s.get_parameters("AAPL")
    assert stock["bb_period"] == 20
    assert stock["bb_std"] == 2.0
    print("  ✅ get_parameters(symbol)")


def main():
    print("=" * 50)
    print("RoyalTDN — Test BollingerRSIStrategy")
    print("Fase 5.3 — Mean Reversion")
    print("=" * 50)

    test_import_and_construction()
    test_validate_ok()
    test_validate_invalid()
    test_validate_oversold_overbought()
    test_generate_signal_buy()
    test_generate_signal_sell()
    test_generate_signal_insufficient_data()
    test_generate_signal_no_signal()
    test_get_parameters()
    test_get_parameters_with_symbol()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
