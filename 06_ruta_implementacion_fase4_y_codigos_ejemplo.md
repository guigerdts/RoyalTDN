```

---

## Archivo 6: `06_ruta_implementacion_fase4_y_codigos_ejemplo.md`

```markdown
# 6. Ruta de Implementación: Fase 4 – El Salto Profesional y Códigos de Ejemplo Avanzados

Esta fase representa la transición de un sistema robusto a uno de grado cuasi-institucional. Aquí se refinan los componentes que realmente separan un bot amateur de uno que puede gestionar capital serio de manera consistente. Además, incluimos ejemplos de código más avanzados y modulares que reflejan la arquitectura final.

---

## Fase 4: El Salto Profesional – Datos y Ejecución Avanzada (6+ Meses)

### 6.4.1 Adopción de datos de alta calidad

Abandonamos `yfinance` por completo. Contratamos un proveedor profesional para datos históricos y en tiempo real.

**Opción recomendada: Polygon.io**

- Plan "Starter" ($29/mes) ofrece datos en tiempo real de acciones (WebSocket) y acceso a históricos tick, minutos y diarios.
- Los datos incluyen todas las acciones, splits, dividendos y delistados.
- API moderna y bien documentada.

**Código de ejemplo: descargar históricos tick con Polygon y almacenar en Parquet**

```python
import requests
import pandas as pd
import datetime
from polygon import RESTClient  # pip install polygon-api-client

client = RESTClient(api_key="TU_POLYGON_API_KEY")

# Descargar trades (ticks) para un día específico
aggs = client.get_aggs(
    ticker="SPY",
    multiplier=1,
    timespan="minute",
    from_="2024-01-02",
    to="2024-01-02"
)

# Convertir a DataFrame
records = [a.__dict__ for a in aggs]
df = pd.DataFrame(records)

# Guardar en formato Parquet, particionado por fecha
df.to_parquet(f"data/spy/minute/2024-01-02.parquet")
```

WebSocket para tiempo real:

```python
from polygon import WebSocketClient
from polygon.websocket.models import WebSocketMessage
from typing import List

# Cliente WebSocket
ws_client = WebSocketClient(api_key="TU_POLYGON_API_KEY")

async def handle_msg(msg: List[WebSocketMessage]):
    for m in msg:
        print(f"{m.symbol}: {m.open} {m.high} {m.low} {m.close}")

ws_client.run(handle_msg, symbols=["SPY"])
```

Integra este flujo en tu módulo de "Ingestión de Datos".

6.4.2 Motor de backtesting orientado a eventos con LEAN (QuantConnect)

¿Por qué LEAN?

· Motor open-source probado en batalla.
· Soporta múltiples asset classes, horarios de mercado, ajustes corporativos.
· Backtest a nivel tick o minuto con lógica de libro de órdenes simplificada.
· Puedes ejecutar en local (Docker) o en la nube de QuantConnect.

Instalación local con Docker:

QuantConnect proporciona una imagen Docker con todo listo.

```bash
docker pull quantconnect/lean
docker run -d --name lean-engine -p 8888:8888 quantconnect/lean
```

Ejemplo de algoritmo en LEAN (Python):

```python
class SMACrossoverAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2023, 12, 31)
        self.SetCash(100000)
        self.AddEquity("SPY", Resolution.Minute)
        self.fast = self.SMA("SPY", 5, Resolution.Daily)
        self.slow = self.SMA("SPY", 20, Resolution.Daily)
        self.SetWarmUp(30)
    
    def OnData(self, data):
        if not self.fast.IsReady: return
        
        if self.fast.Current.Value > self.slow.Current.Value:
            self.SetHoldings("SPY", 1.0)  # 100% del portafolio
        else:
            self.Liquidate("SPY")
```

Este código es más limpio y realista: LEAN maneja las comisiones, splits, horarios y genera métricas detalladas automáticamente.

6.4.3 Ejecución inteligente con algoritmos TWAP/VWAP

En lugar de lanzar órdenes de mercado, implementamos una ejecución TWAP básica.

Código de ejemplo: TWAP simple en Python con Alpaca

```python
import asyncio
import math
from datetime import datetime, timedelta

async def execute_twap(symbol, total_shares, duration_minutes, trading_client):
    """
    Ejecuta una orden TWAP: divide total_shares en lotes durante duration_minutes.
    """
    slice_count = duration_minutes  # Un slice por minuto
    shares_per_slice = total_shares // slice_count
    remainder = total_shares % slice_count
    
    logger.info(f"Iniciando TWAP: {total_shares} de {symbol} en {duration_minutes} min")
    
    for i in range(slice_count):
        slice_start = datetime.now()
        # Calcular tamaño del lote (el último lleva el remanente)
        qty = shares_per_slice + (remainder if i == slice_count - 1 else 0)
        if qty == 0:
            continue
        
        # Enviar orden límite al midpoint para minimizar slippage
        # O simplemente una orden de mercado con QTY pequeño
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        trading_client.submit_order(order_data)
        
        # Esperar hasta el próximo minuto
        elapsed = (datetime.now() - slice_start).total_seconds()
        wait_time = max(0, 60 - elapsed)
        await asyncio.sleep(wait_time)
```

Integra esta función en tu módulo O/EMS. Para órdenes pequeñas en SPY, una market order quizás sea suficiente, pero para cantidades mayores o activos menos líquidos, TWAP es crucial.

6.4.4 Arquitectura final modular con Redis Streams

Este es un esqueleto de cómo luciría el sistema profesional con módulos separados comunicándose por Redis. Es un pseudo-código extenso y detallado para que sirva de referencia de implementación real.

Requisito: Tener Redis corriendo. Puedes añadirlo a tu docker-compose.yml.

ingestor.py (módulo de ingesta de datos)

```python
import asyncio
import json
import redis.asyncio as redis
from polygon import WebSocketClient
from polygon.websocket.models import WebSocketMessage
from typing import List

STREAM_NAME = "market_ticks"

async def main():
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    ws = WebSocketClient(api_key="...")
    
    async def handle_msg(msg: List[WebSocketMessage]):
        for m in msg:
            tick_data = {
                "symbol": m.symbol,
                "price": m.close,
                "volume": m.volume,
                "timestamp": m.timestamp
            }
            await r.xadd(STREAM_NAME, tick_data)
    
    await ws.connect()
    ws.run(handle_msg, symbols=["SPY"])

asyncio.run(main())
```

engine.py (motor de señal)

```python
import asyncio
import redis.asyncio as redis
import pandas as pd

STREAM_NAME = "market_ticks"
SIGNAL_STREAM = "trading_signals"
SYMBOL = "SPY"

async def main():
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    # Buffer para almacenar los últimos N ticks y formar velas o calcular indicadores
    tick_buffer = []
    
    # Crear grupo de consumidores
    try:
        await r.xgroup_create(STREAM_NAME, "engine_group", id='0', mkstream=True)
    except Exception:
        pass
    
    while True:
        # Leer nuevos ticks
        entries = await r.xreadgroup("engine_group", "engine_consumer", {STREAM_NAME: '>'}, count=10)
        for stream, messages in entries:
            for msg_id, msg_data in messages:
                tick_buffer.append(msg_data)
                # Procesar buffer... (formar vela de 1 min, calcular indicadores, etc.)
                # Si se genera una señal:
                signal = {"symbol": SYMBOL, "action": "BUY", "price": msg_data['price']}
                await r.xadd(SIGNAL_STREAM, signal)

asyncio.run(main())
```

risk_manager.py y execution.py seguirían patrones similares, leyendo del stream de señales, validando y enviando al broker.

6.4.5 TCA (Transaction Cost Analysis)

Implementa un script que compare el precio de ejecución de tus órdenes con el precio medio del mercado en el momento de la decisión.

```python
# Consulta SQL de ejemplo en TimescaleDB
query = """
SELECT 
    t.order_id,
    t.execution_price,
    b.vwap as market_vwap_5min,
    (t.execution_price - b.vwap) / b.vwap * 10000 as slippage_bps
FROM trades t
JOIN market_bars_5min b ON 
    t.symbol = b.symbol AND 
    b.time BETWEEN t.decision_time - interval '2.5 min' AND t.decision_time + interval '2.5 min'
"""
slippage = pd.read_sql(query, conn)
print(slippage.describe())
```

Un slippage medio de más de 1-2 bps (basis points, 0.01%) ya merece optimizar tu algoritmo de ejecución.

---

Códigos de ejemplo funcionales adicionales:

Ejemplo 6.A: Bot de trading con arquitectura asíncrona y reintentos

```python
import asyncio
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def submit_order_with_retry(trading_client, order_data):
    try:
        order = trading_client.submit_order(order_data)
        return order
    except Exception as e:
        logger.error(f"Error al enviar orden, reintentando: {e}")
        raise

# Uso:
# order = await submit_order_with_retry(tc, order_data)
```

Ejemplo 6.B: Script de sincronización de posición al iniciar

```python
async def sync_position(symbol, trading_client, local_state):
    try:
        broker_position = trading_client.get_open_position(symbol)
        broker_qty = float(broker_position.qty)
        if broker_qty > 0 and local_state != 'long':
            logger.warning("Sincronización: broker tiene LONG, local no. Actualizando.")
            local_state = 'long'
        elif broker_qty == 0 and local_state == 'long':
            logger.warning("Sincronización: broker sin posición, local LONG. Actualizando.")
            local_state = None
        return local_state
    except Exception:
        logger.warning("No se pudo obtener posición del broker, manteniendo estado local.")
        return local_state
```

---

Meta de la Fase 4: Tu sistema utiliza datos profesionales, tiene un backtesting a prueba de balas, ejecuta órdenes de forma inteligente y mide constantemente su propia eficiencia. Es un bot de trading de nivel institucional operado por una sola persona.

---

En el documento final (07_herramientas_enlaces_y_conclusion.md) encontrarás un compendio de referencias y la conclusión del roadmap.
