# RoyalTDN

Bot de trading algorítmico de grado profesional construido sobre **Python + Alpaca + Redis + TimescaleDB + Grafana**.

**Stack**: Python 3.13 (asyncio), Alpaca API (paper + live), Redis Streams, TimescaleDB, Grafana, Docker.

**Estado**: Fase 4 — Arquitectura Modular con auto-fallback.

## Arquitectura

```
┌──────────────┐    WebSocket     ┌──────────────────┐   Redis Stream   ┌────────────────┐
│              │ ◄──────────────► │                  │  "market_bars"   │                │
│ DataIngestor │     Alpaca       │      Redis       │ ───────────────► │  SMAStrategy   │
│  (thread)    │     Bars         │   (opcional)     │                  │   (thread)     │
│              │                  │                  │                  │                │
└──────────────┘                  └──────────────────┘                  └───────┬────────┘
                                                                                │
                                                                      Redis Stream "signals"
                                                                                │
                                                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                     Orchestrator                                        │
│                                                                                         │
│  _main_loop ──► consume signals ──► risk check ──► execute (TWAP/market) ──► TCA       │
│                                                                                         │
│  ⚠️ Si DataIngestor muere → auto fallback a _run_legacy_loop (REST polling)             │
│                                                                                         │
│  _run_legacy_loop ──► REST Alpaca ──► SMA inline ──► execute_signal (mismo risk mgr)   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Componentes

| Módulo | Descripción | Archivo |
|--------|-------------|---------|
| `DataIngestor` | WebSocket Alpaca → Redis Stream `market_bars` | `ingestion/data_ingestor.py` |
| `SMAStrategy` | Consume `market_bars` → señales SMA5/SMA20 → `signals` | `strategy/sma_strategy.py` |
| `Orchestrator` | Coordina todo: threads, risk manager, ejecución, TCA | `orchestrator.py` |
| `TWAP` | Ejecución time-weighted average price para órdenes grandes | `execution/twap.py` |
| `TCA` | Transaction Cost Analysis (slippage en bps) | `monitoring/tca.py` |
| `Risk Manager` | Position sizing (ATR), kill switches (drawdown, pérdidas seguidas) | `risk_manager.py` |
| `Legacy Polling` | Bot standalone sin Redis (respaldo histórico) | `legacy_polling.py` |

## Comandos

```bash
python -m royaltdn check        # Verificar conexión Alpaca Paper
python -m royaltdn run           # Bot completo (ingestor → Redis → strategy → ejecución)
                                 # Con auto-fallback a legacy si ingestor falla
python -m royaltdn run-legacy    # Bot legacy directo (sin Redis)
```

### Modo run (recomendado)

Arranca la arquitectura modular completa. Si Redis no está disponible o el thread del `DataIngestor` falla (ej: conflicto de event loop en `alpaca-py`), el `Orchestrator` **detecta automáticamente la muerte del thread** y transiciona a modo legacy:

```bash
# Normal (con Redis + TimescaleDB)
REDIS_URL=redis://localhost:6379/0 python -m royaltdn run

# Forzar fallback legacy (Redis inválido)
REDIS_URL=redis://noexiste:6379/0 python -m royaltdn run
```

En modo legacy, el risk manager, TWAP, y alertas Telegram **siguen activos** — solo cambia la fuente de datos (REST polling cada 60s en vez de WebSocket en tiempo real).

## Setup

```bash
# Dependencias
pip install alpaca-py redis python-dotenv pandas numpy

# Variables de entorno (ver .env.example)
export ALPACA_API_KEY="tu_key"
export ALPACA_SECRET_KEY="tu_secret"
export REDIS_URL="redis://localhost:6379/0"    # Opcional — fallback legacy sin Redis
export DATABASE_URL=""                          # Opcional — TimescaleDB

# Ejecutar
python -m royaltdn run
```

## Roadmap

| Fase | Estado | Descripción |
|------|--------|-------------|
| Fase 0-1 | ✅ | Cimientos: estructura, SMA crossover, backtest VectorBT |
| Fase 2 | ✅ | Risk manager, optimización, notebooks |
| Fase 3 | ✅ | Docker, TimescaleDB, Grafana, CI/CD |
| **Fase 4** | **✅** | **Arquitectura modular: ingestor → Redis → strategy → orchestrator + auto-fallback** |
| Fase 5 | ⬜ | Polígon.io, estrategias avanzadas, ML |
