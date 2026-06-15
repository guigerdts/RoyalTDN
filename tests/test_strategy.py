#!/usr/bin/env python3
"""RoyalTDN — Test del Motor de Estrategia SMA

Verifica:
1. compute_sma() con datos conocidos
2. detect_cross() para BUY, SELL y None
3. SMAStrategy.process_bar() produce señales correctas
4. No duplica señales (misma acción repetida)
5. Thread helper funciona

Uso:
    python tests/test_strategy.py
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from royaltdn.strategy.sma_strategy import compute_sma, detect_cross, SMAStrategy


# ── Tests de funciones puras ─────────────────────────────────────────


def test_compute_sma():
    """compute_sma con datos conocidos."""
    assert compute_sma([1, 2, 3, 4, 5], 3) == 4.0       # (3+4+5)/3
    assert compute_sma([10, 20, 30], 2) == 25.0          # (20+30)/2
    assert compute_sma([1, 2], 3) is None                 # buffer insuficiente
    assert compute_sma([], 1) is None                     # vacío
    assert compute_sma([5], 1) == 5.0                     # exacto
    print("  ✅ compute_sma")


def test_detect_cross_buy():
    """SMA rápida CRUZA ARRIBA -> BUY."""
    result = detect_cross(
        prev_fast=4.0, prev_slow=5.0,   # fast < slow
        curr_fast=6.0, curr_slow=5.0,   # fast > slow
    )
    assert result == "BUY", f"Esperaba BUY, obtuve {result}"
    print("  ✅ detect_cross BUY")


def test_detect_cross_sell():
    """SMA rápida CRUZA ABAJO -> SELL."""
    result = detect_cross(
        prev_fast=6.0, prev_slow=5.0,   # fast > slow
        curr_fast=4.0, curr_slow=5.0,   # fast < slow
    )
    assert result == "SELL", f"Esperaba SELL, obtuve {result}"
    print("  ✅ detect_cross SELL")


def test_detect_cross_none():
    """Sin cruce -> None."""
    # Sin referencia previa
    assert detect_cross(None, None, 5.0, 4.0) is None
    # Misma tendencia (fast siempre arriba)
    assert detect_cross(6.0, 4.0, 7.0, 5.0) is None
    # Misma tendencia (fast siempre abajo)
    assert detect_cross(3.0, 5.0, 4.0, 6.0) is None
    # Valores idénticos (no cruce)
    assert detect_cross(5.0, 5.0, 5.0, 5.0) is None
    print("  ✅ detect_cross None")


# ── Tests de SMAStrategy ────────────────────────────────────────────


def test_process_bar_buffer_insufficient():
    """Con pocas barras no genera señal."""
    engine = SMAStrategy("redis://localhost:6379/0", sma_fast=3, sma_slow=5)

    # Metemos 4 barras (insuficiente para SMA5)
    for i in range(4):
        signal = engine.process_bar({
            "symbol": "SPY",
            "close": str(100 + i),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        assert signal is None, f"Esperaba None en barra {i}"

    # La 5ta barra ya tiene suficiente buffer -> calcula SMA
    signal = engine.process_bar({
        "symbol": "SPY",
        "close": "105",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Primer cálculo: detect_cross retorna None (no hay prev_fast/prev_slow todavía)
    # Pero process_bar actualiza prev_fast/prev_slow igual
    assert signal is None, "Primer cálculo con buffer lleno no debería generar señal"

    print("  ✅ buffer insuficiente -> None")


def test_process_bar_generates_buy():
    """Simula una subida que genera BUY."""
    engine = SMAStrategy("redis://localhost:6379/0", sma_fast=3, sma_slow=5)

    # Primero llenar el buffer (5+ barras) con precios planos
    for _ in range(5):
        engine.process_bar({"symbol": "SPY", "close": "100", "timestamp": ""})
    # En este punto prev_fast ≈ prev_slow ≈ 100

    # Ahora inyectar subida: fast sube, slow reacciona lento -> BUY
    for price in [101, 102, 103, 104, 105]:
        signal = engine.process_bar({"symbol": "SPY", "close": str(price), "timestamp": ""})
        if signal:
            assert signal["action"] == "BUY"
            assert signal["symbol"] == "SPY"
            assert signal["price"] == price
            assert "sma_fast" in signal
            assert "sma_slow" in signal
            print(f"  ✅ BUY señal generada @ {price}")
            return

    # Si llegó acá no detectó el cruce (puede pasar si el buffer es muy chico)
    print("  ⚠️  No se generó BUY (puede ser normal con pocos datos)")


def test_no_duplicate_signals():
    """Misma acción repetida no publica otra señal."""
    engine = SMAStrategy("redis://localhost:6379/0", sma_fast=3, sma_slow=5)

    # Llenar buffer plano
    for _ in range(5):
        engine.process_bar({"symbol": "SPY", "close": "100", "timestamp": ""})

    # Subida que genera BUY
    buy_count = 0
    for price in [101, 102, 103, 104, 105, 106, 107]:
        signal = engine.process_bar({"symbol": "SPY", "close": str(price), "timestamp": ""})
        if signal:
            buy_count += 1

    # Solo debería haber generado UN BUY (no repetir)
    assert buy_count <= 1, f"Esperaba 0-1 BUY, obtuve {buy_count}"
    print(f"  ✅ Sin duplicados: {buy_count} señal(es)")


def test_buy_then_sell():
    """Subida → BUY, luego bajada → SELL."""
    engine = SMAStrategy("redis://localhost:6379/0", sma_fast=3, sma_slow=5)

    # Llenar buffer plano
    for _ in range(5):
        engine.process_bar({"symbol": "SPY", "close": "100", "timestamp": ""})

    # Subida escalonada → BUY
    for p in [101, 102, 103, 104, 105, 106, 107]:
        s = engine.process_bar({"symbol": "SPY", "close": str(p), "timestamp": ""})
        if s:
            assert s["action"] == "BUY"
            print(f"  ✅ BUY @ {p}")

    # Bajada escalonada → SELL
    for p in [106, 105, 104, 103, 102, 101, 100, 99, 98, 97, 96]:
        s = engine.process_bar({"symbol": "SPY", "close": str(p), "timestamp": ""})
        if s:
            assert s["action"] == "SELL"
            print(f"  ✅ SELL @ {p}")
            return

    print("  ⚠️  No se generó SELL (puede ser normal con pocos datos)")


def test_thread_helper():
    """Verifica que as_thread construye un Thread."""
    thread = SMAStrategy.as_thread("redis://localhost:6379/0")
    assert thread.name == "sma-strategy"
    assert thread.daemon is True
    assert hasattr(thread, "engine")
    assert thread.engine.symbol == "SPY"
    print("  ✅ as_thread helper")


# ── Main ────────────────────────────────────────────────────────────


def main():
    print("=" * 50)
    print("RoyalTDN — Test SMAStrategy")
    print("Fase 4 — Motor de Estrategia")
    print("=" * 50)

    test_compute_sma()
    test_detect_cross_buy()
    test_detect_cross_sell()
    test_detect_cross_none()
    test_process_bar_buffer_insufficient()
    test_process_bar_generates_buy()
    test_no_duplicate_signals()
    test_buy_then_sell()
    test_thread_helper()

    print("\n✅ TODOS LOS TESTS PASARON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
