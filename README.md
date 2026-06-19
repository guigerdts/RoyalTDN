# RoyalTDN

Bot de trading algorítmico de grado profesional construido sobre **Python + Alpaca + Redis + TimescaleDB + Grafana**.

**Stack**: Python 3.13 (asyncio), Alpaca API (paper + live), Redis Streams, TimescaleDB, Grafana, Docker, **Rich TUI**, **Loguru**, pandas-ta.

**Estado**: Fase 11 — Menú interactivo Rich con 8 opciones, Simulación What-if, Registro de Actividad, Alertas configurables.

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
│                         │                                            ▲                  │
│  ⚠️ Si DataIngestor muere → auto fallback a _run_legacy_loop (REST polling)             │
│                         │                                            │                  │
│  _run_legacy_loop ──► REST Alpaca ──► SMA inline ──► execute_signal ──► _publish_status │
│       │                                                                                 │
│       ├── _check_signals() ──► lee pause_signal.json / scanner_trigger.json             │
│       ├── _watch_user_strategies() ──► detecta cambios en user_strategies/*.json       │
│       └── evalúa DynamicStrategy de usuario ──► señales BUY/SELL                        │
└────┬───────────────────────────────────────────────────────────────────────────────┬────┘
     │  publica 7 JSON files                                                         │ poll signals
     ▼ cada ciclo                                                                     ▼
┌──────────────────┐                                                         ┌──────────────────┐
│   logs/*.json     │                                                         │ pause_signal.json│
│   - status        │◄──── lee ─────┐                                         │ scanner_trigger  │
│   - equity        │               │                                         └──────────────────┘
│   - positions     │               │
│   - signals       │               │
│   - strategies    │               │
│   - trades        │               │
│   - scanner_res   │               │
└──────────────────┘               │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Menú Interactivo Rich (Fase 11)                 │
│                                                                   │
│  run_menu() → StateLoader → 8 opciones por número                │
│                                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Dashboard │ │ Scanner  │ │Estrategias│ │  Trades  │ │  Logs  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐                        │
│  │ Control  │ │Simulación★│ │Actividad★│                        │
│  └──────────┘ └────────────┘ └──────────┘                        │
│                                                                   │
│  Badges: 🔔 señales nuevas  💰 trades nuevos                     │
│  PAUSADO en amarillo en header/Control/Dashboard KPI             │
└──────────────────────────────────────────────────────────────────┘
```

### Componentes

| Módulo | Descripción | Archivo |
|--------|-------------|---------|
| `DataIngestor` | WebSocket Alpaca → Redis Stream `market_bars` | `ingestion/data_ingestor.py` |
| `BollingerRSIStrategy` | Estrategia Bollinger + RSI (oversold/overbought) | `strategy/bollinger_rsi.py` |
| `MomentumATRStrategy` | Estrategia momentum con trailing ATR | `strategy/momentum_atr.py` |
| `FactorRotationStrategy` | Rotación de factores basada en ranking | `strategy/factor_rotation.py` |
| `Orchestrator` | Coordina todo: threads, risk manager, ejecución, TCA, **IPC signal polling**, watcher de estrategias | `orchestrator.py` |
| `Scanner` | Escaneo multi-estrategia del universo de activos | `scanner.py` |
| `TWAP` | Ejecución time-weighted average price para órdenes grandes | `execution/twap.py` |
| `TCA` | Transaction Cost Analysis (slippage en bps) | `monitoring/tca.py` |
| `Risk Manager` | Position sizing (ATR), kill switches (drawdown, pérdidas seguidas) | `risk_manager.py` |
| — | — | — |
| *Fase 7* | | |
| `indicators` | 16 funciones indicadoras (15 pandas-ta + SmartMoneyFlowCloud manual) | `strategy/indicators.py` |
| `rule_engine` | Evaluador recursivo de árboles de reglas AND/OR (20+ operadores) | `strategy/rule_engine.py` |
| `schema` | Validador JSON v1 para configuraciones de estrategia | `strategy/schema.py` |
| `StrategyStore` | CRUD atómico de estrategias de usuario (JSON + timestamps) | `strategy/strategy_store.py` |
| `DynamicStrategy` | Estrategia definida en runtime desde JSON, hereda de BaseStrategy | `strategy/dynamic.py` |
| `Backtesting` | Motor de backtesting con yfinance + simulación de portafolio | `strategy/backtesting.py` |
| `Builder UI` | Constructor visual 3 columnas (paleta, reglas, preview, backtest, gestión) | `frontend/pages/builder.py` |
| — | — | — |
| *Fase 8* | | |
| `StateLoader` | Lector de 7 JSON con TTL cache para el dashboard | `frontend/console/components/state.py` |
| `LogBuffer` | Buffer circular thread-safe (200 líneas) para logs en vivo | `frontend/console/log_handler.py` |
| `Widgets` | 12 funciones Rich renderable (KPIs, tablas, panels, footer) | `frontend/console/components/widgets.py` |
| `Screens` | 5 pantallas: Dashboard, Scanner, Estrategias, Trades, Logs | `frontend/console/screens/` |
| `Commands` | Señales IPC: pause_bot(), resume_bot(), trigger_scanner() | `frontend/console/commands.py` |
| `Console App` | Bucle Rich Live @ 2 FPS con input() para comandos | `frontend/console/app.py` |
| `Loguru Config` | Configuración centralizada de Loguru (3 sinks) | `frontend/console/loguru_config.py` |
| `CLI` | 6 subcomandos: run, status, logs, pause, resume, scanner | `main.py` |

## Comandos

```bash
python -m royaltdn          # Mostrar ayuda con todos los comandos

python -m royaltdn check    # Verificar conexión Alpaca Paper
python -m royaltdn run      # Bot completo + consola interactiva Rich (Fase 8)
python -m royaltdn run-legacy # Bot legacy directo (sin Redis, sin consola)

python -m royaltdn status   # One-shot: mostrar estado actual del bot
python -m royaltdn logs     # One-shot: mostrar últimas 50 líneas de log

python -m royaltdn pause    # Señal IPC: pausar el bot
python -m royaltdn resume   # Señal IPC: reanudar el bot
python -m royaltdn scanner  # Señal IPC: disparar scanner manual
```

### Modo run (recomendado)

Arranca la arquitectura modular completa **más la consola interactiva Rich** en la terminal. El Orchestrator corre en un thread daemon y la consola en el thread principal. Si Redis no está disponible o el thread del `DataIngestor` falla (ej: conflicto de event loop en `alpaca-py`), el `Orchestrator` **detecta automáticamente la muerte del thread** y transiciona a modo legacy:

```bash
# Normal (con Redis + TimescaleDB + consola interactiva)
REDIS_URL=redis://localhost:6379/0 python -m royaltdn run

# Forzar fallback legacy (Redis inválido)
REDIS_URL=redis://noexiste:6379/0 python -m royaltdn run
```

En modo legacy, el risk manager, TWAP, alertas Telegram, **y las estrategias de usuario** siguen activos — solo cambia la fuente de datos (REST polling cada 60s en vez de WebSocket).

### Menú Interactivo (Fase 11)

Al ejecutar `python -m royaltdn run`, se inicia el menú interactivo Rich con **8 opciones** navegables por número:

| Opción | Pantalla | Descripción |
|--------|----------|-------------|
| `1` | Dashboard | KPIs, posiciones, señales, trades, logs con auto-refresh configurable |
| `2` | Scanner | Resultados del escaneo multi-estrategia (badge 🔔 si hay señales nuevas) |
| `3` | Estrategias | Vista unificada predefinidas + usuario con CRUD completo |
| `4` | Trades | Historial con filtros (símbolo + fecha), export CSV/JSON, estadísticas avanzadas |
| `5` | Logs | Logs con filtros por nivel y búsqueda de texto |
| `6` | Control | Pausar/reanudar bot, forzar scanner, configurar alertas de riesgo |
| `7` | Simulación ★ | What-if: modificar riesgo, re-backtest, comparar resultados |
| `8` | Actividad ★ | Registro de acciones del usuario con búsqueda |

**Badges de notificación:** 🔔 señales nuevas, 💰 trades nuevos — aparecen automáticamente en el menú principal.

**Estrategias (opción 3):** CRUD completo — activar/desactivar, editar con precarga, eliminar (usuario), backtest rápido, builder visual de 12 etapas.

**Control (opción 6):** Bot PAUSADO se muestra en amarillo en header + Control + Dashboard. Alertas configurables (drawdown, pérdidas consecutivas).

### One-shot: status y logs

```bash
python -m royaltdn status    # Imprime dashboard una vez y sale
python -m royaltdn logs      # Últimas 50 líneas con syntax highlighting
```

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

# Fase 5-6 (Scanner)
pip install -r requirements/fase6.txt

# Fase 7 (Builder + Backtesting)
pip install -r requirements/fase7.txt

# Fase 8 (Consola Rich + Loguru)
pip install -r requirements/fase8_console.txt

# Variables de entorno (ver .env.example)
export ALPACA_API_KEY="tu_key"
export ALPACA_SECRET_KEY="tu_secret"
export REDIS_URL="redis://localhost:6379/0"    # Opcional — fallback legacy sin Redis
export DATABASE_URL=""                          # Opcional — TimescaleDB

# Ejecutar bot con consola interactiva
python -m royaltdn run

# One-shot status
python -m royaltdn status
```

## Tests

```bash
pytest tests/ -v
```

~80 tests en total cubriendo: SMA, BollingerRSI, MomentumATR, FactorRotation, Scanner, Orchestrator, TCA, indicadores, rule_engine, schema, StrategyStore, DynamicStrategy, backtesting, integración, **StateLoader, LogBuffer, widgets, commands, screens, menú interactivo** (Fases 8-11).

Los tests del menú (`tests/test_menu.py`) cubren:
- StateLoader: carga, cache TTL, archivos faltantes, JSON corrupto
- LogBuffer: add, trim, filtros, thread-safety
- Dashboard: render con datos vacíos y reales
- Builder flow: creación completa de estrategia
- Ctrl+C: salida graceful del menú

## Roadmap

| Fase | Estado | Descripción |
|------|--------|-------------|
| Fase 0-1 | ✅ | Cimientos: estructura, SMA crossover, backtest VectorBT |
| Fase 2 | ✅ | Risk manager, optimización, notebooks |
| Fase 3 | ✅ | Docker, TimescaleDB, Grafana, CI/CD |
| Fase 4 | ✅ | Arquitectura modular: ingestor → Redis → strategy → orchestrator + auto-fallback |
| Fase 5 | ✅ | Scanner multi-estrategia, estrategias avanzadas (BollingerRSI, MomentumATR, FactorRotation) |
| Fase 6 | ✅ | Frontend Streamlit: Dashboard, Scanner, Estrategias, Trades, Logs + status publishing |
| Fase 7 | ✅ | Constructor visual de estrategias: 16 indicadores, reglas lógicas, backtesting, watcher automático |
| **Fase 8** | **✅** | **Consola interactiva Rich: reemplazo de Streamlit por TUI, Loguru, 6 CLI subcomandos, IPC por señales** |
| **Fase 9** | **✅** | **Textual TUI: BuilderScreen + HelpScreen + refactor a Textual** |
| **Fase 10** | **✅** | **Menú texto interactivo: Rich puro sin Textual (compatibilidad Termux)** |
| **Fase 11** | **✅** | **Menú profesional: 15 mejoras + PAUSADO + Simulación + Actividad + Alertas** |
