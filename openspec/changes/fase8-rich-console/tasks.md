# Tasks: Fase 8 — Rich Interactive Console

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1800–2500 (additions + deletions) |
| 400-line budget risk | **High** |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Foundation + Loguru → PR 2: Data + Widgets + Screens → PR 3: CLI + IPC + Tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: **Yes**
Chained PRs recommended: **Yes**
Chain strategy: **pending**
400-line budget risk: **High**

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | H1: Foundation + Loguru Migration | PR 1 | Base = main; ~15 mechanical module migrations, delete frontend/, deps |
| 2 | H2–H3: Data layer, Widgets, Screens, App | PR 2 | Base = main (after PR 1); ~8 new files, no orchestrator changes |
| 3 | H4–H5: CLI + IPC + Cleanup + Tests | PR 3 | Base = main (after PR 2); main.py CLI, orchestrator IPC, tests |

---

## Hito 1: Foundation + Loguru Migration

### ✅ Tarea 1.1: Eliminar Streamlit + plotly + frontend/

**Archivo**: N/A (desinstalación + eliminación de archivos)
**Tipo**: eliminar
**Dependencias**: ninguna
**Esfuerzo**: media

**Descripción**:
Desinstalar streamlit y plotly del entorno. Eliminar `requirements/fase6.txt` o vaciarlo. Eliminar todo el árbol `src/royaltdn/frontend/` excepto `components/builder_state.py` que debe refactorizarse (extraer `INDICATOR_DEFS`, `OPERATOR_GROUPS`, `DEFAULT_STATE`, `NEEDS_VALUE`, `_build_tree`, `_flatten_conditions` y eliminar las funciones que dependen de `import streamlit as st`).

**Contenido requerido**:
- `pip uninstall streamlit plotly -y`
- `rm -rf src/royaltdn/frontend/__pycache__/ src/royaltdn/frontend/pages/ src/royaltdn/frontend/components/charts.py src/royaltdn/frontend/components/__init__.py src/royaltdn/frontend/components/backtest_charts.py src/royaltdn/frontend/components/loaders.py src/royaltdn/frontend/app.py src/royaltdn/frontend/__init__.py`
- Refactor `builder_state.py`: conservar INDICATOR_DEFS, INDICATOR_MAP, OPERATOR_GROUPS, NEEDS_VALUE, DEFAULT_STATE, _next_id, _build_tree, _flatten_conditions; eliminar init_builder_state, add_indicator, remove_indicator, add_entry_condition, remove_entry_condition, add_exit_condition, remove_exit_condition, build_config, update_json_view, reset_builder, load_config_into_state

**Criterios de verificación**:
1. [x] `pip list | grep streamlit` no muestra streamlit
2. [x] `pip list | grep plotly` no muestra plotly
3. [x] `ls src/royaltdn/frontend/` muestra solo `components/builder_state.py` (sin `__pycache__/`)
4. [x] `python -c "from royaltdn.frontend.components.builder_state import INDICATOR_DEFS; print(len(INDICATOR_DEFS))"` funciona y retorna 16

### ✅ Tarea 1.2: Instalar nuevas dependencias + requirements

**Archivo**: `requirements/fase8_console.txt`
**Tipo**: crear
**Dependencias**: 1.1
**Esfuerzo**: baja

**Descripción**:
Instalar rich, loguru, tqdm, colorama. Crear `requirements/fase8_console.txt` con rangos exactos.

**Contenido requerido**:
- `pip install rich loguru tqdm colorama`
- Archivo `requirements/fase8_console.txt` con contenido:
  ```
  rich>=13.0.0,<14.0.0
  loguru>=0.7.0,<1.0.0
  tqdm>=4.66.0,<5.0.0
  colorama>=0.4.6,<1.0.0
  ```

**Criterios de verificación**:
1. [x] `python -c "import rich; import loguru; import tqdm; import colorama; print('OK')"` retorna OK
2. [x] `requirements/fase8_console.txt` existe con los 4 paquetes y rangos exactos

### ✅ Tarea 1.3: Crear loguru_config.py

**Archivo**: `src/royaltdn/frontend/console/loguru_config.py`
**Tipo**: crear
**Dependencias**: 1.2
**Esfuerzo**: media

**Descripción**:
Crear función `setup_logging()` que configura Loguru con 3 sinks: file sink con rotación (logs/bot.log, 10MB, 7 días retention), stderr sink colorizado (DEBUG level), y LogBuffer sink opcional. Usar formato exacto `{time} | {level:<8} | {name}:{function}:{line} | {message}` con colores `<green>`, `<level>`, `<cyan>` para stderr.

**Contenido requerido**:
- `setup_logging(log_buffer: Optional[LogBuffer] = None) -> None`
- Remover handler default de Loguru con `logger.remove()`
- `logger.add("logs/bot.log", rotation="10 MB", retention="7 days", format=FILE_FORMAT, level="INFO")`
- `logger.add(sys.stderr, colorize=True, format=CONSOLE_FORMAT, level="DEBUG")`
- Si `log_buffer` no es None: `logger.add(log_buffer.add, level="DEBUG")`

**Criterios de verificación**:
1. [x] `setup_logging()` se importa sin errores
2. [x] Después de llamar `setup_logging()`, `logger.info("test")` escribe a `logs/bot.log`
3. [x] LogBuffer sink se conecta correctamente cuando se pasa un buffer

### ✅ Tarea 1.4: Migrar 15 módulos de logging estándar a Loguru

**Archivo**: Múltiples archivos (ver lista)
**Tipo**: modificar
**Dependencias**: 1.3
**Esfuerzo**: alta

**Descripción**:
En cada módulo: eliminar `import logging`, eliminar `logger = logging.getLogger(...)`, agregar `from loguru import logger`. Reemplazar formato `%`-string en llamadas de logger con estilo `{}` de Loguru. NO cambiar la semántica de las llamadas (`.info()`, `.warning()`, `.error()`, `.debug()`, `.critical()` se mantienen igual).

**Módulos a migrar (lista completa)**:
1. `src/royaltdn/orchestrator.py`
2. `src/royaltdn/ingestion/data_ingestor.py` — también eliminar `basicConfig`
3. `src/royaltdn/strategy/sma_strategy.py` — también eliminar `basicConfig`
4. `src/royaltdn/strategy/bollinger_rsi.py`
5. `src/royaltdn/strategy/momentum_atr.py`
6. `src/royaltdn/strategy/factor_rotation.py`
7. `src/royaltdn/execution/twap.py`
8. `src/royaltdn/storage/db.py`
9. `src/royaltdn/monitoring/tca.py`
10. `src/royaltdn/scanner/scanner.py`
11. `src/royaltdn/scanner/filters.py`
12. `src/royaltdn/scanner/universe.py`
13. `src/royaltdn/risk_manager.py`
14. `src/royaltdn/alerts.py`
15. `src/royaltdn/legacy_polling.py` — también eliminar `basicConfig`

**Criterios de verificación**:
1. [x] `grep -rn "import logging" src/royaltdn/ --include="*.py" | grep -v frontend | grep -v __pycache__` retorna vacío
2. [x] `grep -rn "logging.getLogger" src/royaltdn/ --include="*.py" | grep -v frontend | grep -v __pycache__` retorna vacío
3. [x] Cada módulo migrado se importa sin errores: `python -c "from royaltdn.orchestrator import Orchestrator; print('OK')"`
4. [x] Formato `%` reemplazado por `{}` en todas las llamadas a logger

### ✅ Tarea 1.5: Crear LogBuffer (log_handler.py)

**Archivo**: `src/royaltdn/frontend/console/log_handler.py`
**Tipo**: crear
**Dependencias**: 1.2
**Esfuerzo**: media

**Descripción**:
Crear clase `LogBuffer` con buffer circular thread-safe usando `collections.deque(maxlen=200)`. Implementar `add()` como callable para sink de Loguru, `get_lines()` con filtros por level/module/text, y `get_recent()`. Crear `setup_console_log_handler()` que agrega un sink de Loguru que formatea el record como string antes de pasarlo al buffer.

**Contenido requerido**:
- `LogBuffer.__init__(self, max_lines: int = 200)` — inicializa deque y Lock
- `LogBuffer.add(self, record: str) -> None` — thread-safe append
- `LogBuffer.get_lines(self, level_filter=None, module_filter=None, text_filter=None, last_n=None) -> list[str]`
- `LogBuffer.get_recent(self, n: int = 5) -> list[str]`
- `setup_console_log_handler(log_buffer: LogBuffer) -> int` — retorna sink ID

**Criterios de verificación**:
1. [x] Import sin errores: `from royaltdn.frontend.console.log_handler import LogBuffer`
2. [x] Buffer trimea a max 200 cuando se agregan 250 líneas
3. [x] `get_lines(level_filter="INFO")` retorna solo líneas INFO
4. [x] `get_recent(5)` retorna últimas 5 líneas en orden
5. [ ] Thread-safe: 10 hilos agregan 100 líneas cada uno sin race condition

### ✅ Tarea 1.6: Refactorizar main.py — reemplazar logging por Loguru

**Archivo**: `src/royaltdn/main.py`
**Tipo**: modificar
**Dependencias**: 1.3, 1.4
**Esfuerzo**: baja

**Descripción**:
Reemplazar `import logging`, `logging.basicConfig()`, y `FileHandler` por `from loguru import logger` + llamada a `setup_logging()`. Eliminar todo el bloque de configuración de logging (líneas 33-45). Agregar `from royaltdn.frontend.console.loguru_config import setup_logging` y llamar `setup_logging()` al inicio de `main()`.

**Contenido requerido**:
- Eliminar `import logging` (línea 12)
- Eliminar todo el bloque `logging.basicConfig(...)` / `FileHandler` / `getLogger()` (líneas 33-47)
- Agregar `from loguru import logger`
- Agregar `from royaltdn.frontend.console.loguru_config import setup_logging`
- Llamar `setup_logging()` como primera línea de `main()`

**Criterios de verificación**:
1. [x] `python -c "from royaltdn.main import main; print('OK')"` funciona sin errores (pre-existing dep issues excluded)
2. [x] No queda `import logging` en main.py
3. [x] `logging.getLogger()` no aparece en main.py

---

## Hito 2: Data Layer + Widgets

### Tarea 2.1: Crear StateLoader (state.py)

**Archivo**: `src/royaltdn/frontend/console/components/state.py`
**Tipo**: crear
**Dependencias**: 1.1, 1.2
**Esfuerzo**: media

**Descripción**:
Clase `StateLoader` que lee los 7 archivos JSON de `logs/` con TTL cache. Cada archivo tiene su propio método de carga (`load_status`, `load_equity`, `load_positions`, `load_scanner_results`, `load_strategies`, `load_trades`). `load_all()` carga todos y retorna dict estructurado. Manejar archivos faltantes → default vacío, JSON corrupto → log + default.

**Contenido requerido**:
- `StateLoader.__init__(self, logs_dir: str = "logs", cache_ttl: float = 1.0)`
- Cache interna: `dict[str, tuple[float, Any]]` con timestamp + datos
- `_load_file(self, filename: str, default: Any) -> Any` — método privado con manejo de errores
- 6 load methods con defaults que coinciden con data-contract.md
- `load_all() -> dict` con claves: status, equity, positions, scanner, strategies, trades

**Criterios de verificación**:
1. [ ] Import sin errores
2. [ ] `load_status()` retorna dict correcto cuando `logs/status.json` existe
3. [ ] `load_scanner_results()` retorna default `{"last_scan": {}, "scan_history": [], "updated_at": None}` cuando el archivo no existe
4. [ ] JSON corrupto produce default + log warning (no crash)
5. [ ] Cache TTL funciona: segunda llamada dentro de 1s no relee el archivo

### Tarea 2.2: Crear 12 funciones widget (widgets.py)

**Archivo**: `src/royaltdn/frontend/console/components/widgets.py`
**Tipo**: crear
**Dependencias**: 2.1
**Esfuerzo**: alta

**Descripción**:
12 funciones que reciben datos (dicts/lists de StateLoader) y retornan renderables de Rich (`Panel`, `Table`, etc.). Ninguna escribe a consola directamente. Cada función debe manejar datos vacíos sin crashear.

**Funciones a crear**:
- `create_header(state) -> Panel` — título, modo, status badge (ONLINE verde/OFFLINE rojo/KILLED amarillo), uptime, countdown
- `create_kpi_cards(state) -> Table` — 4 columnas: Capital, P&L Día, Drawdown, Win Rate
- `create_positions_table(state) -> Table` — símbolo, cantidad, P.entrada, P.actual, P&L, duración
- `create_signals_table(signals) -> Table` — hora, símbolo, acción, precio, estrategia
- `create_risk_panel(state) -> Panel` — barra drawdown progreso, pérdidas consecutivas
- `create_scanner_table(scanner_data) -> Table` — last scan info + signals
- `create_strategies_table(strategies_data, user_strategies) -> Table` — name, status, params
- `create_trades_table(trades) -> Table` — entry/exit time, symbol, P&L
- `create_trade_metrics(trades) -> Panel` — Profit Factor, mejor/peor trade, Sharpe
- `create_log_panel(log_buffer, level_filter, module_filter, text_filter) -> Panel` — logs colorizados
- `create_footer() -> Panel` — atajos de teclado
- `create_empty_state(message: str) -> Panel` — mensaje centrado

**Criterios de verificación**:
1. [ ] Cada función retorna un objeto Rich renderable (Panel o Table)
2. [ ] `create_positions_table({"open_positions": [], "total_open": 0})` no crashea
3. [ ] `create_header({"bot_status": "OFFLINE"})` muestra status badge rojo
4. [ ] `create_footer()` siempre retorna Panel sin errores

---

## Hito 3: Screens + Commands + App

### Tarea 3.1: Crear screens/__init__.py

**Archivo**: `src/royaltdn/frontend/console/screens/__init__.py`
**Tipo**: crear
**Dependencias**: 2.2
**Esfuerzo**: baja

**Descripción**:
Package init que exporta todas las funciones render_* de los 5 screens.

**Contenido requerido**:
- `from royaltdn.frontend.console.screens.dashboard import render_dashboard`
- `from royaltdn.frontend.console.screens.scanner import render_scanner`
- `from royaltdn.frontend.console.screens.estrategias import render_estrategias`
- `from royaltdn.frontend.console.screens.trades import render_trades`
- `from royaltdn.frontend.console.screens.logs import render_logs`

**Criterios de verificación**:
1. [ ] `from royaltdn.frontend.console.screens import render_dashboard` funciona

### Tarea 3.2: Crear screens/dashboard.py

**Archivo**: `src/royaltdn/frontend/console/screens/dashboard.py`
**Tipo**: crear
**Dependencias**: 3.1 (screens/__init__), 2.2
**Esfuerzo**: media

**Descripción**:
Función `render_dashboard(state, log_buffer) -> Layout`: Layout completo con header, body (60/40 split), y footer. Lado izquierdo: KPI cards + positions table + signals table. Lado derecho: risk panel + últimos logs.

**Contenido requerido**:
- Verificar terminal size mínimo 80x24 — si es menor, retornar Layout con mensaje "Terminal too small"
- Usar `Rich.Layout` con `Splitter` para columnas
- Layout.header, Layout.body, Layout.footer con sizes fijos

**Criterios de verificación**:
1. [ ] `render_dashboard(mock_state, mock_buffer)` retorna Layout
2. [ ] Layout contiene header con "ROYALTDN"
3. [ ] Con terminal < 80x24, retorna Layout con mensaje de resize

### Tarea 3.3: Crear screens/scanner.py

**Archivo**: `src/royaltdn/frontend/console/screens/scanner.py`
**Tipo**: crear
**Dependencias**: 3.1, 2.2
**Esfuerzo**: baja

**Descripción**:
Función `render_scanner(state, log_buffer) -> Layout`: last scan info header, signals table, scan history table.

**Contenido requerido**:
- Usar `create_header()`, `create_scanner_table()`, `create_footer()` de widgets
- Manejar scan vacío con `create_empty_state("Scanner no ha ejecutado aún")`

**Criterios de verificación**:
1. [ ] Retorna Layout con header + scanner table + footer
2. [ ] Con scanner vacío, muestra empty state

### Tarea 3.4: Crear screens/estrategias.py

**Archivo**: `src/royaltdn/frontend/console/screens/estrategias.py`
**Tipo**: crear
**Dependencias**: 3.1, 2.2
**Esfuerzo**: baja

**Descripción**:
Función `render_estrategias(state, log_buffer) -> Layout`: predefined strategies table + user strategies table.

**Criterios de verificación**:
1. [ ] Retorna Layout con ambas tablas
2. [ ] Estrategia con `validation: false` muestra ❌ en status

### Tarea 3.5: Crear screens/trades.py

**Archivo**: `src/royaltdn/frontend/console/screens/trades.py`
**Tipo**: crear
**Dependencias**: 3.1, 2.2
**Esfuerzo**: baja

**Descripción**:
Función `render_trades(state, log_buffer) -> Layout`: metrics panel + trades table.

**Criterios de verificación**:
1. [ ] Retorna Layout con trade metrics + trades table
2. [ ] Con 0 trades, muestra empty state

### Tarea 3.6: Crear screens/logs.py

**Archivo**: `src/royaltdn/frontend/console/screens/logs.py`
**Tipo**: crear
**Dependencias**: 3.1, 2.2
**Esfuerzo**: baja

**Descripción**:
Función `render_logs(state, log_buffer, level_filter, module_filter, text_filter) -> Layout`: filter bar mostrando filtros activos + log panel colorizado.

**Criterios de verificación**:
1. [ ] Retorna Layout con filter bar + log panel
2. [ ] Filtros activos se muestran en el filter bar

### Tarea 3.7: Crear commands.py (señales IPC)

**Archivo**: `src/royaltdn/frontend/console/commands.py`
**Tipo**: crear
**Dependencias**: 1.1
**Esfuerzo**: baja

**Descripción**:
Tres funciones que escriben archivos JSON de señal en `logs/`: `pause_bot()`, `resume_bot()`, `trigger_scanner()`. Usar `Path.write_text()` con `json.dumps()`. Cada archivo incluye `action` y `timestamp`.

**Contenido requerido**:
- `pause_bot() -> None` — escribe `logs/pause_signal.json` con `{"action": "pause", "timestamp": "<ISO-8601>"}`
- `resume_bot() -> None` — escribe `logs/pause_signal.json` con `{"action": "resume", "timestamp": "<ISO-8601>"}`
- `trigger_scanner() -> None` — escribe `logs/scanner_trigger.json` con `{"action": "scan_now", "timestamp": "<ISO-8601>"}`
- Asegurar que directorio `logs/` existe

**Criterios de verificación**:
1. [ ] `pause_bot()` crea `logs/pause_signal.json` con JSON válido
2. [ ] `trigger_scanner()` crea `logs/scanner_trigger.json`
3. [ ] JSON generado se puede leer con `json.loads()` y tiene campo `action` y `timestamp`

### Tarea 3.8: Crear app.py (bucle Live + key handling)

**Archivo**: `src/royaltdn/frontend/console/app.py`
**Tipo**: crear
**Dependencias**: 3.1, 3.7, 2.2
**Esfuerzo**: alta

**Descripción**:
Función `run_console()`: inicializa StateLoader, LogBuffer, setup_console_log_handler. Bucle Rich `Live` a 4 FPS con dispatch de pantallas (5 screens vía teclas 1-5). Key capture no bloqueante con `select.select` + timeout 0.25s. Handler para p (pause), r (resume), s (scanner), i/w/e/a (log filters), q (quit). Ctrl+C manejado como 'q'.

**Contenido requerido**:
- `run_console(logs_dir: str = "logs") -> None`
- Inicializar StateLoader, LogBuffer, `setup_console_log_handler(log_buffer)`
- `colorama.init()` al inicio
- `get_key(timeout=0.25) -> str | None` — non-blocking stdin con `select.select`
- `handle_key(key, state)` — dispatcher: '1'..'5' cambia screen, 'p' llama pause_bot, etc.
- `render_screen(screen_id, state, log_buffer, filters)` — dispatcher a los 5 screens
- Bucle `with Live(..., refresh_per_second=4, screen=True) as live:`
- `try/finally` para `colorama.deinit()` en quit

**Criterios de verificación**:
1. [ ] `run_console()` se importa sin errores
2. [ ] `handle_key('1')` cambia screen_id a 1 (dashboard)
3. [ ] `handle_key('p')` llama a `pause_bot()` sin errores
4. [ ] `handle_key('q')` retorna `False` para salir del loop
5. [ ] Ctrl+C no crashea — sale limpiamente

---

## Hito 4: CLI + Orchestrator IPC

### Tarea 4.1: Agregar 6 subcomandos CLI en main.py

**Archivo**: `src/royaltdn/main.py`
**Tipo**: modificar
**Dependencias**: 3.8, 3.7
**Esfuerzo**: alta

**Descripción**:
Reemplazar el CLI actual de 3 comandos por 6 subcomandos: `run`, `status`, `logs`, `pause`, `resume`, `scanner`. `run` inicia Orchestrator en thread daemon + `run_console()` en main thread. `status` y `logs` son one-shot. `pause`/`resume`/`scanner` delegan a commands.py. `python -m royaltdn` sin args imprime help.

**Contenido requerido**:
- `cmd_run()`: `threading.Thread(target=orchestrator.start, daemon=True)` + `run_console()` en main thread
- `cmd_status()`: usa `StateLoader.load_all()`, renderiza dashboard una vez con `rich.print()`, exit 1 si no hay status
- `cmd_logs()`: lee `logs/bot.log` últimas 50 líneas con Rich syntax highlighting
- `cmd_pause()`: `pause_bot()`, `print("⏸️ Pause signal sent")`
- `cmd_resume()`: `resume_bot()`, `print("▶️ Resume signal sent")`
- `cmd_scanner()`: `trigger_scanner()`, `print("🔍 Scanner trigger sent")`
- `main()`: primer `if len(sys.argv) < 2: print(USAGE); sys.exit(1)`
- Mantener compatibilidad: `check` y `run-legacy` siguen funcionando como comandos legacy

**Criterios de verificación**:
1. [ ] `python -m royaltdn` (sin args) imprime help con 8 comandos
2. [ ] `python -m royaltdn status` con `logs/status.json` presente imprime dashboard y exit 0
3. [ ] `python -m royaltdn status` sin `logs/status.json` imprime "Bot OFFLINE" y exit 1
4. [ ] `python -m royaltdn logs` con `logs/bot.log` presente imprime últimas 50 líneas
5. [ ] `python -m royaltdn pause` escribe pause_signal.json
6. [ ] `python -m royaltdn check` sigue funcionando (legacy)

### Tarea 4.2: Modificar Orchestrator para IPC signal polling

**Archivo**: `src/royaltdn/orchestrator.py`
**Tipo**: modificar
**Dependencias**: 1.4 (Loguru migration), 3.7
**Esfuerzo**: media

**Descripción**:
Agregar polling de archivos de señal al inicio de cada iteración en ambos loops (`_main_loop` y `_run_legacy_loop`). Leer `logs/pause_signal.json` para pausar/reanudar, `logs/scanner_trigger.json` para trigger de scanner. Eliminar archivos después de procesar. Si `self.paused` es True, saltar cuerpo principal del loop (seguir publicando status).

**Contenido requerido**:
- Método `_check_signals(self) -> None`:
  - Si `logs/pause_signal.json` existe: parsear action → `self.paused = True/False`, eliminar archivo
  - Si `logs/scanner_trigger.json` existe: `self._scanner.scan()` (si scanner disponible), eliminar archivo
- En `_main_loop`: llamar `_check_signals()` al inicio del `while`
- En `_run_legacy_loop`: llamar `_check_signals()` al inicio del `while`
- Si `self.paused`: `continue` después de publicar status (no ejecutar señales)
- Agregar `self.paused = False` en `__init__`

**Criterios de verificación**:
1. [ ] `_check_signals()` lee pause_signal.json y setea `self.paused`
2. [ ] Después de procesar, pause_signal.json es eliminado
3. [ ] Si `self.paused = True`, el loop salta ejecución de señales
4. [ ] scanner_trigger.json dispara `_scanner.scan()` y se elimina

---

## Hito 5: Cleanup + Tests

### Tarea 5.1: Limpiar imports huérfanos y verificar integración

**Archivo**: N/A (verificación global)
**Tipo**: modificar
**Dependencias**: 4.1, 4.2
**Esfuerzo**: baja

**Descripción**:
Buscar y eliminar cualquier import de `streamlit` o `plotly` que quede en el código fuera de frontend/. Verificar que `builder_state.py` no tenga `import streamlit as st` (ya refactorizado en T1.1). Verificar que todos los imports nuevos son correctos.

**Contenido requerido**:
- `grep -rn "import streamlit\|from streamlit\|import plotly\|from plotly" src/royaltdn/ --include="*.py" | grep -v __pycache__` — debe retornar vacío
- `python -c "from royaltdn.frontend.console.app import run_console; from royaltdn.frontend.console.screens import render_dashboard; from royaltdn.frontend.console.components.widgets import create_header; print('OK')"` — debe funcionar

**Criterios de verificación**:
1. [ ] No hay `import streamlit` ni `import plotly` en `src/royaltdn/`
2. [ ] Todos los imports de los nuevos módulos funcionan

### Tarea 5.2: Crear tests/test_console.py

**Archivo**: `tests/test_console.py`
**Tipo**: crear
**Dependencias**: 4.1, 4.2
**Esfuerzo**: alta

**Descripción**:
Tests para todos los componentes nuevos: StateLoader con archivos JSON temporales, LogBuffer (add/get_lines/filtros/thread-safety), widgets (cada función con datos mock y vacíos), commands (escribe/lee archivos), screens (render con datos mock), key handling.

**Contenido requerido**:
- `test_stateloader_load_all()` — fixture temp dir con JSON files
- `test_stateloader_missing_file()` — default sin crash
- `test_stateloader_corrupt_json()` — warning + default
- `test_stateloader_cache()` — TTL funciona
- `test_logbuffer_add_and_trim()` — 250 adds → 200 max
- `test_logbuffer_get_lines_filter()` — filtro level/module/text
- `test_logbuffer_get_recent()` — últimas N
- `test_logbuffer_thread_safety()` — 10 threads
- `test_widgets_all_functions()` — cada función retorna Panel/Table con datos mock
- `test_widgets_empty_data()` — datos vacíos no crashean
- `test_commands_pause_resume_scanner()` — escribe JSON, se lee de vuelta
- `test_handle_key_screen_switch()` — '1'→dashboard, '2'→scanner, etc.
- `test_handle_key_invalid()` — tecla inválida no crashea

**Criterios de verificación**:
1. [ ] `python -m pytest tests/test_console.py -v` — todos los tests pasan
2. [ ] Cobertura de al menos 15 tests

### Tarea 5.3: Verificación final + run all tests

**Archivo**: N/A
**Tipo**: N/A
**Dependencias**: 5.1, 5.2
**Esfuerzo**: baja

**Descripción**:
Ejecutar todos los tests existentes + test_console.py. Verificar import de todos los módulos nuevos. Verificar CLI commands. Verificar que no haya errores de importación circulares.

**Contenido requerido**:
- `python -m pytest tests/ -v` — todos pasan
- `python -c "from royaltdn.frontend.console.app import run_console; print('Console OK')"`
- `python -m royaltdn status` con archivos JSON existentes
- `python -m royaltdn pause` → verificar que archivo se crea

**Criterios de verificación**:
1. [ ] `python -m pytest tests/ -v` — exit code 0, todos los tests pasan
2. [ ] `python -m royaltdn status` — imprime dashboard y exit 0
3. [ ] No hay errores de importación circular
