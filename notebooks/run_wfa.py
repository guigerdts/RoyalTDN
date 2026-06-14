#!/usr/bin/env python3
"""RoyalTDN — Walk-Forward Analysis Script (Fase 2)"""
import numpy as np
import pandas as pd
import yfinance as yf
import warnings
import vectorbt as vbt
import os

warnings.filterwarnings('ignore')
print(f"VectorBT: {vbt.__version__} | NumPy: {np.__version__}")

# ── Datos ─────────────────────────────────────────────────────────────────────
print("\n=== DESCARGANDO DATOS SPY 2015-2024 ===")
spy = yf.download('SPY', start='2015-01-01', end='2024-12-31', auto_adjust=True)
close = spy['Close'].squeeze()
print(f"Filas: {len(close)} | Rango: ${close.min():.2f} - ${close.max():.2f}")

# ── Grilla de parámetros ──────────────────────────────────────────────────────
fast_periods = np.arange(2, 30, 2)     # 14 valores
slow_periods = np.arange(30, 200, 10)  # 17 valores
n_fast = len(fast_periods)
n_slow = len(slow_periods)
n_combos = n_fast * n_slow
print(f"Fast SMAs: {n_fast} | Slow SMAs: {n_slow} | Combos: {n_combos}")

# ── Walk-Forward Analysis ────────────────────────────────────────────────────
print("\n" + "="*60)
print("WALK-FORWARD ANALYSIS")
print("="*60)

n_splits = 5
window_days = int(3 * 365.25)
test_days = int(1 * 365.25)

results = []
for fold in range(n_splits):
    train_start = close.index[0] + pd.Timedelta(days=fold * test_days)
    train_end = train_start + pd.Timedelta(days=window_days)
    test_end = train_end + pd.Timedelta(days=test_days)

    if test_end > close.index[-1]:
        print(f"Fold {fold+1}: fuera de rango")
        continue

    train_mask = (close.index >= train_start) & (close.index < train_end)
    test_mask = (close.index >= train_end) & (close.index < test_end)
    ct = close[train_mask]
    cx = close[test_mask]
    if len(ct) < 100 or len(cx) < 50:
        continue

    # ── IN-SAMPLE: optimizar ──
    fast_vals = vbt.MA.run(ct, window=fast_periods).ma.values
    slow_vals = vbt.MA.run(ct, window=slow_periods).ma.values

    f3d = np.repeat(fast_vals[:, :, np.newaxis], n_slow, axis=2)
    s3d = np.repeat(slow_vals[:, np.newaxis, :], n_fast, axis=1)
    entries_is = f3d > s3d
    exits_is = s3d > f3d  # opposite: slow > fast

    entries_is_2d = entries_is.reshape(len(ct), -1)
    exits_is_2d = exits_is.reshape(len(ct), -1)

    pf_is = vbt.Portfolio.from_signals(ct, entries_is_2d, exits_is_2d, freq='D', init_cash=100_000)
    sharpe_is = pf_is.sharpe_ratio()
    best_pos = int(sharpe_is.values.argmax())
    best_sharpe = sharpe_is.max()
    best_f = int(fast_periods[best_pos // n_slow])
    best_s = int(slow_periods[best_pos % n_slow])

    # ── OUT-OF-SAMPLE: validar ──
    fast_oos = np.asarray(vbt.MA.run(cx, window=best_f).ma)
    slow_oos = np.asarray(vbt.MA.run(cx, window=best_s).ma)
    entries_oos = fast_oos > slow_oos
    exits_oos = slow_oos > fast_oos

    pf_oos = vbt.Portfolio.from_signals(cx, entries_oos, exits_oos, freq='D', init_cash=100_000)

    oos_sharpe = float(pf_oos.sharpe_ratio())
    oos_mdd = float(pf_oos.max_drawdown())
    oos_ret = float(pf_oos.total_return())
    n_trades = int(pf_oos.trades.count())

    results.append({
        'Fold': fold + 1,
        'Train': f"{train_start.date()}–{train_end.date()}",
        'Test': f"{train_end.date()}–{test_end.date()}",
        'SMA': f"({best_f},{best_s})",
        'Sharpe_IS': round(float(best_sharpe), 2),
        'Sharpe_OOS': round(oos_sharpe, 2),
        'MaxDD_OOS': f"{oos_mdd*100:.1f}%",
        'Return_OOS': f"{oos_ret*100:.1f}%",
        'Trades': n_trades,
    })
    print(f"Fold {fold+1}: SMA({best_f},{best_s})  "
          f"IS Sharpe: {best_sharpe:.2f} → OOS Sharpe: {oos_sharpe:.2f}  "
          f"Ret: {oos_ret*100:.1f}%  DD: {oos_mdd*100:.1f}%")

# ── Resultados ────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("RESUMEN WALK-FORWARD")
print("="*60)
df = pd.DataFrame(results)
print(df.to_string(index=False))

if len(results) > 0:
    ooss = [r['Sharpe_OOS'] for r in results]
    print(f"\n📊 Sharpe OOS promedio: {np.mean(ooss):.2f}")
    print(f"📊 Sharpe OOS mediana:  {np.median(ooss):.2f}")
    print(f"📊 Sharpe OOS > 1.0:    {sum(1 for s in ooss if s > 1)}/{len(results)}")
    print(f"📊 Sharpe OOS > 0:      {sum(1 for s in ooss if s > 0)}/{len(results)}")
    print(f"📊 Sharpe OOS negativo: {sum(1 for s in ooss if s < 0)}/{len(results)}")

# ── Robustez paramétrica ──────────────────────────────────────────────────────
print("\n" + "="*60)
print("PRUEBA DE ROBUSTEZ")
print("="*60)

best_r = df.loc[df['Sharpe_OOS'].idxmax()]
bf, bs = map(int, best_r['SMA'].strip('()').split(','))
print(f"Mejor par WFA: SMA({bf},{bs})")

variants = [
    (bf, bs, 'Original'),
    (max(2, bf-2), bs, f'Fast-2 ({bf-2},{bs})'),
    (bf+2, bs, f'Fast+2 ({bf+2},{bs})'),
    (bf, max(30, bs-10), f'Slow-10 ({bf},{bs-10})'),
    (bf, bs+10, f'Slow+10 ({bf},{bs+10})'),
    (8, 45, 'Alt (8,45)'),
    (12, 55, 'Alt (12,55)'),
]

robust = []
for f, s, label in variants:
    fast_v = np.asarray(vbt.MA.run(close, window=f).ma)
    slow_v = np.asarray(vbt.MA.run(close, window=s).ma)
    entries_v = fast_v > slow_v
    exits_v = slow_v > fast_v
    pf_v = vbt.Portfolio.from_signals(close, entries_v, exits_v, freq='D', init_cash=100_000)
    robust.append({
        'Variante': label,
        'Sharpe': round(float(pf_v.sharpe_ratio()), 2),
        'MaxDD': f"{float(pf_v.max_drawdown())*100:.1f}%",
        'Return': f"{float(pf_v.total_return())*100:.1f}%",
        'Trades': int(pf_v.trades.count()),
    })

df_rob = pd.DataFrame(robust)
print(df_rob.to_string(index=False))
s_vals = [r['Sharpe'] for r in robust if r['Sharpe'] not in (-np.inf, np.inf)]
if s_vals:
    print(f"\nSharpe promedio: {np.mean(s_vals):.2f} | Std: {np.std(s_vals):.2f}")
    print("✅ ROBUSTA" if np.std(s_vals) < 0.5 else "⚠️ SENSIBLE")

# ── Cross-asset ───────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("VALIDACIÓN CROSS-ASSET")
print("="*60)

for ticker, name in [('QQQ', 'NASDAQ Tech'), ('IWM', 'Small Caps')]:
    try:
        d = yf.download(ticker, start='2015-01-01', end='2024-12-31', auto_adjust=True, progress=False)
        ca = d['Close'].squeeze()
        fv = np.asarray(vbt.MA.run(ca, window=bf).ma)
        sv = np.asarray(vbt.MA.run(ca, window=bs).ma)
        ev = fv > sv
        xv = sv > fv
        p = vbt.Portfolio.from_signals(ca, ev, xv, freq='D', init_cash=100_000)
        print(f"\n{ticker} ({name}): Sharpe={float(p.sharpe_ratio()):.2f}  "
              f"Ret={float(p.total_return())*100:.1f}%  "
              f"DD={float(p.max_drawdown())*100:.1f}%  "
              f"Trades={int(p.trades.count())}")
    except Exception as e:
        print(f"{ticker}: Error — {e}")

# ── Conclusión ────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("CONCLUSIÓN")
print("="*60)
if len(results) > 0:
    avg = np.mean([r['Sharpe_OOS'] for r in results])
    print(f"Sharpe OOS promedio: {avg:.2f}")
    if avg > 1.0:
        print("✅ POTENCIAL ALAFA — Sharpe OOS > 1.0")
    elif avg > 0.5:
        print("⚠️ ALFA DÉBIL — Sharpe OOS entre 0.5 y 1.0")
    else:
        print("❌ SIN ALFA — Sharpe OOS < 0.5. SMA crossover no tiene edge.")
    print("\n⚠️  Esto es la LÍNEA DE BASE (baseline).")
    print("   Estrategias más sofisticadas (Fase 4) deberían superar esto.")
