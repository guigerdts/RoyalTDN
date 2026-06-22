# Verificación de Integración — FASE 18.5

## Purpose

Suite de 24 pruebas manuales Given/When/Then para verificar 3 bugs corregidos y estabilidad del menú interactivo.

## Requirements

| Req | Domain | Given | When | Then |
|-----|--------|-------|------|------|
| R1.1 | Arranque | `.env` has single `SCANNER_UNIVERSE=crypto` | menu app starts | header shows `"Universe: crypto"` |
| R1.2 | Nav | menu running | user enters 1-8 (all screens) | each renders without error, 0 returns |
| R1.3 | Universo | menu running | user presses `'U'` | universe cycles, header updates |
| R1.4 | Scalping | `SCANNER_UNIVERSE=etfs` | user opens Scanner | scalping disabled or hidden |
| R2.1 | Scanner | user enters Scanner | screen renders | universe name is shown |
| R2.2 | Scanner | user presses `'s'` | scan completes | metrics panel: total, passed, signals, time |
| R2.3 | Scanner | scan triggered >1 symbol | scan runs | tqdm bars show `Escaneando {symbol}` |
| R2.4 | Scanner | verbose OFF | user presses `'v'` | verbose dashboard OR loading message shown |
| R2.5 | Scanner | bot just started | user opens Scanner w/o `'s'` | `"No hay resultados aún."` shown |
| R3.1 | Estrategias | user enters option 3 | screen renders | sorted table: Nombre, Tipo, Símbolo, Timeframe, Activa, Parámetros |
| R3.2 | Estrategias | user selects strategy + `T` | toggle | `active` field updated |
| R3.3 | Estrategias | user selects `B`acktest | backtest completes | metrics: win rate, profit factor, P&L |
| R4.1 | Trades | user enters option 4 | screen renders | summary: total_trades, win_rate, profit_factor, total_pnl |
| R4.2 | Trades | trades exist | table renders | columns: Symbol, Side, Qty, Entry, Exit, P&L, Date |
| R4.3 | Trades | user enters symbol | filter applied | only matching trades shown; period filters recalc |
| R5.1 | Logs | user enters option 5 | screen renders | last 20 lines with ANSI colors |
| R5.2 | Logs | user selects "1" (INFO) | filter | only INFO lines; search finds matches |
| R6.1 | Control | bot ONLINE | user selects "1" Pausar | `pause_bot()` called, "PAUSADO" shown, activity logged |
| R6.2 | Control | user selects "4" Alertas | screen renders | thresholds shown; edit persists to file |
| R7.1 | Simulación | user enters option 7 | seed data loads | parameter comparison table shown |
| R7.2 | Simulación | seed data loaded | screen renders | 2+ parameter variants side-by-side |
| R8.1 | Actividad | user enters option 8 | screen renders | action log with timestamps (pause, resume, toggle, scan) |
| R9.1 | Salida | menu running | user enters `0` or Ctrl+C+`s` | `orch.stop()` called, clean exit, no traceback |
| R10.1 | check-readiness | bot running >1 day | `python -m royaltdn check-readiness` | Rich Panel with 6 checks, exit code 0/1/2, bot NOT started |
