# RoyalTDN

Bot de trading algorítmico de grado profesional construido sobre **Python + Alpaca + Redis + TimescaleDB + Grafana**.

**Stack**: Python 3.13 (asyncio), Alpaca API (paper + live), Redis Streams, TimescaleDB, Grafana, Docker, Streamlit, pandas-ta.

**Estado**: Fase 7 — Constructor visual de estrategias multi-indicador con backtesting integrado.

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
│  _run_legacy_loop ──► REST Alpaca ──► SMA inline ──► execute_signal ──► _publish_status │
│       │                                                                                 │
│       ├── _watch_user_strategies() ──► detecta cambios en user_strategies/*.json       │
│       └── evalúa DynamicStrategy de usuario ──► señales BUY/SELL                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend (Fase 6+7)                  │
│                                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Dashboard │ │ Scanner  │ │Estrategias│ │  Trades  │ │  Logs  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  🛠️ Builder (Fase 7)                                     │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │    │
│  │  │ Indicadores   │ │ JSON Preview │ │ Save / Load      │  │    │
│  │  │ + Reglas      │ │ + Backtest   │ │ + Deploy         │  │    │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Componentes

| Módulo | Descripción | Archivo |
|--------|-------------|---------|
| `DataIngestor` | WebSocket Alpaca → Redis Stream `market_bars` | `ingestion/data_ingestor.py` |
| `BollingerRSIStrategy` | Estrategia Bollinger + RSI (oversold/overbought) | `strategy/bollinger_rsi.py` |
| `MomentumATRStrategy` | Estrategia momentum con trailing ATR | `strategy/momentum_atr.py` |
| `FactorRotationStrategy` | Rotación de factores basada en ranking | `strategy/factor_rotation.py` |
| `Orchestrator` | Coordina todo: threads, risk manager, ejecución, TCA, **watcher de estrategias de usuario** | `orchestrator.py` |
| `Scanner` | Escaneo multi-estrategia del universo de activos | `scanner.py` |
| `TWAP` | Ejecución time-weighted average price para órdenes grandes | `execution/twap.py` |
| `TCA` | Transaction Cost Analysis (slippage en bps) | `monitoring/tca.py` |
| `Risk Manager` | Position sizing (ATR), kill switches (drawdown, pérdidas seguidas) | `risk_manager.py` |
| `Frontend` | **Streamlit** 6 páginas: Dashboard, Scanner, Estrategias, Trades, Logs, **Builder** | `frontend/` |
| — | — | — |
| *Fase 7* | | |
| `indicators` | 16 funciones indicadoras (15 pandas-ta + SmartMoneyFlowCloud manual) | `strategy/indicators.py` |
| `rule_engine` | Evaluador recursivo de árboles de reglas AND/OR (20+ operadores) | `strategy/rule_engine.py` |
| `schema` | Validador JSON v1 para configuraciones de estrategia | `strategy/schema.py` |
| `StrategyStore` | CRUD atómico de estrategias de usuario (JSON + timestamps) | `strategy/strategy_store.py` |
| `DynamicStrategy` | Estrategia definida en runtime desde JSON, hereda de BaseStrategy | `strategy/dynamic.py` |
| `Backtesting` | Motor de backtesting con yfinance + simulación de portafolio | `strategy/backtesting.py` |
| `Builder UI` | Constructor visual 3 columnas (paleta, reglas, preview, backtest, gestión) | `frontend/pages/builder.py` |

## Comandos

```bash
python -m royaltdn check        # Verificar conexión Alpaca Paper
python -m royaltdn run           # Bot completo (ingestor → Redis → strategy → ejecución)
                                # Con auto-fallback a legacy si ingestor falla
python -m royaltdn run-legacy    # Bot legacy directo (sin Redis)

streamlit run src/royaltdn/frontend/app.py  # Frontend Streamlit (6 páginas)
```

### Modo run (recomendado)

Arranca la arquitectura modular completa. Si Redis no está disponible o el thread del `DataIngestor` falla (ej: conflicto de event loop en `alpaca-py`), el `Orchestrator` **detecta automáticamente la muerte del thread** y transiciona a modo legacy:

```bash
# Normal (con Redis + TimescaleDB)
REDIS_URL=redis://localhost:6379/0 python -m royaltdn run

# Forzar fallback legacy (Redis inválido)
REDIS_URL=redis://noexiste:6379/0 python -m royaltdn run
```

En modo legacy, el risk manager, TWAP, alertas Telegram, **y las estrategias de usuario** siguen activos — solo cambia la fuente de datos (REST polling cada 60s en vez de WebSocket).

### Frontend Streamlit

```bash
# Instalar dependencias de frontend
pip install -r requirements/fase6.txt

# Iniciar
streamlit run src/royaltdn/frontend/app.py --server.port 8501
```

6 páginas:
- **📊 Dashboard** — Métricas, equity curve, drawdown, posiciones abiertas, estado del bot
- **🔍 Scanner** — Resultados del escaneo multi-estrategia
- **⚙️ Estrategias** — Estado de estrategias activas
- **📈 Trades** — Historial de trades
- **📋 Logs** — Logs del bot en tiempo real
- **🛠️ Builder** — Constructor visual de estrategias (Fase 7)

## Strategy Builder (Fase 7)

Constructor visual para crear estrategias de trading sin código:

1. **Paleta de indicadores** (columna izquierda): seleccioná entre 16 indicadores, configurá parámetros, agregalos a la estrategia
2. **Reglas de entrada/salida** (columna izquierda): construí árboles lógicos AND/OR con condiciones sobre indicadores
3. **Vista previa JSON** (columna central): el JSON de configuración se genera automáticamente
4. **Backtesting** (columna central): ejecutá el backtest con datos reales de Yahoo Finance, métricas (Sharpe, Sortino, WinRate, MaxDD) + 4 charts Plotly
5. **Gestión** (columna derecha): guardá, cargá, validá y desplegá estrategias
6. **Watcher automático**: el Orchestrator detecta nuevas estrategias guardadas y las carga sin reiniciar

### 16 indicadores disponibles

| Indicador | Librería | Parámetros clave |
|-----------|----------|------------------|
| SMA | pandas-ta | period, source |
| EMA | pandas-ta | period, source |
| RSI | pandas-ta | period, source |
| MACD | pandas-ta | fast, slow, signal, source |
| Bollinger Bands | pandas-ta | period, std, source |
| ATR | pandas-ta | period |
| Volume | pandas-ta | — |
| Ichimoku Cloud | pandas-ta | tenkan, kijun, senkou |
| SuperTrend | pandas-ta | period, multiplier |
| VWAP | pandas-ta / manual | anchor |
| Z-Score | pandas-ta | period, entry/exit thresholds |
| ADX | pandas-ta | period |
| OBV | pandas-ta | — |
| Stochastic | pandas-ta | k_period, d_period, slowing |
| Parabolic SAR | pandas-ta | af, max_af |
| **SmartMoneyFlowCloud** | **Manual** | trend_length, flow_window, atr_length |

### 20+ operadores de reglas

- **Comparación**: `>`, `>=`, `<`, `<=`, `==`, `!=`
- **Crossover**: `crosses_above`, `crosses_below`
- **Overbought/Oversold**: `is_overbought`, `is_oversold`, `exits_overbought`, `exits_oversold`
- **Tendencia**: `trend_strong`, `trend_weak`
- **Bandas**: `inside_band`, `breaks_above_band`, `breaks_below_band`
- **Ichimoku**: `price_above_cloud`, `price_below_cloud`, `price_in_cloud`, `tenkan_crosses_kijun`, `price_crosses_chikou`
- **Smart Money Flow**: `smf_above_basis`, `smf_below_basis`, `smf_regime_bull/bear`, `smf_retest_bull/bear`

### Arquitectura de persistencia

```
user_strategies/
├── my_rsi_strategy_20260616_120000_123.json   # version 1
├── my_rsi_strategy_20260616_120500_456.json   # version 2
└── otra_estrategia_20260616_121000_789.json
```

- Escritura atómica (tempfile + os.replace)
- Timestamps con precisión de milisegundos
- Versionado automático (múltiples saves del mismo nombre)
- Watcher en Orchestrator detecta nuevos archivos cada 60s

## Setup

```bash
# Dependencias base
pip install alpaca-py redis python-dotenv pandas numpy

# Fase 5-6 (Scanner + Frontend)
pip install -r requirements/fase6.txt

# Fase 7 (Builder + Backtesting)
pip install -r requirements/fase7.txt

# Variables de entorno (ver .env.example)
export ALPACA_API_KEY="tu_key"
export ALPACA_SECRET_KEY="tu_secret"
export REDIS_URL="redis://localhost:6379/0"    # Opcional — fallback legacy sin Redis
export DATABASE_URL=""                          # Opcional — TimescaleDB

# Ejecutar bot
python -m royaltdn run

# Ejecutar frontend
streamlit run src/royaltdn/frontend/app.py
```

## Tests

```bash
pytest tests/ -v
```

88 tests en total cubriendo: SMA, BollingerRSI, MomentumATR, FactorRotation, Scanner, Orchestrator, TCA, indicadores, rule_engine, schema, StrategyStore, DynamicStrategy, backtesting, integración.

## Roadmap

| Fase | Estado | Descripción |
|------|--------|-------------|
| Fase 0-1 | ✅ | Cimientos: estructura, SMA crossover, backtest VectorBT |
| Fase 2 | ✅ | Risk manager, optimización, notebooks |
| Fase 3 | ✅ | Docker, TimescaleDB, Grafana, CI/CD |
| Fase 4 | ✅ | Arquitectura modular: ingestor → Redis → strategy → orchestrator + auto-fallback |
| Fase 5 | ✅ | Scanner multi-estrategia, estrategias avanzadas (BollingerRSI, MomentumATR, FactorRotation) |
| Fase 6 | ✅ | Frontend Streamlit: Dashboard, Scanner, Estrategias, Trades, Logs + status publishing |
| **Fase 7** | **✅** | **Constructor visual de estrategias: 16 indicadores, reglas lógicas, backtesting, watcher automático** |
