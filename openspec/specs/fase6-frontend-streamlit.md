# Spec: Fase 6 — Frontend Streamlit

## Purpose

Define los contratos, estructuras de datos y comportamientos para añadir un frontend Streamlit a RoyalTDN. El frontend se comunica exclusivamente mediante archivos JSON en `logs/`, escritos atómicamente por el orquestador y el scanner. La especificación cubre: formatos de archivo, escritura atómica, páginas del frontend, modificaciones al orquestador, manejo de errores y criterios de aceptación.

---

## 1. JSON File Contracts

### 1.1 `logs/status.json`

**Purpose**: Estado global del bot — online/offline, modo, errores, uptime.
**Update frequency**: Cada ciclo legacy (~60s) + on startup + on shutdown.
**Write mode**: Overwrite (siempre).
**Written by**: `Orchestrator._publish_status()`.

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `bot_status` | string | REQUIRED | Estado del bot: `ONLINE`, `OFFLINE`, `KILLED` | `"ONLINE"` |
| `mode` | string | REQUIRED | Modo de operación: `"legacy"` o `"modular"` | `"legacy"` |
| `timestamp` | string (ISO 8601) | REQUIRED | Momento de la publicación | `"2026-06-16T10:30:00Z"` |
| `last_signal` | object or null | OPTIONAL | Última señal generada (ver schema anidado) | `{"action": "BUY", "price": 450.20, "symbol": "SPY", "timestamp": "..."}` |
| `last_error` | string or null | OPTIONAL | Último error registrado, o `null` si no hay | `null` |
| `uptime_seconds` | number | REQUIRED | Segundos desde que el bot inició | `3600` |
| `symbols` | array[string] | REQUIRED | Símbolos que el bot monitorea | `["SPY", "QQQ"]` |
| `scanner_enabled` | boolean | REQUIRED | `true` si el scanner está inicializado | `true` |
| `version` | string | OPTIONAL | Versión del bot | `"1.0.0"` |

**Schema anidado — `last_signal`**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `action` | string | REQUIRED | `"BUY"`, `"SELL"`, o `"RANK"` | `"BUY"` |
| `price` | number | REQUIRED | Precio de la señal | `450.20` |
| `symbol` | string | REQUIRED | Símbolo asociado | `"SPY"` |
| `strategy` | string | OPTIONAL | Estrategia que generó la señal | `"sma_crossover"` |
| `timestamp` | string | REQUIRED | ISO 8601 | `"2026-06-16T10:00:00Z"` |
| `metadata` | object | OPTIONAL | Datos adicionales de la estrategia | `{"fast_sma": 448.5}` |

**Edge cases**:

| Condición | Comportamiento del frontend |
|-----------|----------------------------|
| File missing | Dashboard muestra "Waiting for bot to start..." con spinner |
| File empty | Se logea warning, status indicator se muestra como OFFLINE |
| File corrupt (invalid JSON) | Se logea error, se muestra "Status unavailable — corrupt file" |
| File stale (>5 min desde `timestamp`) | Status badge se muestra como "STALE" (amarillo), se marca visualmente |
| `bot_status` unrecognized value | Default a OFFLINE, se logea advertencia |
| `last_error` is string no null | Se muestra badge de error rojo con tooltip del mensaje |

---

### 1.2 `logs/equity.json`

**Purpose**: Datos de capital, P&L, drawdown y curva de equity histórica.
**Update frequency**: Cada ciclo legacy (~60s).
**Write mode**: Overwrite.
**Written by**: `Orchestrator._publish_status()`.

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `initial_equity` | number | REQUIRED | Capital inicial al arrancar el bot | `100000.00` |
| `current_equity` | number | REQUIRED | Capital actual desde Alpaca | `101234.50` |
| `pnl_day` | number | REQUIRED | P&L del día en USD | `1234.50` |
| `pnl_day_pct` | number | REQUIRED | P&L del día en porcentaje | `1.23` |
| `drawdown` | number | REQUIRED | Drawdown máximo actual en USD (negativo o cero) | `-500.00` |
| `drawdown_pct` | number | REQUIRED | Drawdown máximo actual en % (negativo o cero) | `-0.50` |
| `sharpe` | number | OPTIONAL | Ratio de Sharpe (anualizado) | `1.45` |
| `equity_curve` | array[object] | REQUIRED | Array de puntos de equity históricos | `[{"timestamp":"...","equity":100500.00}]` |
| `updated_at` | string (ISO 8601) | REQUIRED | Última actualización | `"2026-06-16T10:30:00Z"` |
| `stale` | boolean | OPTIONAL | `true` si equity no pudo obtenerse de Alpaca y se usó último valor conocido | `false` |

**Schema anidado — `equity_curve[]`**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `timestamp` | string (ISO 8601) | REQUIRED | Momento del punto de equity | `"2026-06-16T10:30:00Z"` |
| `equity` | number | REQUIRED | Valor de equity en ese momento | `100800.00` |

**Edge cases**:

| Condición | Comportamiento del frontend |
|-----------|----------------------------|
| File missing | Dashboard muestra "Waiting for data..." con spinner en cards de equity |
| `stale: true` | Se muestra badge "⚠️ Stale" junto al valor de capital |
| `equity_curve` vacío | Equity chart muestra "No equity data yet" |
| `equity_curve` con 1 solo punto | Línea horizontal sin variación |
| `pnl_day_pct` no presente | Se calcula a partir de `pnl_day` y `current_equity` si es posible |
| `sharpe` ausente | Card de Sharpe muestra "—" (em dash) |

---

### 1.3 `logs/positions.json`

**Purpose**: Posiciones abiertas actuales en el broker.
**Update frequency**: Cada ciclo legacy (~60s).
**Write mode**: Overwrite.
**Written by**: `Orchestrator._publish_status()`.

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `open_positions` | array[object] | REQUIRED | Lista de posiciones abiertas | `[{"symbol":"SPY","side":"long",...}]` |
| `total_open` | number | REQUIRED | Cantidad de posiciones abiertas (debe coincidir con `len(open_positions)`) | `1` |
| `updated_at` | string (ISO 8601) | REQUIRED | Última actualización | `"2026-06-16T10:30:00Z"` |

**Schema anidado — `open_positions[]`**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `symbol` | string | REQUIRED | Ticker | `"SPY"` |
| `side` | string | REQUIRED | `"long"` o `"short"` | `"long"` |
| `qty` | number | REQUIRED | Cantidad de acciones/contratos | `100` |
| `entry_price` | number | REQUIRED | Precio de entrada promedio | `445.00` |
| `current_price` | number | REQUIRED | Precio de mercado actual | `450.20` |
| `pnl_unrealized` | number | REQUIRED | P&L no realizado en USD | `520.00` |
| `entry_at` | string (ISO 8601) | REQUIRED | Timestamp de entrada | `"2026-06-16T09:30:00Z"` |
| `strategy` | string | OPTIONAL | Estrategia que abrió la posición | `"sma_crossover"` |

**Edge cases**:

| Condición | Comportamiento del frontend |
|-----------|----------------------------|
| File missing | Tabla de posiciones muestra "No position data available" |
| `open_positions` vacío | Tabla vacía con "No open positions" |
| `total_open` mismatch con `len(open_positions)` | Se confía en el array, se logea warning |
| `current_price` igual a `entry_price` | P&L muestra $0.00 |
| Duración no calculable | Duration muestra "—" cuando `entry_at` no está disponible |

---

### 1.4 `logs/signals.json`

**Purpose**: Señales generadas hoy por las estrategias.
**Update frequency**: Cada ciclo legacy (~60s).
**Write mode**: Overwrite.
**Written by**: `Orchestrator._publish_status()`.

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `today_count` | number | REQUIRED | Total de señales generadas hoy | `3` |
| `last_signals` | array[object] | REQUIRED | Últimas N señales (máx 20) | `[{"action":"BUY","symbol":"SPY",...}]` |
| `updated_at` | string (ISO 8601) | REQUIRED | Última actualización | `"2026-06-16T10:30:00Z"` |

**Schema anidado — `last_signals[]`**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `action` | string | REQUIRED | `"BUY"`, `"SELL"`, o `"RANK"` | `"BUY"` |
| `symbol` | string | REQUIRED | Ticker | `"SPY"` |
| `price` | number | REQUIRED | Precio de referencia | `450.20` |
| `strategy` | string | REQUIRED | Nombre de la estrategia | `"sma_crossover"` |
| `timestamp` | string (ISO 8601) | REQUIRED | Momento de la señal | `"2026-06-16T10:00:00Z"` |
| `metadata` | object | OPTIONAL | Datos adicionales | `{"fast_sma": 448.5, "slow_sma": 447.2}` |

**Edge cases**:

| Condición | Comportamiento del frontend |
|-----------|----------------------------|
| File missing | Signals section muestra "No signals generated yet" |
| `last_signals` vacío | Card de Signals Today muestra 0, tabla vacía |
| `action` no reconocido | Row se muestra con color gris por defecto |
| `metadata` faltante | Se omite columna expandible de detalles |

---

### 1.5 `logs/scanner_results.json`

**Purpose**: Resultados del último escaneo multi-estrategia del scanner.
**Update frequency**: En cada ejecución del scanner (~60 min).
**Write mode**: Overwrite.
**Written by**: `Scanner.scan()` — debe llamar a `_atomic_write()`.

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `scan_timestamp` | string (ISO 8601) | REQUIRED | Momento del escaneo | `"2026-06-16T10:00:00Z"` |
| `symbols_scanned` | number | REQUIRED | Símbolos evaluados | `100` |
| `symbols_passed` | number | REQUIRED | Símbolos que pasaron filtro de liquidez | `45` |
| `total_signals` | number | REQUIRED | Total de señales generadas | `12` |
| `top_signals` | array[object] | REQUIRED | Top N señales rankeadas | `[{"symbol":"XLK","strategy":"factor_rotation",...}]` |
| `history` | array[object] | OPTIONAL | Historial de últimos 10 escaneos | `[{"scan_timestamp":"...","total_signals":12}]` |
| `updated_at` | string (ISO 8601) | REQUIRED | Última actualización | `"2026-06-16T10:30:00Z"` |

**Schema anidado — `top_signals[]`**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `symbol` | string | REQUIRED | Ticker | `"XLK"` |
| `strategy` | string | REQUIRED | Estrategia que generó la señal | `"factor_rotation"` |
| `action` | string | REQUIRED | `"BUY"`, `"SELL"`, o `"RANK"` | `"RANK"` |
| `price` | number | REQUIRED | Precio de referencia | `180.50` |
| `score` | number or null | OPTIONAL | Score numérico (solo FactorRotation) | `2.34` |
| `metadata` | object | OPTIONAL | Datos adicionales | `{"momentum": 15.2, "volatility": 6.5}` |

**Edge cases**:

| Condición | Comportamiento del frontend |
|-----------|----------------------------|
| File missing | Scanner page muestra "Scanner not initialized or no scan completed yet" |
| `top_signals` vacío | Tabla vacía, distribución chart sin datos |
| `history` ausente | History table no se renderiza |
| `score` null o ausente | Columna score muestra "—" |

---

### 1.6 `logs/strategies.json`

**Purpose**: Configuración y estado de cada estrategia cargada.
**Update frequency**: Cada ciclo legacy (~60s).
**Write mode**: Overwrite.
**Written by**: `Orchestrator._publish_status()`.

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `strategies` | array[object] | REQUIRED | Lista de estrategias | `[{"name":"sma_crossover","active":true,...}]` |
| `updated_at` | string (ISO 8601) | REQUIRED | Última actualización | `"2026-06-16T10:30:00Z"` |

**Schema anidado — `strategies[]`**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `name` | string | REQUIRED | Nombre único de la estrategia | `"sma_crossover"` |
| `active` | boolean | REQUIRED | `true` si está activa | `true` |
| `params` | object | REQUIRED | Parámetros de configuración | `{"fast_period": 5, "slow_period": 20}` |
| `validation` | boolean | REQUIRED | `true` si pasó validación | `true` |
| `last_signal` | string or null | OPTIONAL | Última acción generada: `"BUY"`, `"SELL"`, o `null` | `"BUY"` |
| `signal_count` | number | REQUIRED | Total de señales generadas por esta estrategia | `15` |
| `symbol` | string | REQUIRED | Símbolo asignado a la estrategia | `"SPY"` |
| `timeframe` | string | OPTIONAL | Resolución de la estrategia | `"1d"` |

**Edge cases**:

| Condición | Comportamiento del frontend |
|-----------|----------------------------|
| File missing | Estrategias page muestra "No strategies loaded" |
| `strategies` vacío | Misma pantalla que file missing |
| `params` vacío | Tabla de params muestra "No parameters" |
| `last_signal` null | Badge de última señal muestra "—" |

---

### 1.7 `logs/trades.json`

**Purpose**: Historial completo de trades ejecutados.
**Update frequency**: En cada cierre de trade (evento).
**Write mode**: Append — se lee el array existente, se añade, se escribe completo.
**Written by**: `Orchestrator._append_trade()`.

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `total_trades` | number | REQUIRED | Conteo total de trades | `42` |
| `win_rate` | number | OPTIONAL | Porcentaje de trades ganadores (0-100) | `64.3` |
| `profit_factor` | number | OPTIONAL | Ratio ganancia/pérdida | `2.1` |
| `total_pnl` | number | OPTIONAL | P&L total acumulado en USD | `1234.50` |
| `trades` | array[object] | REQUIRED | Lista de trades ejecutados | `[{"symbol":"SPY","side":"long",...}]` |
| `updated_at` | string (ISO 8601) | REQUIRED | Última actualización | `"2026-06-16T10:30:00Z"` |

**Schema anidado — `trades[]`**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `symbol` | string | REQUIRED | Ticker | `"SPY"` |
| `side` | string | REQUIRED | `"long"` o `"short"` | `"long"` |
| `entry_price` | number | REQUIRED | Precio de entrada | `445.00` |
| `exit_price` | number | REQUIRED | Precio de salida | `450.20` |
| `qty` | number | REQUIRED | Cantidad de acciones | `100` |
| `pnl` | number | REQUIRED | P&L realizado en USD | `520.00` |
| `entry_at` | string (ISO 8601) | REQUIRED | Timestamp de entrada | `"2026-06-16T09:30:00Z"` |
| `exit_at` | string (ISO 8601) | REQUIRED | Timestamp de salida | `"2026-06-16T10:00:00Z"` |
| `strategy` | string | REQUIRED | Estrategia que generó la señal | `"sma_crossover"` |
| `slippage_bps` | number or null | OPTIONAL | Slippage en basis points | `0.5` |
| `execution_method` | string | OPTIONAL | `"market"` o `"twap"` | `"market"` |
| `entry_order_id` | string or null | OPTIONAL | ID de la orden de entrada | `"abc123"` |
| `exit_order_id` | string or null | OPTIONAL | ID de la orden de salida | `"def456"` |

**Edge cases**:

| Condición | Comportamiento del frontend |
|-----------|----------------------------|
| File missing | Trades page muestra "No trades executed this session" |
| `trades` vacío | Misma pantalla que file missing |
| `win_rate`, `profit_factor`, `total_pnl` no presentes | Se calculan a partir del array `trades` en el frontend |
| `slippage_bps` null | Columna slippage muestra "—" |
| Archivo crece demasiado (>1000 trades) | Frontend mantiene en memoria solo últimos 200 para display, cálculos sobre todos |
| Trade con `pnl` positivo pero `exit_price < entry_price` (short) | Win/loss se determina por signo de `pnl`, no por precio |

---

## 2. Atomic Write Contract

### 2.1 `_atomic_write(path, data)` Function

**Signature**:
```python
def _atomic_write(path: Path, data: dict) -> bool
```

**Input**:
- `path: Path` — Ruta absoluta o relativa al archivo destino (ej. `Path("logs/status.json")`)
- `data: dict` — Diccionario Python serializable a JSON

**Process**:
1. Serializar `data` a JSON string con `json.dumps(data, indent=2, default=str)`
2. Escribir a `path.with_suffix(".tmp")` (archivo temporal en el mismo filesystem)
3. Llamar `os.replace(tmp_path, path)` — atómico en Linux cuando source y destination están en el mismo filesystem
4. Retornar `True` en éxito, `False` en error

**Guarantees**:
- El archivo destino NUNCA contiene JSON parcial — o contiene los datos viejos o los nuevos completos
- `os.replace()` es atómica en Linux (rename syscall sobre mismo filesystem): no hay ventana donde otro proceso lea un archivo truncado o parcial
- El `.tmp` file se escribe primero para que, si el proceso se corta durante la escritura, el destino quede intacto

**Error handling**:
| Error | Comportamiento |
|-------|---------------|
| `PermissionError` | Log `logger.warning("Permission denied writing %s", path)`, retorna `False` |
| `OSError: [ENOSPC]` (disk full) | Log `logger.error("Disk full — cannot write %s", path)`, retorna `False`, archivo anterior preservado |
| `TypeError` (non-serializable) | Log `logger.error("Non-serializable data for %s: %s", path, e)`, retorna `False` |
| Cualquier otra excepción | Log `logger.warning("Error writing %s: %s", path, e)`, retorna `False` |

**Edge cases**:
- `.tmp` file ya existe de escritura previa fallida → `os.replace` lo sobrescribe
- Path es directorio → `PermissionError` capturado por handler genérico
- `data` contiene `datetime` objects → `default=str` los serializa a ISO 8601
- Contenido idéntico al anterior → se escribe igual, no hay optimización de skip

---

## 3. Frontend Pages — Detailed Specs

### 3.1 📊 Dashboard (`pages/dashboard.py`)

**Layout (top-to-bottom)**:
1. **Top row**: 6 metric cards in `st.columns(6)`, each with label, value, optional delta
2. **Second row**: Two columns side by side — equity curve chart (Plotly line) | drawdown chart (Plotly filled area)
3. **Third row**: Open positions table (`st.dataframe`)
4. **Bottom**: Bot status indicator box

**Metric cards** (6 cards, each in `st.container` with `st.metric` or custom HTML):

| Card | Data Source | Format | Empty State |
|------|------------|--------|-------------|
| Capital ($) | `equity.json` → `current_equity` | `$123,456.78` | "—" |
| P&L Day ($) | `equity.json` → `pnl_day` | `+$1,234.50` / `-$500.00` (green/red) | "—" |
| P&L Day (%) | `equity.json` → `pnl_day_pct` | `+1.23%` / `-0.50%` (green/red) | "—" |
| Drawdown (%) | `equity.json` → `drawdown_pct` | `-0.50%` (siempre rojo) | "—" |
| Open Positions | `positions.json` → `total_open` | `3` | `0` |
| Signals Today | `signals.json` → `today_count` | `7` | `0` |
| Sharpe Ratio | `equity.json` → `sharpe` | `1.45` | "—" |

**Equity curve**:
- Plotly scatter+line chart: `px.line(x=timestamps, y=equity_values, ...)`
- X-axis: `timestamp` from `equity_curve[]` (formatted as date)
- Y-axis: `equity` value with `$` prefix
- Hover tooltip: `$xxx,xxx.xx` at `HH:MM`
- Empty: central annotation "No equity data yet"
- Single point: horizontal line at that value

**Drawdown chart**:
- Plotly filled area: `px.area(x=timestamps, y=drawdown_values, ...)`
- Calculated from equity_curve: `drawdown = (equity - peak) / peak * 100`
- Color: red gradient fill
- Y-axis: percentage (0 to -max_drawdown)
- Empty: "No drawdown data"

**Open positions table**:
- Columns: Symbol, Side (↗/↘ icon), Qty, Entry Price, Current Price, Unrealized P&L (color-coded), Duration
- Duration calculated from `entry_at` to now (format: `Xh Ym` or `Xm Ys`)
- Row color: green tint if P&L > 0, red tint if < 0
- Empty: Empty dataframe with "No open positions"

**Bot status**:
- `st.container` with colored border/background:
  - `ONLINE` → green background, "● ONLINE" text
  - `OFFLINE` → red background, "● OFFLINE" text
  - `KILLED` → orange background, "● KILLED" text
- Mode badge: "legacy" or "modular" next to status
- Last signal time: from `status.json` → `last_signal.timestamp`
- Last error: if `status.json` → `last_error` is not null, show red error box
- Stale indicator: if `status.json` is stale (>5 min), show yellow "⚠️ STALE" badge

**Auto-refresh**: `st.rerun` every 3 seconds via `time.sleep(3)` at end of render function, wrapped in `if "stop_auto_refresh" not in st.session_state`.

**Empty states**: 
- All files missing → "Waiting for bot to start..." with `st.spinner`
- Partial missing → Individual empty states per section

---

### 3.2 🔍 Scanner (`pages/scanner.py`)

**Layout**:
1. Config/settings section at top (expander or sidebar)
2. Signals table with colored rows
3. Distribution bar chart
4. Scan history table

**Config selector**:
- `st.selectbox` for universe: `["etfs", "sp500", "all"]`
- `st.checkbox` per strategy (from `strategies.json` names)
- `st.number_input` for top N signals (1-20, default `SCANNER_TOP_N`)
- *Note*: These are visual-only filters. Actual config is set via env vars, displayed only.

**Signals table**:
- `st.dataframe` with columns: Symbol, Strategy, Action, Price, Score, Metadata
- Color coding via `st.dataframe` column config or `pd.Styler`:
  - `BUY` → green background row
  - `SELL` → red background row
  - `RANK` → blue background row
- Sortable by Score descending (default)

**Distribution chart**:
- Plotly bar chart: `px.bar(x=strategy_names, y=signal_counts)`
- One bar per strategy, height = number of signals from that strategy
- Color by action type (BUY=green, SELL=red, RANK=blue) as stacked bars

**Scan history**:
- `st.dataframe` with columns: Scan Time, Scanned, Passed, Signals
- Sorted descending by `scan_timestamp`
- Shows last 10 entries from `history` array

**Auto-refresh**: Every 5 seconds.

**Empty state**: "Scanner not initialized or no scan completed yet" with `st.info`.

---

### 3.3 ⚙️ Estrategias (`pages/estrategias.py`)

**Layout**:
1. Each strategy as `st.expander`
2. Inside expander: params table, validation icon, last signal, signal count

**Per strategy**:
- Expander title: `{name}` + active badge ("🟢 ACTIVE" / "🔴 INACTIVE")
- Inside:
  - Params table: `st.dataframe(params_dict.items())` — key | value rows
  - Validation: ✅ if `validation: true`, ❌ if `false`
  - Last signal: badge or text showing last action
  - Signal count: numeric display
  - Symbol: the symbol assigned

**Toggle**: `st.checkbox` per strategy to mark active/inactive — **visual only**, does NOT affect bot behavior. State stored in `st.session_state`.

**Empty state**: "No strategies loaded" with `st.warning`.

**Auto-refresh**: Every 5 seconds.

---

### 3.4 📈 Trades (`pages/trades.py`)

**Layout**:
1. Filters bar (top): date range, symbol, strategy, result radio
2. Summary metrics row
3. Trade table
4. P&L chart (bar)
5. Distribution histogram
6. CSV download button

**Filters**:
- `st.date_input` for date range (start, end) — defaults to last 30 days
- `st.selectbox` for symbol filter — "All" or specific from trades
- `st.selectbox` for strategy filter — "All" or specific from trades
- `st.radio` for result: `["All", "Wins", "Losses"]`
- Filters apply to ALL data displays (table, charts, metrics, CSV)

**Summary metrics** (calculated from filtered trades):

| Metric | Formula | Example |
|--------|---------|---------|
| Total Trades | `len(trades)` | `42` |
| Win Rate % | `wins / total * 100` | `64.3%` |
| Profit Factor | `gross_profit / abs(gross_loss)` | `2.10` |
| Total P&L | `sum(pnl)` | `$1,234.50` |
| Avg P&L | `mean(pnl)` | `$29.39` |
| Best Trade | `max(pnl)` | `$520.00` |
| Worst Trade | `min(pnl)` | `-$150.00` |

**Trade table**:
- `st.dataframe` with all columns: Symbol, Side, Entry Price, Exit Price, Qty, P&L, Entry At, Exit At, Strategy, Slippage, Method
- Paginated: show last 200 rows by default, with `st.selectbox` to toggle between 50/100/200
- Sortable by exit date descending (default)
- P&L column: green text for positive, red for negative

**P&L chart**:
- Plotly bar chart: `px.bar(x=trade_index, y=pnl)`
- Green bars for positive P&L, red bars for negative
- X-axis: trade index or exit date
- Y-axis: P&L in USD
- Hover: shows symbol, P&L, dates

**Distribution histogram**:
- Plotly histogram: `px.histogram(x=pnl_values, nbins=20)`
- Overlay with normal distribution curve
- X-axis: P&L buckets, Y-axis: frequency

**CSV export**:
- `st.download_button` with label "📥 Download CSV"
- Generates CSV from currently filtered trades
- Filename: `trades_export_{YYYYMMDD}.csv`
- Uses `pandas.DataFrame.to_csv(index=False)`
- Columns: all trade fields

**Auto-refresh**: Every 5 seconds.

**Empty state**: "No trades executed this session" with `st.info`.

---

### 3.5 📋 Logs (`pages/logs.py`)

**Layout**:
1. Filter row (top): level checkboxes, module input, search input, clear button
2. Log viewer container

**Log viewer**:
- `st.empty` container updated each cycle
- Reads last N lines from `logs/bot.log` using `collections.deque` (maxlen=1000)
- Renders as `st.text_area` (read-only) or custom monospace `st.markdown` block
- Auto-scroll to bottom via CSS/JS or by rendering log line count

**Filters**:
- `st.checkbox` for each level: DEBUG, INFO, WARNING, ERROR — all enabled by default
- `st.text_input` for module filter — filters log line by module name (case-insensitive substring match)
- `st.text_input` for search text — filters log line content (case-insensitive substring match)
- Filters apply client-side in Streamlit session state

**Clear button**:
- `st.button` "🗑 Clear" — clears session state log buffer (visual only, does NOT delete log file)

**Reading logic**:
```python
log_path = Path("logs/bot.log")
if log_path.exists():
    with open(log_path, "r") as f:
        # Use deque for efficient tail reading
        from collections import deque
        lines = deque(f, maxlen=1000)
    # Apply filters
    ...
else:
    st.info("Log file not found at logs/bot.log")
```

**Auto-refresh**: Every 2 seconds.

**Edge cases**:

| Condición | Comportamiento |
|-----------|---------------|
| Log file missing | `st.info("Log file not found at logs/bot.log")` |
| Log file > 10MB (muy grande) | Lee solo últimas 1000 líneas via `deque(f, maxlen=1000)` |
| Log file no tiene permisos de lectura | `st.error("Permission denied reading logs/bot.log")` |
| No lines match filters | `st.caption("No log lines match the current filters")` |
| Todos los checkboxes desactivados | "No log levels selected" |
| Character encoding issues | `encoding="utf-8", errors="replace"` |

---

## 4. Orchestrator Modifications Contract

### 4.1 `_get_current_equity() -> float`

**Signature**:
```python
def _get_current_equity(self) -> float
```

**Behavior**:
1. Llama a `self._trading.get_account()` — método sincrónico del TradingClient de Alpaca
2. Retorna `float(account.equity)` como float
3. Cachea el valor en `self._cached_equity` para el ciclo actual

**Error handling**:
- Si Alpaca API falla (timeout, 429, 401, etc.): log `logger.warning("Error fetching equity: %s", e)`, retorna `self._cached_equity` (último valor conocido)
- Si es la primera llamada y falla: retorna `self._initial_equity` (seteado en `_setup()`)
- Nunca lanza excepción hacia arriba

### 4.2 `_publish_status()`

**Signature**:
```python
def _publish_status(self) -> None
```

**Order of file writes** (importante: trades.json primero, status.json último):

```python
def _publish_status(self):
    now = datetime.now(timezone.utc)
    equity = self._get_current_equity()
    
    # 1. equity.json
    _atomic_write(LOGS_DIR / "equity.json", { ... })
    
    # 2. positions.json
    _atomic_write(LOGS_DIR / "positions.json", { ... })
    
    # 3. signals.json
    _atomic_write(LOGS_DIR / "signals.json", { ... })
    
    # 4. strategies.json
    _atomic_write(LOGS_DIR / "strategies.json", { ... })
    
    # 5. scanner_results.json (only if scanner ran this cycle)
    # (written by scanner module, NOT here)
    
    # 6. status.json — LAST, because frontend uses this as heartbeat indicator
    _atomic_write(LOGS_DIR / "status.json", { ... })
```

**Why status.json last**: El frontend usa `status.json` como heartbeat. Si status.json se publica antes que los otros archivos, el frontend podría leer status nuevo pero datos viejos. Al escribir status.json al final, garantizamos que cuando el frontend vea un timestamp nuevo, TODOS los archivos están actualizados.

**What data goes where**:

| File | Data source in orchestrator |
|------|----------------------------|
| `equity.json` | `_get_current_equity()`, `self._initial_equity`, equity_curve acumulada en `self._equity_curve` (lista) |
| `positions.json` | `self._trading.get_all_positions()`, `self._position`, `self._position_qty`, `self._last_entry_price` |
| `signals.json` | `self._signals_today` (lista acumulada de señales del día) |
| `strategies.json` | Iterar `self._scanner.strategies` + estrategias conocidas por nombre |
| `status.json` | `self._running`, `self._killed`, `self._use_legacy_fallback`, `self._last_signal`, `self._last_error` |

### 4.3 `_append_trade(trade: dict)`

**Signature**:
```python
def _append_trade(self, trade: dict) -> None
```

**Process**:
1. Leer `logs/trades.json` si existe → cargar JSON
2. Si no existe o está corrupto → inicializar con estructura base vacía
3. Append `trade` al array `trades`
4. Recalcular `total_trades`, `total_pnl`, `win_rate`, `profit_factor`
5. Escribir con `_atomic_write(LOGS_DIR / "trades.json", data)`

**Trade structure** (el dict `trade` debe tener estos campos):

| Field | Source |
|-------|--------|
| `symbol` | `self.symbol` (o `trade["symbol"]`) |
| `side` | `"long"` (hardcodeado por ahora) |
| `entry_price` | `self._last_entry_price` |
| `exit_price` | `trade["exit_price"]` o `price` param |
| `qty` | `self._position_qty` |
| `pnl` | Calculado: `(exit_price - entry_price) * qty` |
| `entry_at` | `self._last_entry_at` (ISO string) |
| `exit_at` | `datetime.now(timezone.utc).isoformat()` |
| `strategy` | `"sma_crossover"` (hardcodeado, o de signal) |
| `slippage_bps` | De `calculate_slippage()` |
| `execution_method` | `"twap"` o `"market"` |

**Error handling**:
- `FileNotFoundError` al leer → crear estructura nueva (no es error)
- `json.JSONDecodeError` al leer → log warning, empezar con estructura vacía
- Error al escribir → log warning, no interrumpir flujo

### 4.4 Modifications to `_run_legacy_loop()`

Insertar llamada a `_publish_status()` en estos puntos:

```python
async def _run_legacy_loop(self):
    ...
    # STARTUP: publish initial status
    await self._publish_status()  # ← ADDED after setup
    
    while self._running and not self._killed:
        try:
            # ... existing scanner logic ...
            # ... existing SMA logic ...
            
            # END OF CYCLE: publish status
            await self._publish_status()  # ← ADDED at end of each cycle
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            # ... existing error handling ...
    
    # SHUTDOWN: publish final status with OFFLINE
    self._running = False
    await self._publish_status()  # ← ADDED after loop ends (bot stops)
```

**Note**: `_publish_status()` es async-lite — `_atomic_write()` es sincrónico. Se puede llamar con `await asyncio.to_thread(self._publish_status)` si se desea verdadera no-blocking, pero el costo de escritura es tan bajo (~5ms) que una llamada directa al final del ciclo es aceptable.

### 4.5 Modifications to `_execute_signal()`

Insertar llamado a `_append_trade()` en el path SELL (cierre de posición):

```python
# ── SELL (cierre) ──
elif action == "SELL" and self._position == "long":
    ...
    # Existing: calcular pnl, slippage, etc.
    
    # AFTER calculating P&L and before resetting position state:
    trade_record = {
        "symbol": self.symbol,
        "side": "long",
        "entry_price": self._last_entry_price,
        "exit_price": price,
        "qty": self._position_qty,
        "pnl": pnl,
        "entry_at": self._last_entry_at.isoformat(),
        "exit_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "sma_crossover",  # TODO: extract from signal
        "slippage_bps": slippage_bps,
        "execution_method": exec_method,
    }
    self._append_trade(trade_record)  # ← ADDED
    
    # Existing: reset position state
    ...
```

### 4.6 Startup

En `_setup()` o inmediatamente después, publicar status inicial:

```python
async def _setup(self) -> bool:
    # ... existing logic ...
    
    # ADD: publish initial status after successful setup
    self._publish_status()
    
    return True
```

**Initial status**: `bot_status: "ONLINE"`, `mode: "legacy"` (o "modular"), `last_signal: null`, `last_error: null`, `uptime_seconds: 0`.

### 4.7 Shutdown

En `_shutdown()` o justo antes de salir, publicar status final:

```python
async def _shutdown(self):
    # ADD: publish final status BEFORE closing connections
    self._running = False
    self._publish_status()
    
    # ... existing cleanup logic ...
```

**Final status**: `bot_status: "OFFLINE"` (o `"KILLED"` si `self._killed` es `True`), `last_error: null` (o último error), `uptime_seconds: elapsed`.

---

## 5. Error Handling Scenarios

| # | Scenario | Detalle | Comportamiento |
|---|----------|---------|----------------|
| 1 | **Alpaca API error reading equity** | `get_account()` falla por rate limit, timeout, o auth | `_get_current_equity()` retorna último valor conocido, `equity.json` se publica con flag `stale: true`. Frontend muestra badge "⚠️ Stale". |
| 2 | **JSON write permission error** | `logs/` no tiene permisos de escritura | `_atomic_write()` logea warning, retorna `False`. Orchestrator continúa ejecutándose. Archivo anterior preservado. Frontend muestra datos anteriores. |
| 3 | **Scanner not initialized** | `self._scanner` es `None` | `scanner_results.json` no se escribe. Frontend muestra "Scanner not initialized or no scan completed yet". |
| 4 | **No trades yet** | Bot no ha ejecutado ningún trade | `trades.json` existe pero `trades: []`. Frontend muestra tabla vacía con "No trades executed this session". |
| 5 | **Frontend starts before bot** | Ningún archivo JSON existe en `logs/` | Todas las páginas muestran estado de espera. Dashboard: "Waiting for bot to start...". Otras páginas: sus respectivos empty states. |
| 6 | **Bot crashes mid-cycle** | Archivos JSON dejan de actualizarse | `status.json` mantiene último estado antes del crash. Frontend detecta que `status.json` tiene >5 minutos desde su timestamp → badge STALE (amarillo). Después de 3 ciclos de refresh sin cambio, marca bot como OFFLINE. |
| 7 | **Concurrent write race** | Frontend lee mientras bot escribe | Atomic write previene lectura parcial. Frontend lee archivo completo anterior (antes del rename) o completo nuevo (después del rename). Nunca datos truncados. |
| 8 | **Disk full** | `_atomic_write()` falla con ENOSPC | Log error "Disk full". Archivo `.tmp` se elimina, archivo destino preservado. Frontend continúa con datos anteriores. |
| 9 | **File deleted while frontend running** | Usuario borra `logs/equity.json` manualmente | Próximo ciclo de refresh → file missing → empty state para equity section. Bot sigue funcionando. |
| 10 | **Recovery after bot restart** | Bot se detiene y reinicia | Nuevo status.json con `bot_status: "ONLINE"` y `uptime_seconds: 0`. Frontend detecta cambio de OFFLINE → ONLINE, reactiva displays. |
| 11 | **Log file rotation/truncation** | Logs rotados externamente | Frontend usa `deque(f, maxlen=1000)` → siempre lee últimas 1000 líneas. Si archivo se trunca, deque captura líneas disponibles. |

---

## 6. Acceptance Criteria

### JSON File Write Correctness

- [ ] `_atomic_write()` escribe `.tmp` y renombra atómicamente
- [ ] `equity.json` se sobrescribe cada ciclo (nunca append)
- [ ] `positions.json` se sobrescribe cada ciclo
- [ ] `signals.json` se sobrescribe cada ciclo
- [ ] `strategies.json` se sobrescribe cada ciclo
- [ ] `status.json` se sobrescribe cada ciclo (último en escribirse)
- [ ] `scanner_results.json` se sobrescribe por el scanner en cada scan
- [ ] `trades.json` hace append (read → append → write) en cada cierre de trade
- [ ] Todos los archivos contienen JSON válido (json.loads parsea sin error)
- [ ] `status.json` se publica en startup (ONLINE), cada ciclo, y shutdown (OFFLINE)

### Frontend Pages — Live Data

- [ ] Dashboard muestra 6 metric cards con valores reales
- [ ] Equity curve chart renderiza con hover tooltip
- [ ] Drawdown chart renderiza como filled area
- [ ] Open positions table tiene todas las columnas especificadas
- [ ] Bot status muestra ONLINE/verde con datos actualizados
- [ ] Scanner page muestra signals table con colores BUY/SELL/RANK
- [ ] Scanner distribution chart tiene barras por estrategia
- [ ] Estrategias page muestra expanders con params, validation, signal count
- [ ] Trades page muestra tabla con P&L columnas color-coded
- [ ] Trades P&L chart tiene barras verdes/rojas
- [ ] Trades CSV export descarga archivo válido
- [ ] Logs page muestra últimas líneas con auto-scroll
- [ ] Logs level filters funcionan (DEBUG/INFO/WARNING/ERROR)
- [ ] Todas las páginas hacen auto-refresh en sus intervalos especificados

### Frontend Pages — Missing/Empty Data

- [ ] Dashboard sin archivos → "Waiting for bot to start..."
- [ ] Dashboard sin equity.json → cards muestran "—", chart muestra empty state
- [ ] Dashboard sin positions.json → tabla muestra "No position data available"
- [ ] Scanner sin scanner_results.json → "Scanner not initialized or no scan completed yet"
- [ ] Estrategias sin strategies.json → "No strategies loaded"
- [ ] Trades sin trades.json → "No trades executed this session"
- [ ] Logs sin bot.log → "Log file not found at logs/bot.log"
- [ ] Todas las páginas se renderizan sin crash ante cualquier archivo faltante

### Bot Cycle Integration

- [ ] `_publish_status()` se llama al final de cada ciclo de `_run_legacy_loop()`
- [ ] Status se publica en startup (setup completo)
- [ ] Status final OFFLINE se publica en shutdown
- [ ] `_append_trade()` se llama en el path SELL de `_execute_signal()`
- [ ] Publicar status NO bloquea el ciclo principal (>500ms de latencia es detectable)
- [ ] Error en publish no detiene el ciclo — se logea y continúa

### Recovery Scenarios

- [ ] Bot crash → archivos dejan de actualizar → frontend muestra STALE → luego OFFLINE
- [ ] Bot restart → status cambia a ONLINE → frontend reanuda displays
- [ ] Archivo borrado manualmente → frontend muestra empty state para esa sección
- [ ] Archivo corrupto → frontend logea warning, muestra "Data unavailable"
- [ ] Frontend arranca antes que bot → todas las secciones en waiting state
- [ ] Disco lleno → _atomic_write() logea error, archivos anteriores preservados

---

## 7. File Structure (Frontend Package)

```
src/royaltdn/frontend/
├── __init__.py
├── app.py                   # Entry point: st.navigation with 5 pages
├── pages/
│   ├── __init__.py
│   ├── dashboard.py         # 📊 Dashboard page
│   ├── scanner.py           # 🔍 Scanner page
│   ├── estrategias.py       # ⚙️ Estrategias page
│   ├── trades.py            # 📈 Trades page
│   └── logs.py              # 📋 Logs page
├── components/
│   ├── __init__.py
│   ├── loaders.py            # JSON file readers with error handling
│   └── charts.py             # Plotly chart builders
```

### `components/loaders.py` — Public API

```python
def load_json(path: Path) -> Optional[dict]:
    """Read and parse a JSON file safely. Returns None on any error."""

def load_status() -> dict:       # returns {} if missing/corrupt
def load_equity() -> dict:       # returns {} if missing/corrupt
def load_positions() -> dict:    # returns {} if missing/corrupt
def load_signals() -> dict:      # returns {} if missing/corrupt
def load_scanner_results() -> dict:  # returns {} if missing/corrupt
def load_strategies() -> dict:   # returns {} if missing/corrupt
def load_trades() -> dict:       # returns {} if missing/corrupt
def is_stale(updated_at: str, max_age_minutes: int = 5) -> bool:
```
All loader functions return empty dict `{}` on any error (missing, corrupt, permission). Never raise.

### `components/charts.py` — Public API

```python
def equity_curve_chart(equity_data: dict) -> go.Figure:
def drawdown_chart(equity_data: dict) -> go.Figure:
def distribution_chart(scanner_data: dict) -> go.Figure:
def pnl_bar_chart(trades: list[dict]) -> go.Figure:
def pnl_histogram(trades: list[dict]) -> go.Figure:
```
All chart functions return a valid Plotly Figure with empty-state annotations when data is empty.

### `app.py` — Entry Point

```python
import streamlit as st
from streamlit.navigation import page, navigation

st.set_page_config(
    page_title="RoyalTDN",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

dashboard = page("pages/dashboard.py", title="📊 Dashboard")
scanner = page("pages/scanner.py", title="🔍 Scanner")
estrategias = page("pages/estrategias.py", title="⚙️ Estrategias")
trades = page("pages/trades.py", title="📈 Trades")
logs = page("pages/logs.py", title="📋 Logs")

nav = navigation([dashboard, scanner, estrategias, trades, logs])
nav.run()
```

---

## 8. Dependencies Between Modules

```
┌─────────────────────────────────────────────────────────────────┐
│                        orchestrator.py                          │
│                                                                 │
│  _publish_status()  ───→  _atomic_write(path, data)            │
│  _append_trade()    ───→  _atomic_write(logs/trades.json, ...) │
│  _get_current_equity() ──→ self._trading.get_account()         │
│                                                                 │
│  Called at end of _run_legacy_loop() each cycle                 │
│  Called in _execute_signal() on SELL path                      │
│  Called on startup (_setup) and shutdown (_shutdown)            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ writes
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                        scanner.py                               │
│                                                                 │
│  scan() ───→ _atomic_write(logs/scanner_results.json, result)  │
│                                                                 │
│  Called from orchestrator._run_legacy_loop() every              │
│  SCANNER_INTERVAL_MINUTES                                       │
└──────────────────────┬──────────────────────────────────────────┘
                       │ writes
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                        logs/*.json (7 files)                    │
│                                                                 │
│  status.json     ← orchestrator (every cycle, overwrite)        │
│  equity.json     ← orchestrator (every cycle, overwrite)        │
│  positions.json  ← orchestrator (every cycle, overwrite)        │
│  signals.json    ← orchestrator (every cycle, overwrite)        │
│  strategies.json ← orchestrator (every cycle, overwrite)        │
│  scanner_results.json ← scanner (on scan, overwrite)            │
│  trades.json     ← orchestrator (on trade close, append)        │
└──────────┬──────────────────────────────────────────────────────┘
           │ reads (polling every 2-5s)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     frontend/components/                         │
│                                                                 │
│  loaders.py ──→ reads logs/*.json → returns dict or {}          │
│  charts.py  ──→ gets data from loaders → returns Plotly Figure  │
└──────────┬──────────────────┬───────────────────────────────────┘
           │                  │
           ▼                  ▼
┌────────────────────┐  ┌────────────────────────────────────────┐
│  pages/*.py        │  │  app.py                                │
│                    │  │                                        │
│  dashboard.py ←─── loaders + charts                            │
│  scanner.py   ←─── loaders + charts                            │
│  estrategias.py ←── loaders                                    │
│  trades.py    ←─── loaders + charts                            │
│  logs.py      ←─── reads logs/bot.log directly                 │
└────────────────────┘  └────────────────────────────────────────┘
```

---

## 9. Requirements

### Requirement: Atomic JSON file writing

The orchestrator SHALL write all JSON files to `logs/` using the `_atomic_write()` function that writes to a `.tmp` file then atomically renames to the target path. This SHALL prevent partial reads by the frontend.

#### Scenario: Atomic write prevents partial read

- GIVEN the orchestrator is writing `equity.json` via `_atomic_write()`
- WHEN the frontend reads `equity.json` during the write
- THEN the frontend SHALL see either the complete previous file or the complete new file
- AND the frontend SHALL NEVER see truncated or partially-written JSON

#### Scenario: Atomic write handles disk full

- GIVEN the disk is full during `_atomic_write()`
- WHEN `json.dumps()` + write to `.tmp` succeeds but `os.replace()` fails
- THEN the original file SHALL remain intact
- AND the orchestrator SHALL log a warning and continue running

### Requirement: Frontend starts without crashing when files are missing

The frontend SHALL render all pages without crashing even when zero JSON files exist in `logs/`.

#### Scenario: All files missing on startup

- GIVEN the frontend starts before the bot has written any files
- WHEN the user navigates to any page
- THEN the page SHALL show its empty state message
- AND NO page SHALL raise an unhandled exception

#### Scenario: Individual file missing mid-session

- GIVEN the bot is running and the frontend is displaying data
- WHEN a user deletes a single JSON file (e.g., `equity.json`)
- THEN the affected section SHALL show its empty state
- AND the other sections SHALL continue displaying normally

### Requirement: Frontend detects stale data

The frontend SHALL check the `updated_at` or `timestamp` field of each JSON file and display a stale indicator when data is older than 5 minutes.

#### Scenario: Bot stops updating files

- GIVEN the bot has been writing JSON files every 60 seconds
- WHEN the bot crashes and file updates stop
- THEN within 3 refresh cycles (max 15s), the frontend SHALL detect that `status.json` is stale
- AND the Dashboard SHALL show an "⚠️ STALE" or red "OFFLINE" indicator

### Requirement: Bot status lifecycle

The orchestrator SHALL publish `status.json` with correct bot status at startup, each cycle, and shutdown.

#### Scenario: Bot publishes OFFLINE on shutdown

- GIVEN the orchestrator is running in legacy mode
- WHEN `_shutdown()` is called
- THEN `status.json` SHALL be written with `bot_status: "OFFLINE"` before connections are closed
- AND the frontend SHALL reflect this within one refresh cycle

### Requirement: Trade recording on exit

The orchestrator SHALL record completed trades to `logs/trades.json` when a position is closed in `_execute_signal()`.

#### Scenario: Trade appended on SELL

- GIVEN a long position is open with `self._position == "long"`
- WHEN a `SELL` signal is processed in `_execute_signal()`
- THEN `_append_trade()` SHALL be called with the trade details
- AND `trades.json` SHALL contain the new trade appended to the `trades` array

### Requirement: Metric card display

The Dashboard page SHALL display metric cards for Capital, P&L Day ($), P&L Day (%), Drawdown (%), Open Positions, Signals Today, and Sharpe Ratio.

#### Scenario: All metrics show live values

- GIVEN `equity.json`, `positions.json`, and `signals.json` contain valid data
- WHEN the Dashboard page renders
- THEN 7 metric cards SHALL display with formatted values
- AND P&L Day ($) SHALL be green for positive, red for negative

#### Scenario: Metric cards handle missing equity

- GIVEN `equity.json` is missing or empty
- WHEN the Dashboard renders
- THEN Capital, P&L Day, Drawdown, and Sharpe Ratio cards SHALL show "—"

### Requirement: Stale equity flag

When the orchestrator cannot fetch equity from Alpaca, it SHALL use the last known value and set `stale: true` in `equity.json`.

#### Scenario: Alpaca API error

- GIVEN the Alpaca API returns an error (timeout, 429, or auth failure)
- WHEN `_get_current_equity()` is called
- THEN it SHALL return the cached equity value
- AND `_publish_status()` SHALL include `stale: true` in `equity.json`
- AND the Dashboard SHALL show a "⚠️ Stale" badge next to Capital

### Requirement: Scanner page handles missing data

The Scanner page SHALL show an appropriate empty state when scanner data is not available.

#### Scenario: Scanner never ran

- GIVEN `scanner_results.json` does not exist or is empty
- WHEN the user navigates to the Scanner page
- THEN the page SHALL display "Scanner not initialized or no scan completed yet"
- AND NO charts or tables SHALL render

### Requirement: Trades page CSV export

The Trades page SHALL include a download button that exports the currently filtered trades as a CSV file.

#### Scenario: CSV download with filtered trades

- GIVEN the Trades page is rendering with 10 trades visible (after filters)
- WHEN the user clicks "📥 Download CSV"
- THEN a CSV file SHALL download with filename `trades_export_YYYYMMDD.csv`
- AND the CSV SHALL contain all trade columns matching the current filter

### Requirement: Logs page reads last 1000 lines

The Logs page SHALL read and display the last 1000 lines from `logs/bot.log`.

#### Scenario: Log file has more than 1000 lines

- GIVEN `logs/bot.log` has 5000 lines
- WHEN the Logs page refreshes
- THEN only the last 1000 lines SHALL be displayed
- AND the display SHALL be performant (< 500ms render)

#### Scenario: Log file missing

- GIVEN `logs/bot.log` does not exist
- WHEN the Logs page renders
- THEN `st.info("Log file not found at logs/bot.log")` SHALL be shown
- AND the page SHALL NOT crash

### Requirement: Auto-refresh intervals

Each frontend page SHALL auto-refresh at its specified interval using `st.rerun` with a sleep.

#### Scenario: Dashboard refreshes every 3 seconds

- GIVEN the Dashboard page is active in the browser
- WHEN 3 seconds elapse since the last render
- THEN `st.rerun` SHALL be called
- AND the page SHALL re-read all JSON files and update displays

#### Scenario: Logs refreshes every 2 seconds

- GIVEN the Logs page is active in the browser
- WHEN 2 seconds elapse since the last render
- THEN `st.rerun` SHALL be called
- AND new log lines SHALL appear in the viewer

---

## 10. Open Questions

1. **Scanner publishing**: ¿El scanner debe llamar a `_atomic_write()` directamente o debe emitir un evento que el orquestador captura? **Decisión actual**: Scanner llama directamente a `_atomic_write()` — es más simple y el scanner ya tiene acceso a las funciones necesarias.
2. **Equity curve tamaño**: ¿Cuántos puntos debe mantener `equity_curve[]`? **Decisión actual**: Máximo 1000 puntos (unos 16 horas a 1 punto/minuto). Cuando excede, se descarta el más antiguo.
3. **Log file path**: ¿El path del log debe ser configurable? **Decisión actual**: Fijo en `logs/bot.log` para esta fase. Se puede hacer configurable en una fase futura.
