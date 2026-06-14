# 3. El Stack Tecnológico Completo: De los Datos al Dinero

---

## 3.0 Visión General del Stack

Este documento es un catálogo exhaustivo de cada herramienta, servicio y biblioteca que compone el ecosistema de un bot de trading profesional. Para cada componente, se justifica su elección, se detallan alternativas, y se proporcionan configuraciones y patrones de uso. El stack está organizado en cinco capas lógicas: Datos, Backtesting/Research, Ejecución en Vivo, Infraestructura/DevOps, y Herramientas de Soporte.

---

## 3.1 Capa de Datos

El combustible del sistema. Sin datos de alta calidad, nada funciona.

### 3.1.1 Proveedores de Datos Históricos y en Tiempo Real

**A. Polygon.io (Recomendado Principal)**
- **Descripción:** Proveedor integral de datos de mercado. Cubre acciones, opciones, forex y cripto.
- **Planes:** Starter ($29/mes) incluye datos en tiempo real (WebSocket) y acceso a históricos tick, minutos y diarios para acciones US. Plan gratuito limitado disponible.
- **API:** REST y WebSocket. Bien documentada, con librerías oficiales en Python (`polygon-api-client`).
- **Ventajas sobre Yahoo Finance:**
  - Datos de splits y dividendos ajustados correctamente (ajuste hacia atrás configurable).
  - Incluye activos delistados (sin sesgo de supervivencia).
  - Tick data real (cada transacción, con timestamp, precio, volumen, bid/ask, condiciones de venta).
  - WebSocket para tiempo real con baja latencia.
- **Desventajas:** Coste mensual. Límites de tasa en planes bajos.

**B. Alpaca Markets Data API**
- **Descripción:** Si usas Alpaca como broker, su API de datos está incluida de forma gratuita (acciones US). No necesitas un proveedor externo para empezar.
- **Cobertura:** Acciones y ETFs en US. Velas 1min, 5min, 15min, 1H, 1D.
- **Streaming:** WebSocket para tiempo real con segundos de retraso en cuenta gratuita, sin retraso en cuenta live.
- **Ventajas:** Unificación de broker + datos en un solo proveedor. Simplicidad inicial.

**C. Interactive Brokers (IB) Data API**
- **Descripción:** A través de su API TWS/IB Gateway, IB proporciona datos de mercado en tiempo real e históricos. La calidad es alta, pero la API es compleja y con limitaciones ("pacing violations" que restringen la frecuencia de peticiones históricas).
- **Recomendación:** Usar la librería `ib_insync` en Python, que simplifica enormemente la interacción.

**D. Yahoo Finance (Solo para Prototipos Iniciales)**
- **Descripción:** Gratuito. Fácil de usar con `yfinance`.
- **Problemas:** Datos de cierre ajustado pueden tener errores. No incluye activos delistados. Sin tick data. Sin soporte oficial. No usar para backtesting final ni para decisiones de producción.

### 3.1.2 Formatos de Datos y Almacenamiento en Frío (Backtesting Masivo)

**A. Apache Parquet (Formato de Archivo)**
- **Descripción:** Formato de almacenamiento columnar, comprimido y muy eficiente para lectura/escritura.
- **Uso ideal:** Almacenar terabytes de datos históricos (tick data, velas de 1 segundo) para backtesting masivo.
- **Ecosistema Python:** Pandas lee y escribe Parquet nativamente (`df.to_parquet()`, `pd.read_parquet()`). Polars es aún más rápido.
- **Esquema de particionado recomendado:** `data/{symbol}/{frequency}/{year}/{month}/{day}.parquet`
  - Ejemplo: `data/SPY/1min/2024/01/02.parquet`
  - Esto permite leer eficientemente solo los datos necesarios para un backtest.

**B. Almacenamiento S3 / MinIO (Repositorio Centralizado)**
- **Amazon S3:** Almacenamiento de objetos en la nube. Barato, escalable, duradero.
- **MinIO:** Servidor de objetos compatible con S3, auto-hospedado (open-source). Ideal para tener tu propio "lago de datos" local o en un VPS.
- **Flujo:** Descargas datos con scripts Python, los guardas localmente en Parquet y los sincronizas a tu bucket S3/MinIO para backup y acceso desde cualquier máquina.

### 3.1.3 Almacenamiento en Caliente (Series Temporales en Producción)

**A. TimescaleDB (Recomendado Principal)**
- **Descripción:** Extensión de PostgreSQL optimizada para series temporales. Combina la potencia y flexibilidad de SQL con la velocidad de inserciones y consultas de bases de datos NoSQL especializadas.
- **Concepto clave: Hypertables.** Una tabla normal de PostgreSQL que TimescaleDB particiona automáticamente por tiempo y por un campo opcional (ej. `symbol`). Las consultas que filtran por tiempo se aceleran drásticamente.
- **Uso ideal:**
  - Almacenar velas de 1 minuto de todos los activos que monitoreas.
  - Registrar todas las órdenes y operaciones (trades) con sus timestamps.
  - Almacenar métricas de TCA (slippage, costes) para análisis posterior.
- **Ventajas:** SQL completo (JOINs, agregaciones, funciones ventana), compresión de datos nativa (ahorra hasta 90% de espacio), políticas de retención automáticas, ecosistema de PostgreSQL (backups, replicación, herramientas de administración).
- **Instalación:** Vía Docker (`timescale/timescaledb:latest-pg15`), imagen oficial con todo listo.

**B. InfluxDB (Alternativa NoSQL)**
- **Descripción:** Base de datos de series temporales NoSQL. Muy rápida para ingestar y consultar métricas.
- **Uso ideal:** Si tu bot es más un generador de métricas (P&L, drawdown) que un sistema con lógica relacional compleja. Su lenguaje de consulta (Flux) es potente pero tiene curva de aprendizaje.
- **Comparación con TimescaleDB:** InfluxDB es más simple para series puras. TimescaleDB es superior si necesitas relacionar trades con velas, hacer joins complejos, o aprovechar la madurez del ecosistema PostgreSQL.

**C. Redis (Almacenamiento Ultra-Caliente / Cache)**
- **Descripción:** Base de datos en memoria. Latencia de microsegundos.
- **Uso ideal:**
  - Almacenar el último tick recibido de cada símbolo.
  - Guardar el estado actual del bot (posición actual, P&L diario).
  - Implementar bloqueos distribuidos y heartbeats.
  - Funcionar como bus de mensajería (Redis Streams) para desacoplar módulos.
- **Persistencia:** Redis puede configurarse para persistir en disco (RDB, AOF), pero su principal valor es la velocidad en memoria.

### 3.1.4 Pipeline de Ingestión en Tiempo Real

**Arquitectura de Ingestión con Redis Streams:**
1.  Un script `ingestor.py` se conecta al WebSocket de Polygon/Alpaca.
2.  Al recibir un tick, lo normaliza a un formato interno estándar (JSON con campos: `symbol`, `timestamp`, `price`, `volume`, `bid`, `ask`).
3.  Publica el JSON en un Redis Stream llamado `raw_ticks`.
4.  (Opcional) Un script `aggregator.py` lee del stream `raw_ticks`, acumula ticks, forma velas de 1 minuto y las publica en otro stream `minute_bars` y las inserta en TimescaleDB.
5.  El motor de señal se suscribe a `minute_bars` (o `raw_ticks` si opera a nivel tick) para generar señales.

**Alternativa: Apache Kafka** para sistemas de muy alta frecuencia o con múltiples consumidores en diferentes ubicaciones. Kafka es superior en rendimiento y durabilidad, pero añade complejidad operativa significativa.

---

## 3.2 Capa de Backtesting e Investigación

### 3.2.1 El Lenguaje: Python y sus Librerías de Análisis

- **Python 3.10+:** El estándar en finanzas cuantitativas por su legibilidad y ecosistema.
- **Pandas:** Para manipulación de datos tabulares. Imprescindible.
- **Polars:** Alternativa a Pandas escrita en Rust, mucho más rápida y con mejor gestión de memoria. Recomendada para datasets grandes (>10M de filas). La sintaxis es similar pero no idéntica.
- **NumPy:** Cálculo numérico vectorizado. Base de casi todo lo demás.
- **Matplotlib / Seaborn / Plotly:** Visualización. Plotly es interactiva y excelente para dashboards de investigación en Jupyter.

### 3.2.2 Frameworks de Backtesting

**A. VectorBT (Vectorized Backtesting)**
- **Enfoque:** Vectorización masiva. En lugar de simular una operación tras otra, calcula todas las operaciones posibles para miles de combinaciones de parámetros en una sola pasada matricial.
- **Fortalezas:**
  - Velocidad extrema para barrido de parámetros y walk-forward analysis.
  - Generación de señales a partir de indicadores técnicos integrados.
  - Métricas de rendimiento y visualizaciones incorporadas.
- **Debilidades:** Menos flexible para lógicas de gestión de riesgo complejas o ejecución realista (aunque soporta slippage y comisiones). Es una herramienta de *investigación*, no un motor de backtesting orientado a eventos.
- **Caso de uso:** "¿Qué combinación de periodos de cruce de medias ha funcionado mejor en los últimos 10 años en SPY, aplicando walk-forward?"

**B. Backtrader (Event-Driven Backtesting)**
- **Enfoque:** Simulación orientada a eventos, similar a cómo opera un bot en vivo. Itera sobre cada barra de datos cronológicamente, llamando a tu función `next()`.
- **Fortalezas:**
  - Lógica de trading más realista: órdenes límite, stops, gestión de cartera.
  - Soporte para múltiples activos y timeframes.
  - Integración con brokers (Alpaca, IB, Oanda) para ejecutar en vivo la misma estrategia backtesteada.
- **Debilidades:** Más lento que VectorBT para barridos de parámetros. La curva de aprendizaje puede ser moderada.
- **Caso de uso:** "Tengo una estrategia con stops dinámicos y trailing stops, quiero backtestearla exactamente como se ejecutará en vivo y luego lanzarla con el mismo código."

**C. QuantConnect / LEAN Engine (Nivel Institucional)**
- **Enfoque:** Plataforma cloud + motor open-source (LEAN). Backtesting y trading en vivo multi-activo.
- **Fortalezas:**
  - Modelado de datos extremadamente realista: ajustes de splits/dividendos automáticos, horarios de mercado exactos, datos tick.
  - Backtesting de carteras completas con lógica de rebalanceo.
  - Acceso a datasets masivos directamente en la nube (sin descargar terabytes).
  - Motor rápido en C# con API de Python.
- **Debilidades:** Curva de aprendizaje más empinada. La versión local requiere Docker. Los costes en la nube pueden escalar si haces backtesting intensivo.
- **Caso de uso:** "Quiero diseñar una estrategia que opera futuros del ES, acciones del SP500 y opciones, con un modelo de ejecución que simule el libro de órdenes."

### 3.2.3 Optimización de Hiperparámetros

- **Optuna:** Framework de optimización bayesiana. Define una función objetivo (ej. Sharpe ratio de tu backtest) y un espacio de búsqueda de parámetros. Optuna explora inteligentemente el espacio, podando automáticamente combinaciones malas. Es muy superior a una simple búsqueda en cuadrícula (grid search).
- **Hiperopt:** Popular en la comunidad de Freqtrade (bot de cripto). Basado en el algoritmo TPE (Tree-structured Parzen Estimator), similar al que usa Optuna internamente.

### 3.2.4 Análisis de Rendimiento

- **QuantStats:** Genera informes HTML profesionales con todas las métricas clave (Sharpe, Sortino, Calmar, drawdowns, análisis de rachas, distribuciones de retorno, heatmaps mensuales). Ideal para documentar tus resultados de backtest.
- **Pyfolio:** Creado por Quantopian. Excelente para la atribución de rendimiento a factores (modelo de Fama-French), análisis de exposición sectorial y desglose de P&L por evento.

---

## 3.3 Capa de Ejecución en Vivo

### 3.3.1 Brokers y Exchanges (Conectividad)

**A. Alpaca Markets (Acciones USA - Ideal para empezar)**
- **API:** REST para operaciones, WebSocket para datos en tiempo real.
- **Librería Python:** `alpaca-py` (oficial, asíncrona y síncrona).
- **Paper Trading:** Entorno de simulación gratuito con dinero ficticio. La API es idéntica al entorno real.
- **Soporte:** Órdenes de mercado, límite, stop, stop-limit, bracket orders (take profit + stop loss nativos).

**B. Interactive Brokers (Multi-activo - Profesional)**
- **API:** A través de TWS (Trader Workstation) o IB Gateway. Protocolo nativo complejo.
- **Librería Python:** `ib_insync` (wrapper moderno y asíncrono, muy recomendado). Simplifica la conexión, el manejo de eventos y la gestión de órdenes.
- **Ventajas:** Acceso a prácticamente todos los mercados del mundo (acciones, futuros, opciones, forex, bonos). Cuentas IRA disponibles. Ejecución de alta calidad.

**C. CCXT (Criptomonedas)**
- **Descripción:** Librería unificada que proporciona una API consistente para operar en más de 100 exchanges de criptomonedas (Binance, Coinbase, Bybit, Kraken, etc.).
- **Funcionalidad:** Conexión a WebSockets, descarga de históricos, ejecución de órdenes, consulta de balances.
- **Imprescindible** si tu bot opera en mercados cripto.

### 3.3.2 Arquitectura del Bot en Vivo (Diseño Modular)

La arquitectura ideal separa las preocupaciones en procesos o hilos independientes que se comunican a través de un bus de mensajes. Esto permite escalar, depurar y mantener cada componente por separado.

**Módulo 1: DataFeedHandler (Ingestor)**
- **Responsabilidad:** Mantener una conexión WebSocket con el proveedor de datos. Recibir ticks/velas, normalizarlos y publicarlos en el bus de datos (Redis Stream).
- **Lógica de reconexión:** Si la conexión se cae, reintentar automáticamente con backoff exponencial.
- **Heartbeat:** Si no se reciben datos en N segundos, emitir una alerta.

**Módulo 2: StrategyEngine (Motor de Señal)**
- **Responsabilidad:** Suscribirse al bus de datos para el(los) activo(s) de interés. Mantener el estado de los indicadores/features. Evaluar las condiciones de entrada/salida. Publicar señales en el stream `signals`.
- **Estado:** Debe ser "stateless" respecto a la ejecución, pero "stateful" respecto a los indicadores (ej. necesita las últimas 20 velas para calcular la media móvil).
- **Señal:** Un mensaje JSON con: `{ "symbol": "SPY", "action": "BUY", "timestamp": 1716588000, "source": "sma_cross" }`.

**Módulo 3: RiskManager (Gestor de Riesgo)**
- **Responsabilidad:** Suscribirse al stream `signals`. Para cada señal, consultar el estado actual de la cuenta y posiciones, y aplicar las reglas de riesgo. Si la señal es aprobada, publica una `approved_signal` o la envía directamente al O/EMS.
- **Fuentes de datos de riesgo:** API del broker (equity, posiciones), Redis (P&L diario calculado, estado de kill switches).
- **Lógica de kill switch:** Este módulo puede cerrar posiciones unilateralmente si detecta una violación de límites.

**Módulo 4: ExecutionManager (O/EMS)**
- **Responsabilidad:** Recibir `approved_signals`. Decidir el algoritmo de ejecución (mercado, límite, TWAP). Enviar órdenes al broker. Monitorizar el estado de las órdenes (parcialmente ejecutadas, completadas, rechazadas). Actualizar el estado de la posición en Redis/BD.
- **Gestión de órdenes bracket:** Si el broker las soporta, enviar la orden de entrada con take profit y stop loss adjuntos. Si no, implementar una lógica propia que monitoree el precio y envíe las órdenes de cierre cuando corresponda.

### 3.3.3 Comunicación Inter-Módulos: Redis Streams

**Patrón de uso:**
- El ingestor es un **productor** del stream `market_data`.
- El motor de señal es un **grupo de consumidores** del stream `market_data`.
- El motor de señal es un **productor** del stream `signals`.
- El risk manager es un **grupo de consumidores** del stream `signals`.
- El risk manager publica en `approved_signals` o llama directamente a una función del O/EMS.

**Ventajas:**
- **Desacoplamiento:** Si el motor de señal se reinicia, los mensajes se acumulan en el stream y se procesan desde el último ID confirmado.
- **Escalabilidad:** Puedes tener múltiples instancias del motor de señal para distintos activos, todas consumiendo del mismo stream.
- **Observabilidad:** Puedes inspeccionar el stream en cualquier momento para ver qué señales se están generando.

---

## 3.4 Capa de Infraestructura, DevOps y Monitorización

### 3.4.1 Contenerización con Docker

**Conceptos clave:**
- **Dockerfile:** Archivo de texto que define cómo construir una imagen (sistema operativo base + dependencias + código).
- **Imagen:** Artefacto inmutable que contiene todo lo necesario para ejecutar tu bot.
- **Contenedor:** Instancia en ejecución de una imagen. Aislado del sistema host.

**Ventajas:**
- **Reproducibilidad:** "En mi máquina funciona" deja de ser un problema.
- **Despliegues inmutables:** No modificas código en servidores de producción; despliegas una nueva imagen y reemplazas el contenedor.
- **Ecosistema:** Docker Compose para entornos multi-contenedor locales, Kubernetes para producción a gran escala.

**Dockerfile de ejemplo para un módulo del bot (Fase 3):**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

```
# Instalar dependencias del sistema si son necesarias (ej. compiladores)

RUN apt-get update && apt-get install -y --no-install-recommends gcc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src /app/src

CMD ["python", "src/main.py"]

3.4.2 Orquestación y Despliegue Continuo (CI/CD)

· Docker Compose: Herramienta para definir y ejecutar aplicaciones Docker multi-contenedor. Un archivo docker-compose.yml define todos los servicios (bot, Redis, TimescaleDB, Grafana) y sus relaciones. Perfecto para desarrollo y VPS únicos.
· GitHub Actions / GitLab CI: Sistema de CI/CD. Permite definir pipelines que se ejecutan automáticamente en la nube tras eventos de Git (push, pull request).
· Pipeline de ejemplo:
  1. Checkout del código.
  2. Setup de Python, instalación de dependencias.
  3. Linting (Ruff/Flake8) y type checking (MyPy).
  4. Unit tests con pytest.
  5. Smoke backtest (script que ejecuta un backtest corto y verifica que no haya errores de lógica).
  6. Build de la imagen Docker.
  7. Push de la imagen a un registro (Docker Hub, GitHub Container Registry).
  8. Deploy: Conectarse por SSH al VPS, hacer pull de la nueva imagen y reiniciar el contenedor.

3.4.3 Monitorización y Observabilidad

A. Prometheus + Grafana (Métrica)

· Prometheus: Sistema de monitoreo que recolecta métricas (contadores, gauges, histogramas) de tus aplicaciones. Tu bot expone un endpoint HTTP (/metrics) con librerías como prometheus_client de Python.
· Grafana: Plataforma de dashboards que se conecta a Prometheus (y muchas otras fuentes) para visualizar las métricas en gráficos de series temporales.
· Ejemplos de métricas a exponer:
  · bot_pnl_realized_total (contador de P&L realizado).
  · bot_positions_open (gauge del número de posiciones abiertas).
  · bot_order_latency_seconds (histograma de latencia de las órdenes).
  · broker_api_errors_total (contador de errores de API).

B. ELK Stack / Grafana Loki (Logs)

· Elasticsearch, Logstash, Kibana (ELK): Stack tradicional de centralización de logs. Pesado pero muy potente.
· Grafana Loki: Alternativa ligera inspirada en Prometheus para logs. Integración nativa con Grafana, lo que permite tener dashboards con métricas y logs en una sola interfaz.
· Práctica recomendada: Emitir logs en formato JSON estructurado desde Python. Incluir siempre timestamp, level, logger, message y cualquier contexto relevante (ej. symbol, order_id). Ejemplo: {"timestamp": "2024-...", "level": "INFO", "logger": "risk.manager", "message": "Signal rejected", "symbol": "SPY", "reason": "daily_loss_limit"}.

C. Alertas

· Grafana Alerting: Definir reglas en Grafana (ej. "si bot_drawdown_current > 5 envía alerta"). Soporta múltiples canales: Telegram, Slack, email, PagerDuty.
· Alertas desde el código: Para condiciones críticas que requieren notificación inmediata sin esperar al ciclo de scrapeo de Prometheus, enviar un mensaje directamente desde el código del bot usando python-telegram-bot o un webhook de Slack.

3.4.4 Chaos Engineering (Resiliencia Probada)

La práctica de experimentar en el sistema para generar fallos y ver cómo responde.

· Desconexión de red: Cortar la red del contenedor del bot y verificar que el watchdog cierra posiciones.
· Saturación de recursos: Limitar la CPU/memoria del contenedor y verificar que el bot se degrada controladamente.
· Inyección de datos corruptos: Publicar un mensaje malformado en el stream de Redis y ver que el consumidor no crashea, sino que registra el error y continúa.

---

3.5 Herramientas de Soporte

· JupyterLab: Entorno interactivo para análisis exploratorio de datos, creación de prototipos de estrategias y visualización.
· DVC (Data Version Control): Versiona datasets y modelos junto con el código Git. Permite hacer dvc checkout para restaurar los datos exactos de un experimento pasado.
· MLflow: Plataforma para gestionar el ciclo de vida de modelos de machine learning. Tracking de experimentos (parámetros, métricas, artefactos) y registro de modelos. Ideal si tu estrategia utiliza ML.
· GitHub Copilot / ChatGPT: Asistentes de código. Útiles para acelerar la escritura de boilerplate y consultar dudas técnicas, pero no para generar estrategias completas sin entenderlas y validarlas.

---

Continúa en los documentos de implementación práctica (04, 05, 06) y el cierre del roadmap (07).

```

---
