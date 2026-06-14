#!/usr/bin/env python3
"""RoyalTDN — Smoke Test de Backtesting

Verifica que las dependencias críticas importan correctamente y que
VectorBT puede ejecutar un backtest básico SMA Crossover sin errores.

Uso:
    python tests/smoke_backtest.py          # ejecuta todo
    python tests/smoke_backtest.py --quick  # solo imports (para CI preflight)

Fase 3 — CI/CD Pipeline (documento 05, sección 5.3.4)
"""

import sys
import argparse

# ──────────────────────────────────────────────
# FASE 1: Verificar que el paquete importa
# ──────────────────────────────────────────────
def test_imports() -> bool:
    """Verifica que todas las dependencias críticas importan."""
    print("🔍 Verificando imports...")
    failures = []

    modules = [
        ("pandas", "pd"),
        ("numpy", "np"),
        ("vectorbt", "vbt"),
        ("yfinance", "yf"),
        ("royaltdn", None),
    ]

    for mod_name, alias in modules:
        try:
            mod = __import__(mod_name)
            if alias:
                globals()[alias] = mod
            print(f"  ✅ {mod_name}")
        except ImportError as e:
            print(f"  ❌ {mod_name}: {e}")
            failures.append(mod_name)

    if failures:
        print(f"\n❌ {len(failures)} módulos fallaron: {', '.join(failures)}")
        return False

    print("  ✅ Todos los imports correctos\n")
    return True


# ──────────────────────────────────────────────
# FASE 2: Smoke backtest con VectorBT
# ──────────────────────────────────────────────
def test_smoke_backtest() -> bool:
    """Ejecuta un backtest rápido SMA Crossover con VectorBT.

    Usa parámetros reducidos y rango de fechas acotado (2020-2023)
    para que termine en < 30 segundos en CI.
    """
    print("🔍 Ejecutando smoke backtest SMA Crossover...")

    import numpy as np
    import yfinance as yf
    import vectorbt as vbt

    # ── Datos: SPY 2020-2023 (acotado para velocidad) ──
    print("  Descargando SPY 2020-2023...")
    spy = yf.download("SPY", start="2020-01-01", end="2023-12-31", auto_adjust=True, progress=False)
    close = spy["Close"].squeeze()
    print(f"  {len(close)} velas | ${float(close.iloc[0]):.2f} → ${float(close.iloc[-1]):.2f}")

    if len(close) < 100:
        print("  ❌ Muy pocos datos (< 100 velas)")
        return False

    # ── Parámetros reducidos (grilla chica para velocidad) ──
    fast_periods = np.arange(5, 30, 5)     # 5, 10, 15, 20, 25
    slow_periods = np.arange(30, 100, 15)  # 30, 45, 60, 75, 90

    total_combos = len(fast_periods) * len(slow_periods)
    print(f"  Grid: {len(fast_periods)} fast x {len(slow_periods)} slow = {total_combos} combinaciones")

    # ── Señales vectorizadas ──
    fast_ma = vbt.MA.run(close, window=fast_periods)
    slow_ma = vbt.MA.run(close, window=slow_periods)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    total_entries = int(entries.sum().max())
    print(f"  Señales de entrada (máx por combo): {total_entries}")

    if total_entries == 0:
        print("  ⚠️  No se generaron señales — puede ser normal si no hay cruces")
        # No fallamos por esto; algunas combinaciones simplemente no cruzan

    # ── Portfolio ──
    pf = vbt.Portfolio.from_signals(close, entries, exits, freq="D", init_cash=100_000)

    sharpe_series = pf.sharpe_ratio()
    mdd_series = pf.max_drawdown()
    return_series = pf.total_return()

    best_sharpe = float(sharpe_series.max())
    best_mdd = float(mdd_series.min())
    best_return = float(return_series.max())

    print(f"  Mejor Sharpe:     {best_sharpe:.2f}")
    print(f"  Peor Max DD:      {best_mdd:.2%}")
    print(f"  Mejor Return:     {best_return:.2%}")

    # Verificar que las métricas existen (no None, no NaN)
    if np.isnan(best_sharpe):
        print("  ⚠️  Sharpe es NaN (sin trades), no es error fatal")
    else:
        print(f"  ✅ Sharpe OK: {best_sharpe:.2f}")

    print(f"  ✅ Smoke backtest completado sin excepciones\n")
    return True


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="RoyalTDN — Smoke Test")
    parser.add_argument("--quick", action="store_true", help="Solo verificar imports")
    args = parser.parse_args()

    print("=" * 50)
    print("RoyalTDN — Smoke Test Suite")
    print("Fase 3 — CI/CD Pipeline")
    print("=" * 50)

    # Fase 1: Imports
    imports_ok = test_imports()
    if not imports_ok:
        print("\n❌ SMOKE TEST FALLÓ: imports incorrectos")
        sys.exit(1)

    # Fase 2: Backtest (opcional con --quick)
    if not args.quick:
        backtest_ok = test_smoke_backtest()
        if not backtest_ok:
            print("\n❌ SMOKE TEST FALLÓ: backtest con errores")
            sys.exit(1)

    print("\n✅ TODOS LOS SMOKE TESTS PASARON")
    sys.exit(0)


if __name__ == "__main__":
    main()
