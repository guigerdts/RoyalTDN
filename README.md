# RoyalTDN — CellMesh Crypto Bot

Bot de trading algorítmico con células componibles para Binance (paper/live). Arquitectura modular, backtesting con datos reales, y optimización automática de parámetros.

**Stack**: Python 3.13 (asyncio), Binance API (WebSocket + REST), TimescaleDB, Grafana, Docker, Loguru, pandas-ta, Optuna.

**Estado**: Producción — 27 estrategias en células sobre 3 timeframes (15m, 1h, 1d). 12 nuevas células SMF Cloud + 3 con Sharpe positivo + 12 heredadas.

---

## Quick start

```bash
# Setup
cp .env.example .env    # Completá BINANCE_API_KEY, BINANCE_SECRET_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Backtest rápido de una estrategia
python -m src.royaltdn.scripts.run_backtest --strategy scalping_reversion

# Optimizar una estrategia
python -m src.royaltdn.scripts.optimize --strategy swing_momentum --trials 25

# Arrancar el bot (paper mode por defecto)
python -m src.royaltdn.main

# Con optimización periódica automática
python -m src.royaltdn.main --optimize
```

---

## Arquitectura: CellMesh

```
                    ┌─────────────────────────────────────┐
                    │            BinanceFeed              │
                    │  WebSocket (candles+trades) + REST  │
                    └──────────────┬──────────────────────┘
                                   │  OHLCV bars
                                   ▼
              ┌──────────────────────────────────────┐
              │             EventBus                  │
              │      publish → subscriber fan-out     │
              └──────┬───────────────────────────────┘
                     │
         ┌───────────┼───────────┬───────────────────┐
         ▼           ▼           ▼                   ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐    ┌──────────────┐
   │  Cell 1  │ │  Cell 2  │ │  Cell 3  │ …  │  Cell N      │
   │ scalping │ │  swing   │ │ intraday │    │  user-defined │
   │_reversion│ │_momentum │ │_trend    │    │  (hot-reload) │
   └────┬─────┘ └────┬─────┘ └────┬─────┘    └──────┬───────┘
        │            │            │                  │
        └───────┬────┴────────────┴──────────────────┘
                ▼
        ┌──────────────────┐
        │  InferenceEngine  │  ──  eval condition graph
        └────────┬─────────┘
                 ▼ signal
        ┌──────────────────┐
        │   RiskManager    │  ──  sizing, drawdown, max positions
        └────────┬─────────┘
                 ▼ order
        ┌──────────────────┐
        │    Broker        │  ──  Binance | PaperBroker
        │  + OrderManager  │  ──  fill tracking, reconciliation
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │  TradeTracker    │  ──  journal, metrics, Telegram alerts
        │  + Journal       │
        │  + Dashboard     │
        └──────────────────┘
```

### Componentes clave

| Módulo | Rol | Archivo |
|--------|-----|---------|
| `EventBus` | Pub/sub asíncrono (bar → cells) | `core/bus.py` |
| `EventEngine` | Orquesta cells, risk, broker, journal | `core/engine.py` |
| `BinanceFeed` | WebSocket (@kline_1m) + REST para datos en vivo | `data/binance_feed.py` |
| `InferenceEngine` | Evalúa árboles de condiciones (AND/OR) | `inference/engine.py` |
| `Cell` | Condiciones de entrada/salida + risk por célula | `cells/base.py` |
| `CellLoader` | Carga células desde YAML templates | `cells/loader.py` |
| `HotReloader` | Detecta cambios en células sin reiniciar | `core/hot_reload.py` |
| `RiskManager` | Position sizing, drawdown kill switch | `risk/manager.py` |
| `Portfolio` | Seguimiento de capital, P&L, drawdown | `risk/portfolio.py` |
| `PaperBroker` | Simulación de órdenes sin capital real | `execution/paper_broker.py` |
| `BinanceBroker` | Órdenes reales + reconciliación | `execution/binance_broker.py` |
| `TradeTracker` | Métricas por cell (win rate, sharpe) | `core/trade_tracker.py` |
| `KillSwitch` | Parada de emergencia automática | `execution/kill_switch.py` |
| `Dashboard` | Monitoreo en tiempo real (asyncio) | `monitoring/dashboard.py` |
| `TelegramAlerts` | Alertas configurables vía Telegram | `monitoring/telegram_alerts.py` |

---

## Estrategias: 3 timeframes, 27 células

Las células se definen en YAML y se cargan en caliente. 16 indicadores base + 4 indicadores SMF Cloud (pandas-ta + indicadores manuales como Support/Resistance y MACD Divergence).

### SMF Cloud Indicators (v2)

4 indicadores de flujo monetario institucional que reemplazan las 12 estrategias sin edge:

| Indicador | Rol |
|-----------|-----|
| `smf_flow` | Dirección y fuerza del flujo monetario (+/−) |
| `smf_strength` | Intensidad normalizada del flujo (0..1) |
| `smf_basis` | Precio de equilibrio institucional |
| `smf_signal` | Señal discreta de entrada/salida |

Cada indicador produce 4 células (trend, momentum, reversion, retest) en cada timeframe: **12 células SMF Cloud** corriendo sobre BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT, LINKUSDT.

### Resultados de optimización (equity-curve Sharpe)

Tras ~100 trials de Optuna por estrategia con métrica real de equity curve:

```
✅ scalping_reversion     1m  ETH  Sharpe 6.67    ← edge sólido
✅ swing_reversion        1d  BTC  Sharpe 0.62    ← edge leve
✅ swing_momentum         1d  ADA  Sharpe 0.41    ← modesto

❌ 12 estrategias heredadas — sin edge (reemplazadas por SMF Cloud)
✅ 12 SMF Cloud cells       —   —   en validación (bot test 06/2026: 44 cells,
                              9 señales SMF en 3.5 min, 0 errores)
```

### Gestión de salidas (exits)

Cada célula SMF tiene dos capas de salida:

1. **Porcentaje fijo** — stop-loss, take-profit y trailing-stop con valores específicos por timeframe:
   - Swing (1d): SL 2-3%, TP 3-5%, TS 2% (trend) / SL 2%, TP 3% (reversion)
   - Intraday (1h): SL 1-1.5%, TP 2-2.5%, TS 1% (trend) / SL 1%, TP 2% (reversion)
   - Scalping (15m): SL 0.6-0.8%, TP 1.2-1.5%, TS 0.5% (trend) / SL 0.6%, TP 1.2% (reversion)

2. **ATR adaptativo** — trailing_stop con `atr_multiplier: 2.0` y stop_loss con `atr_multiplier: 3.0`

Las salidas porcentuales se evalúan primero (sin requerir ATR). Si no se activan, se evalúan las ATR.

### Paleta de indicadores

| Indicador | Parámetros |
|-----------|------------|
| RSI | period |
| EMA | period |
| ADX | period, operator_threshold |
| Bollinger (lower/upper) | period, std |
| Momentum | period |
| MACD Divergence | fast, slow, signal, lookback |
| Support/Resistance | lookback, touch_count, side |
| Range Breakout | period, factor |
| Volume Surge | period, factor |
| ATR | period, max_pct |
| VWAP / VWAP Deviation | period, factor |
| Z-Score | period |
| Ichimoku | tenkan, kijun, senkou_b |
| Spread | max_spread_pct |
| **SMF Flow** | — Flujo monetario acumulado |
| **SMF Strength** | — Intensidad normalizada (0..1) |
| **SMF Basis** | — Precio de equilibrio |
| **SMF Signal** | — Señal discreta (+1/−1/0) |

### Archivos de configuración

| Archivo | Timeframe | Estrategias |
|---------|-----------|-------------|
| `cells/templates/scalping.yaml` | 15m | scalping_reversion, **scalping_smf_retest_rsi**, **scalping_smf_momentum**, **scalping_smf_breakout**, **scalping_smf_reversion** |
| `cells/templates/intraday.yaml` | 1h | intraday_volume_breakout, **intraday_smf_trend_adx**, **intraday_smf_retest_bollinger**, **intraday_smf_momentum_volume**, **intraday_smf_zscore_reversion** |
| `cells/templates/swing.yaml` | 1d | **swing_reversion**, **swing_momentum**, **swing_smf_trend_bollinger**, **swing_smf_momentum_adx**, **swing_smf_reversion_zscore**, **swing_smf_retest_rsi** |

---

## Backtesting y Optimización

### Backtest rápido (`run_backtest.py`)

```bash
# Estrategia individual con símbolo y timeframe por defecto
python -m src.royaltdn.scripts.run_backtest --strategy scalping_reversion

# Forzar símbolo y timeframe
python -m src.royaltdn.scripts.run_backtest --strategy swing_momentum --symbol SOLUSDT --timeframe 1d

# Control de drawdown (por defecto 50% para backtesting)
python -m src.royaltdn.scripts.run_backtest --strategy scalping_reversion --max-drawdown 0.1
```

Métricas que reporta:
- **Sharpe** (equity curve, anualizado por √bars_per_year)
- **Win Rate, Profit Factor**
- **Max Drawdown**
- **Total Return, Total Trades**
- **Ganancias por símbolo** (multi-symbol)

### Optimización (`optimize.py`)

```bash
# Optimizar una estrategia con Optuna
python -m src.royaltdn.scripts.optimize --strategy scalping_reversion --trials 100

# Optimizar todas las estrategias
python -m src.royaltdn.scripts.optimize --strategy all --trials 25

# Output: guarda los mejores parámetros en el YAML correspondiente
```

- 25–100 trials con TPE sampler
- Parámetros optimizados: entry conditions, stop loss, take profit, trailing stop, sizing, max positions
- Multi-símbolo: optimiza sobre el promedio de todos los símbolos configurados

### Backtest completo (`backtest.py`)

```bash
python -m src.royaltdn.scripts.backtest --strategies scalping.yaml --start 2025-01-01 --end 2026-06-01
```

---

## Monitoreo

### Dashboard en terminal (Loguru + asyncio)

El bot corre en background con logging estructurado a `logs/trading.log`. El dashboard muestra en tiempo real:

- Equity, P&L, drawdown
- Posiciones abiertas
- Señales generadas por cada cell
- Alertas vía Telegram (opcional)

### Grafana (TimescaleDB)

Si TimescaleDB está configurado, las métricas se persisten y Grafana las visualiza:

```bash
docker-compose up -d timescaledb grafana
```

---

## Configuración

### Variables de entorno (`.env`)

| Variable | Obligatoria | Default |
|----------|-------------|---------|
| `BINANCE_API_KEY` | Sí (live) | — |
| `BINANCE_SECRET_KEY` | Sí (live) | — |
| `BINANCE_PRIVATE_KEY` | No | — |
| `TELEGRAM_BOT_TOKEN` | No | — |
| `TELEGRAM_CHAT_ID` | No | — |
| `DATABASE_URL` | No | — |

### Modos de broker

| Modo | Config | Ejecución |
|------|--------|-----------|
| **Paper** | `broker: paper` (default) | Simulación, sin capital real |
| **Binance Testnet** | `broker: binance` + `testnet: true` | Órdenes contra sandbox |
| **Binance Live** | `broker: binance` + `testnet: false` | Capital real |

Ver `src/royaltdn/config.yaml` para configuración completa.

---

## Tests

```bash
pytest tests/ -v
```

Cobertura: backtesting, optimización, risk manager, journal, indicators, inference engine, cell loader, hot reload.

---

## Roadmap

| Fase | Estado | Descripción |
|------|--------|-------------|
| CellMesh core | ✅ | EventBus, EventEngine, BinanceFeed, RiskManager, brokers |
| Templates YAML | ✅ | 15 células en 3 timeframes |
| Backtesting | ✅ | run_backtest.py con métricas reales |
| Optimización | ✅ | Optimiza.py con Optuna, equity-curve Sharpe |
| Hot reload | ✅ | Carga en caliente de células modificadas |
| Dashboard + Telegram | ✅ | Monitoreo en tiempo real con alertas |
| SMF Cloud Indicators | ✅ | 4 indicadores institucionales + 12 células en 3 timeframes |
| **Estrategias con edge** | **🔶** | **3 heredadas + 12 SMF Cloud en validación (bot test OK 06/2026)** |
| Gestión de riesgo real | 🔶 | Position sizing por ATR, drawdown kill switch |
| Live trading Binance | 🔶 | Paper funcionando, live en validación |
