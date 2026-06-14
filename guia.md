
GUÍA COMPLETA: CONSTRUCCIÓN DE UN BOT DE TRADING ALGORÍTMICO RENTABLE

Del concepto a la operación profesional – Stack, Metodología y Ruta de Implementación

Autor: Basado en la experiencia de un Trader Algorítmico Profesional
Versión: 1.0
Fecha: Junio 2026
Descargo de responsabilidad: Este documento tiene fines educativos. No constituye asesoramiento financiero. El trading algorítmico conlleva riesgos sustanciales de pérdida de capital. Todo el conocimiento aquí expuesto debe ser validado por el lector en entornos de simulación antes de operar con capital real.

---

Índice de contenidos

1. Introducción: Más Allá del Código
2. Principios Fundamentales de un Bot Rentable
   · 2.1 Alfa Real, No Ruido Sobreajustado
   · 2.2 Backtesting con Realismo Quirúrgico
   · 2.3 Gestión de Riesgo como Jefe Supremo
   · 2.4 Ejecución Inteligente
   · 2.5 Resiliencia Operativa 24/7
   · 2.6 Monitorización y Gobierno Constante
3. El Stack Tecnológico Completo (De los Datos al Dinero)
   · 3.1 Capa de Datos
   · 3.2 Motor de Backtesting e Investigación
   · 3.3 Ejecución en Vivo (El Corazón)
   · 3.4 Infraestructura, DevOps y Monitorización
   · 3.5 Herramientas de Soporte y Analítica Complementaria
   · 3.6 Diagrama de Arquitectura de Alto Nivel
4. Ruta de Implementación Paso a Paso (Desde Cero)
   · 4.1 Fase 0: Los Cimientos (1-2 Semanas)
   · 4.2 Fase 1: Tu Primer Bot Caminando (2-4 Semanas)
   · 4.3 Fase 2: Del Juguete al Laboratorio de Investigación (1-3 Meses)
   · 4.4 Fase 3: Infraestructura de “Mesa de Trading” Personal (3-6 Meses)
   · 4.5 Fase 4: El Salto Profesional – Datos y Ejecución Avanzada (6+ Meses)
5. Códigos de Ejemplo Funcionales
   · 5.1 Backtest Vectorizado Básico (Pandas)
   · 5.2 Backtest Profesional con Walk-Forward (VectorBT)
   · 5.3 Bot en Vivo con Alpaca (Python)
   · 5.4 Dockerfile para el Bot
6. Lista de Herramientas, Enlaces y Referencias
7. Conclusión Final: La Mentalidad del Negocio

---

1. Introducción: Más Allá del Código

Ser rentable con un bot de trading no es acertar una vez, ni encontrar el "Santo Grial" de los indicadores. Es construir un negocio sistemático que sobreviva a cientos de regímenes de mercado sin que el factor suerte lo arruine. Desde la perspectiva de un trader profesional que lleva años viviendo de esto, la rentabilidad sostenible se basa en un sistema integral donde la estrategia es solo una pieza más.

Lo que realmente marca la diferencia es la ingeniería del proceso: el stack tecnológico, los controles de riesgo y la cultura de desarrollo riguroso. Este documento te guiará a través de cada componente, desde los principios abstractos hasta la ruta de implementación concreta, para que puedas construir tu propio sistema de trading algorítmico profesional.

---

2. Principios Fundamentales de un Bot Rentable

Un bot es rentable si cumple estos requisitos antes de poner un solo euro real:

2.1 Alfa Real, No Ruido Sobreajustado

La señal debe capturar una ineficiencia persistente (microestructura, flujo de órdenes, comportamiento institucional, factores de riesgo con prima) y no simplemente memorizar el pasado. Una estrategia basada en un indicador RSI optimizado en 10 años de datos diarios casi seguro es ruido. Un ejemplo de alfa real sería detectar absorción pasiva en el libro de órdenes usando datos tick a tick y reaccionar en milisegundos. El foco debe estar en la lógica económica o de comportamiento detrás de la señal, no en la optimización paramétrica extrema.

2.2 Backtesting con Realismo Quirúrgico

El backtesting no es un mero trámite, es tu auditor. Debe ser una simulación casi perfecta de la realidad, incluyendo:

· Datos punto a punto: Usa tick data o al menos velas de segundos que incluyan el bid y el ask reales. No uses velas diarias ajustadas sin más.
· Simulación de microestructura: Debes modelar colas de órdenes, latencia, slippage variable según volatilidad y, crucialmente, el market impact (si metes una orden grande, el precio se mueve en tu contra).
· Walk-Forward Analysis: Optimización rodante. Optimizas parámetros en una ventana de datos (in-sample), los validas en la siguiente ventana sin reoptimizar (out-of-sample) y repites el proceso avanzando en el tiempo. Así detectas el sobreajuste.
· Periodo completamente ciego: Separa un pedazo de los datos más recientes que jamás tocarás hasta el final de tu investigación. Si tu bot falla ahí, se descarta sin miramientos, por mucho que brillara en el backtest.

2.3 Gestión de Riesgo como Jefe Supremo

No importa lo buena que sea la señal si una racha de varianza negativa te saca del juego. El bot debe llevar un módulo de riesgo independiente y no negociable que:

· Ajuste el tamaño de posición por volatilidad (ej. usando ATR o Bandas de Keltner).
· Controle la correlación entre activos: No sobrecargar el mismo factor de riesgo inadvertidamente.
· Establezca Kill Switches: Límites de pérdida diaria, drawdown intradiario y número de operaciones fallidas consecutivas que, al alcanzarse, apagan el bot automáticamente.
· Calcule el VaR o Expected Shortfall antes de cada entrada para conocer la pérdida máxima esperada en un escenario adverso.

2.4 Ejecución Inteligente

Una market order rara vez es la mejor opción. Un bot profesional fragmenta órdenes grandes para minimizar el impacto (algoritmos TWAP, VWAP, Iceberg), aprovecha la liquidez oculta y evita ser depredado por operadores de alta frecuencia. Incluso en retail, usar órdenes límite con lógica de reposicionamiento según el spread puede ahorrar medio tick por operación. Ese medio tick, compuesto anualmente, es la diferencia entre un bot perdedor y uno ganador.

2.5 Resiliencia Operativa 24/7

Si el bot es tu negocio, no puede caerse. Si se va Internet, debe detenerse limpiamente o tener redundancia en la nube. Si el broker rechaza una orden, el sistema no puede quedarse con una posición huérfana. Toda excepción debe generar una alerta y, de ser posible, un procedimiento de reconciliación automática. La tolerancia a fallos no es opcional, es un requerimiento de negocio.

2.6 Monitorización y Gobierno Constante

La rentabilidad de un bot no es estática; los regímenes de mercado cambian. Necesitas dashboards que comparen la ejecución real contra el backtest (métricas de slippage, ratio de rechazos, latencia) y que monitoricen el deterioro de la señal. La regla de oro: si el Sharpe Ratio semanal de tu bot cae por debajo de un umbral durante X semanas, el bot se apaga automáticamente para revisión humana.

---

3. El Stack Tecnológico Completo (De los Datos al Dinero)

Aquí se detalla la arquitectura utilizada en mesas profesionales y adaptada para un trader independiente serio.

3.1 Capa de Datos

· Históricos de calidad institucional:
  · Proveedores gratuitos/de pago: Polygon.io, IEX Cloud, Alpaca Data API, Intraday de Bloomberg/Refinitiv (si el presupuesto lo permite).
  · Datos ajustados por splits y dividendos, con vigilancia de sesgos de supervivencia (siempre incluye empresas que quebraron).
· Datos en tiempo real: WebSockets del broker (Interactive Brokers, Alpaca) o fuentes especializadas como IEX TOPS o Polygon WebSocket.
· Almacenamiento:
  · Series temporales: TimescaleDB (PostgreSQL con hypertables para time-series) o InfluxDB.
  · Datos crudos (tick data): Archivos en formato Parquet en almacenamiento local o S3/MinIO para backtesting masivo.
  · Metadata de activos: PostgreSQL tradicional.
· Pipeline de limpieza e ingestión: Apache Kafka o Redis Streams para la ingestión en tiempo real, normalizando y enriqueciendo datos antes de que lleguen al motor de trading.

3.2 Motor de Backtesting e Investigación

· Lenguaje base: Python es el estándar de facto por su ecosistema. Sus librerías principales son pandas, NumPy y Polars (para mayor velocidad). Para simulación de microestructura de alta frecuencia se puede recurrir a C++ o Rust.
· Frameworks:
  · VectorBT: Ideal para prototipado vectorizado ultrarápido y optimización de parámetros.
  · Backtrader o Zipline-Reloaded: Motores orientados a eventos, con lógica de cartera y gestión de órdenes más realista.
  · QuantConnect (LEAN Engine): La opción más profesional. Plataforma en la nube y motor open source para ejecutar en local. Incluye datos, backtesting multi-activo y ejecución en vivo.
· Optimización de parámetros: Librerías como Optuna o Hyperopt, aplicando validación cruzada temporal (nunca K-Fold estándar) y penalizando la complejidad excesiva.
· Análisis de estrategia: QuantStats (informes completos de Sharpe, drawdown, análisis de regímenes), Pyfolio y gráficos de decay de factores para monitorizar la salud de la señal.

3.3 Ejecución en Vivo (El Corazón)

· Plataforma de trading (Brokers con API):
  · Interactive Brokers (API nativa vía ib_insync en Python o protocolo FIX). Profesional y completo.
  · Alpaca Markets (API REST y WebSocket moderna, ideal para empezar y para acciones USA).
  · CCXT para unificar el acceso a múltiples exchanges de cripto (Binance, Bybit, Coinbase, etc.).
· Arquitectura del bot en producción:
  · Procesos separados con comunicación asíncrona (Redis pub/sub, RabbitMQ o colas internas de Python):
    1. Ingesta de Datos: Escucha y normaliza market data.
    2. Motor de Señal: Calcula el alfa y genera órdenes de entrada/salida.
    3. Gestor de Riesgo: Recibe las señales y valida la exposición antes de aprobarlas.
    4. O/EMS (Order/Execution Management System): Genera, envía, modifica y cancela las órdenes aprobadas en el broker.
  · Ejemplo en Python: asyncio combinado con ib_insync permite manejar docenas de instrumentos sin perder un tick.
· Módulo de riesgo independiente: Corre como un proceso separado vigilando el P&L a nivel de cuenta y posición en tiempo real. Si se supera un límite preestablecido, emite una orden de cierre de emergencia directa a la API del broker, pasando por encima de cualquier otra lógica. Implementa un heartbeat: si el motor de señal no responde en N segundos, se cancelan todas las órdenes activas.

3.4 Infraestructura, DevOps y Monitorización

· Despliegue:
  · Contenedores Docker para cada módulo, garantizando entornos idénticos en desarrollo y producción.
  · Orquestación con Docker Compose para entornos locales/staging, y Kubernetes si se necesita alta disponibilidad en la nube.
  · CI/CD (GitHub Actions / GitLab CI): Pipeline que, al hacer push, ejecuta tests unitarios y un backtest rápido. Si pasa, construye la imagen Docker y despliega automáticamente en el entorno de paper trading.
· Monitorización:
  · Logs: Estructurados en formato JSON y centralizados en Elasticsearch, visualizándolos con Kibana.
  · Métricas en tiempo real: Prometheus para recolectar y Grafana para visualizar dashboards con latencia de señal, P&L, exposición, órdenes rechazadas, drawdown intradiario.
  · Alertas: Sistema de notificaciones por Telegram, Slack o email para eventos críticos: desconexión del broker, drawdown superior al umbral, errores en API, discrepancia de posición.
· Simulador de caídas y Chaos Engineering: Pruebas periódicas que desconectan la red, saturan la CPU o inyectan datos corruptos para verificar que el sistema falla de forma controlada (cierres de emergencia, cancelación de órdenes) y no causa pérdidas descontroladas.

3.5 Herramientas de Soporte y Analítica Complementaria

· TCA (Transaction Cost Analysis): Proceso que compara tu precio de ejecución real contra el arrival price (precio medio del mercado en el momento de la decisión) o el VWAP. Es indispensable para medir el slippage y optimizar los algoritmos de ejecución.
· Entorno de investigación: JupyterLab/Notebooks para análisis ad-hoc, feature engineering y visualización de datos.
· Control de versiones de modelos: No solo versionas código con Git, sino también los datasets, parámetros de backtest y modelos. Herramientas como DVC (Data Version Control) o MLflow registran cada experimento para garantizar la reproducibilidad total.

3.6 Diagrama de Arquitectura de Alto Nivel

```
+-------------------------------------------------------------------+
|                    MONITOREO CONTINUO (Grafana)                    |
+-------------------------------------------------------------------+
        ^                ^                ^              ^
        |                |                |              |
+-------+------+  +------+------+  +------+------+  +-----+------+
| Ing. Datos   |  | Motor Señal |  | Gest. Riesgo|  |  Broker    |
| (WebSocket)  +->| (Estrateg.) +->| (VaR, Kill) +->|  API       |
|              |  |             |  |             |  | (Alpaca/IB)|
+--------------+  +------+------+  +------^------+  +-----+------+
                          |                |              ^
                          +-------+--------+              |
                                  |  (Redis Streams)      |
                          +-------v--------+              |
                          |   O/EMS        +--------------+
                          | (Ordenes TWAP, |
                          |  Bracket, etc.)|
                          +----------------+
```

---

4. Ruta de Implementación Paso a Paso (Desde Cero)

Nadie construye este stack de golpe. Esta es tu guía para pasar de cero a un bot semi‑profesional de forma orgánica. Tu objetivo inicial es lograr un MVP (Producto Mínimo Viable) que complete el ciclo de trading.

4.1 Fase 0: Los Cimientos (1-2 Semanas)

Sin esto, no hay nada que hacer. No te saltes ni un punto.

· Requisitos:
  · Python básico (pandas, bucles, funciones, instalar librerías).
  · Conceptos de mercado: vela OHLCV, bid/ask, orden limitada y de mercado.
· Acciones Inmediatas:
  1. Abrir cuenta en broker con API: Alpaca Markets (gratis en papel, API moderna) o Interactive Brokers (más profesional y compleja).
  2. Configurar entorno de desarrollo: Instalar Python, crear un entorno virtual e instalar las librerías base: pip install alpaca-py pandas numpy matplotlib yfinance vectorbt backtrader.
  3. Escribir tu primer script: Usar yfinance para descargar 5 años de datos diarios del SPY y pintar un gráfico de precio. El objetivo es solo probar el flujo de obtener datos y visualizarlos.

4.2 Fase 1: Tu Primer Bot Caminando (2-4 Semanas)

Construye el ciclo completo más simple: señal → backtest manual → ejecución en papel automática.

1. Idea Simple: Coge una regla que entiendas (ej. "precio > media móvil de 20 periodos → comprar").
2. Backtest "de andar por casa" en Jupyter: Implementa la lógica en un notebook con pandas. Calcula las señales, los retornos de la estrategia y dibuja la curva de capital. Esto te enseña los sesgos básicos (shift de la señal, comisiones manuales).
3. Bot en Vivo (Paper Trading): Crea un script que, en un bucle o por WebSocket, obtenga el último precio, calcule la señal y envíe una orden de mercado a Alpaca cuando haya un cambio. La manera más rápida es usar el soporte para "live trading" de Backtrader, que abstrae gran parte de la complejidad.

Meta de la Fase 1: Tener un bot que opere automáticamente en papel durante al menos una semana sin errores.

4.3 Fase 2: Del Juguete al Laboratorio de Investigación (1-3 Meses)

Añade las primeras capas profesionales para no depender de la suerte.

1. Backtesting Serio: Usa VectorBT para aplicar walk‑forward analysis. Optimiza parámetros en una ventana de tiempo y valídalos en la siguiente. Si la curva de capital fuera de muestra se desploma, tu idea inicial era ruido.
2. Gestor de Riesgos Básico: Introduce condicionales if en tu bot para que:
   · No arriesgue más del 2% del capital por operación.
   · Tenga un stop loss fijo (ej. 1 ATR) y un take profit.
   · Se detenga si el drawdown diario supera el 3% (kill switch diario).
3. Monitorización Rudimentaria:
   · Logs: Registra cada operación (timestamp, activo, precio, tamaño, P&L) en un archivo CSV.
   · Alertas: Crea un bot de Telegram simple que te notifique cada entrada, salida y error (librería python-telegram-bot).

Meta de la Fase 2: Tu bot no es ciego. Controla el riesgo, se apaga en emergencias y tienes un registro para auditar qué hace.

4.4 Fase 3: Infraestructura de “Mesa de Trading” Personal (3-6 Meses)

Separa los procesos y prepara tu sistema para ser robusto y escalable.

1. Dockerización: Aprende lo mínimo de Docker y escribe un Dockerfile para tu bot. Ahora se ejecutará igual en tu PC, un servidor en la nube o una Raspberry Pi. Ventaja: despliegues inmutables y controlados.
2. Base de Datos: Sustituye los CSVs por TimescaleDB (PostgreSQL para time-series). Almacena velas de mercado históricas y el registro de todas tus órdenes y ejecuciones. Podrás hacer consultas SQL avanzadas para analizar tu rendimiento.
3. Dashboards (Opcional pero muy potente): Conecta Grafana a tu base de datos TimescaleDB para visualizar la curva de P&L, drawdown y exposición en tiempo real. Deja de mirar logs; mira un dashboard.
4. CI/CD Mínimo: Crea un repositorio en GitHub y configura GitHub Actions para que, al hacer push, se ejecuten tests y un backtest de smoke test. Si pasa, se despliega automáticamente en tu entorno de paper trading. Esto te da una disciplina de código y evita despliegues fallidos.

Meta de la Fase 3: Tu sistema se despliega con un comando git push, almacena todo en una base de datos profesional y se monitoriza con dashboards. Tu base ya está lista para estrategias complejas.

4.5 Fase 4: El Salto Profesional – Datos y Ejecución Avanzada (6+ Meses)

Una vez domines el ciclo completo, añades lo que realmente separa un bot amateur de uno rentable.

1. Datos de Alta Calidad: Abandona los datos de Yahoo Finance. Contrata Polygon.io o usa los datos en tiempo real de Interactive Brokers. Almacena ticks en tu base de datos y rehaz tus backtests con esos datos, simulando el spread real y el impacto de mercado.
2. Motor de Backtesting Orientado a Eventos: Frameworks como el motor open-source LEAN (QuantConnect) son el estándar. Te permiten backtestear con lógica de libro de órdenes, horarios de mercado exactos y datos tick.
3. Ejecución Inteligente: Programa un pequeño algoritmo de ejecución TWAP o VWAP. En lugar de lanzar una orden de compra de 1000 acciones de golpe, la fragmentas en lotes de 100 usando órdenes límite que persiguen el bid. Usa órdenes Bracket (take profit y stop loss nativos en el servidor del broker) para que el riesgo esté gestionado a nivel de infraestructura.
4. TCA (Transaction Cost Analysis): Implementa un proceso que compare tu precio de ejecución real contra el precio medio del mercado en el momento de la decisión. Esta métrica te dirá si tu alfa se lo está comiendo el slippage.

Meta Final de la Fase 4: Has construido un sistema de trading algorítmico de grado profesional que puede gestionar capital real con un control de riesgo y una infraestructura robusta.

---

5. Códigos de Ejemplo Funcionales

5.1 Backtest Vectorizado Básico (Pandas)

El primer backtest que deberías ejecutar. Simple, didáctico y ejecutable en un Jupyter Notebook.

```python
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. Obtener datos
df = yf.download("SPY", start="2018-01-01")

# 2. Calcular señal (Ej: Media Móvil 20 vs Precio)
df['MA20'] = df['Close'].rolling(20).mean()
df['signal'] = 0
df.loc[df['Close'] > df['MA20'], 'signal'] = 1   # Largo
df.loc[df['Close'] <= df['MA20'], 'signal'] = -1  # Corto

# 3. Calcular retornos de la estrategia (CUIDADO con el sesgo: usamos shift(1))
df['returns'] = df['Close'].pct_change()
df['strategy_returns'] = df['signal'].shift(1) * df['returns']

# 4. Calcular curvas de capital y gráfico
cumulative_market = (1 + df['returns']).cumprod()
cumulative_strategy = (1 + df['strategy_returns']).cumprod()

plt.figure(figsize=(10,6))
cumulative_market.plot(label='Buy & Hold SPY')
cumulative_strategy.plot(label='Estrategia MA20')
plt.legend()
plt.title('Backtest Simple - Media Móvil vs Buy & Hold')
plt.show()
```

5.2 Backtest Profesional con Walk-Forward (VectorBT)

VectorBT permite un análisis mucho más profundo en muy pocas líneas.

```python
import vectorbt as vbt
import numpy as np

# 1. Descargar datos con el propio conector de VectorBT
data = vbt.YFData.download("SPY", start="2015-01-01").get('Close')

# 2. Definir el indicador y parámetros a optimizar
fast_ma = vbt.MA.run(data, window=np.arange(5, 50, 5))
slow_ma = vbt.MA.run(data, window=np.arange(50, 200, 25))

# 3. Generar entradas y salidas (cruce de medias)
entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

# 4. Construir el portfolio con Walk-Forward Analysis
# Dividimos los datos en 4 ventanas deslizantes para optimización
portfolio = vbt.Portfolio.from_signals(
    data, 
    entries, 
    exits, 
    freq='D',              # Frecuencia de las velas
    cash=10000,            # Capital inicial
    commission=0.001,      # Comisión del 0.1%
    slippage=0.001,        # Slippage del 0.1%
    freq_anchor='1D',
    # Configuración del Walk-Forward
    optimization_options=dict(
        split=4,                         # Número de ventanas
        split_value=np.linspace(0.5, 1.0, 5) # Proporción in-sample/out-of-sample
    )
)

# 5. Ver resultados estadísticos del mejor par in-sample aplicado al out-of-sample
print(portfolio.stats())
portfolio.plot().show()
```

5.3 Bot en Vivo con Alpaca (Python)

Estructura básica de un bot que opera el cruce de medias con gestión de riesgo. Utiliza asyncio y la API oficial de Alpaca Markets.

```python
import asyncio
import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
from datetime import datetime, timedelta

# Configuración de API Keys (desde variables de entorno, ¡NUNCA en el código!)
API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")
SYMBOL = "SPY"
QTY = 1  # Cantidad pequeña para pruebas en papel

trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# Variable de estado global (en un sistema real, se guarda en BD)
current_position = None

async def get_signal(symbol):
    """Calcula la señal basada en el cruce de medias móviles."""
    # Obtener datos históricos (últimos 30 días)
    end = datetime.now()
    start = end - timedelta(days=30)
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end
    )
    bars = data_client.get_stock_bars(request_params)
    df = bars.df.droplevel(0)  # Limpiar multiíndice si es necesario

    # Calcular medias
    df['MA_5'] = df['close'].rolling(5).mean()
    df['MA_20'] = df['close'].rolling(20).mean()

    # Generar señal (1 = Largo, -1 = Corto, 0 = Sin posición)
    if df['MA_5'].iloc[-1] > df['MA_20'].iloc[-1]:
        return 1
    else:
        return -1

async def execute_order(side):
    """Envía una orden de mercado al broker."""
    order_data = MarketOrderRequest(
        symbol=SYMBOL,
        qty=QTY,
        side=side,
        time_in_force=TimeInForce.DAY
    )
    order = trading_client.submit_order(order_data)
    print(f"Orden enviada: {side} {SYMBOL} - ID: {order.id}")
    return order

async def main():
    global current_position
    print("Bot de Paper Trading Iniciado...")
    while True:
        try:
            # 1. Calcular señal
            signal = await get_signal(SYMBOL)

            # 2. GESTIÓN DE RIESGO SIMPLIFICADA
            # Obtener equity y calcular P&L del día para kill switch (simplificado)
            account = trading_client.get_account()
            equity = float(account.equity)
            # last_equity = float(account.last_equity)  # Para un cálculo más preciso
            
            # Ejemplo: Si el drawdown intradiario supera el 3%, detener el bot
            # if (last_equity - equity) / last_equity > 0.03:
            #     print("KILL SWITCH ACTIVADO: Drawdown > 3%. Bot detenido.")
            #     break

            # 3. Actuar según la señal y la posición actual
            if signal == 1 and current_position != 'long':
                # Si había corto, cerrar primero
                if current_position == 'short':
                    await execute_order(OrderSide.BUY) # Cubrir el corto
                    current_position = None
                # Abrir largo
                await execute_order(OrderSide.BUY)
                current_position = 'long'
                print(f"Posición Actual: {current_position}")

            elif signal == -1 and current_position != 'short':
                if current_position == 'long':
                    await execute_order(OrderSide.SELL) # Vender el largo
                    current_position = None
                await execute_order(OrderSide.SELL) # Abrir corto
                current_position = 'short'
                print(f"Posición Actual: {current_position}")

            # Esperar 1 minuto antes de la siguiente iteración
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Error en el bucle principal: {e}")
            # En caso de error grave, cerrar todas las posiciones como medida de seguridad
            # trading_client.close_all_positions()
            await asyncio.sleep(10)  # Esperar antes de reintentar

if __name__ == "__main__":
    asyncio.run(main())
```

5.4 Dockerfile para el Bot

Un Dockerfile simple para empaquetar el bot anterior.

```dockerfile
# Usar una imagen base ligera de Python
FROM python:3.10-slim

# Establecer directorio de trabajo
WORKDIR /app

# Copiar archivos de dependencias
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del bot
COPY ./bot/ .

# Comando por defecto para ejecutar el bot
CMD ["python", "main.py"]
```

Archivo requirements.txt de ejemplo:

```
alpaca-py
pandas
numpy
python-dotenv
```

---

6. Lista de Herramientas, Enlaces y Referencias

· Brokers con API:
  · Alpaca Markets
  · Interactive Brokers
  · CCXT (Crypto)
· Proveedores de Datos:
  · Polygon.io
  · IEX Cloud
  · Yahoo Finance (solo para pruebas)
· Bases de Datos Time-Series:
  · TimescaleDB
  · InfluxDB
· Backtesting & Research:
  · VectorBT
  · Backtrader
  · QuantConnect (LEAN Engine)
  · Optuna (Optimización)
  · QuantStats (Análisis)
· Infraestructura & DevOps:
  · Docker
  · GitHub Actions (CI/CD)
  · Prometheus
  · Grafana
  · Elasticsearch / Kibana (Logs)
· Control de Versiones de Modelos:
  · DVC (Data Version Control)
  · MLflow

---

7. Conclusión Final: La Mentalidad del Negocio

Ningún stack sirve si no hay una metodología de trader profesional detrás. La tecnología es el esqueleto, pero la disciplina es la carne y la sangre. Para triunfar en este mundo, debes adoptar esta mentalidad:

· Trata tu bot como un fondo de inversión pequeño. Empieza con capital irrisorio (paper trading, luego micro‑lotes) y escala el capital lentamente mientras la ejecución real coincida fielmente con la simulación.
· El backtesting es mentira, la realidad es tu auditor. Dedica el 70% de tu tiempo a validar la robustez estadística de tus hallazgos (Monte Carlo, bootstrapping, permutación de ticks) y solo un 30% a diseñar nuevas señales. No te enamores de tu creación; intenta destruirla con datos.
· Acepta que todo alfa decae. La ventaja que tienes hoy no será la misma mañana. Monitoriza constantemente la tasa de Sharpe deslizante y ten un protocolo de apagado y reoptimización para cuando la señal se deteriore. Nunca "mantengas y reces".
· Aísla el sistema de tus emociones. Un bot rentable es aquel que no puedes tocar durante la sesión de trading. Cualquier intervención manual improvisada es una grieta en el sistema. Si crees que algo falla, debe existir un plan de acción predefinido que hayas diseñado en frío.

Construir un bot algorítmico rentable es una maratón de ingeniería, no un sprint de especulación. El stack tecnológico que hemos detallado aquí es la columna vertebral, pero lo que te permitirá pagar las facturas es la disciplina de ejecutar el proceso una y otra vez, sin atajos: simular de verdad, medir sin autoengaño y ejecutar con precisión quirúrgica.

Empieza hoy con el primer ladrillo. Tu única tarea mañana es escribir esas 10 líneas de código que descargan un gráfico del SPY. Ese acto ya te separa del 90% que solo consume información sin actuar.
