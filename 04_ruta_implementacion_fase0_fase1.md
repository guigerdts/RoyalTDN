```markdown
# 4. Ruta de Implementación: Fase 0 y Fase 1 – De Cero a tu Primer Bot Automático

En este documento comenzamos la construcción práctica. Las Fases 0 y 1 son las más cruciales: te llevan de no tener nada a poseer un bot que opera solo en un entorno de simulación (paper trading), completando el ciclo end-to-end. Cada paso está diseñado para ser ejecutado en orden y proporciona una victoria temprana que te motivará a continuar.

El objetivo al final de la Fase 1 es tener un sistema mínimo funcional (MVP) que te permita iterar y aprender. No busques la perfección; busca el funcionamiento básico.

---

## Fase 0: Los Cimientos (1-2 Semanas)

Esta fase es puramente de preparación del entorno y verificación de que las herramientas básicas funcionan. No se escribe ninguna lógica de trading todavía. Si ya tienes experiencia con Python y Jupyter, puedes completarla en una tarde.

### 4.0.1 Verificar la instalación de Python

Necesitas Python 3.9 o superior. Abre una terminal (o Command Prompt en Windows) y ejecuta:

```bash
python --version
# o en algunos sistemas:
python3 --version
```

Deberías ver algo como Python 3.10.x. Si no, descarga e instala la última versión desde python.org.

4.0.2 Crear un entorno virtual

Los entornos virtuales aíslan las dependencias de cada proyecto, evitando conflictos entre versiones de librerías. Es una práctica profesional obligatoria.

Crea una carpeta para tu proyecto y dentro de ella el entorno virtual:

```bash
mkdir mi_bot_trading
cd mi_bot_trading
python -m venv venv
```

Actívalo:

· Windows (Command Prompt): venv\Scripts\activate
· Windows (PowerShell): .\venv\Scripts\Activate
· macOS / Linux: source venv/bin/activate

Sabrás que está activo porque verás (venv) al inicio de la línea de comandos.

4.0.3 Instalar las librerías fundamentales

Con el entorno activo, instala el conjunto básico que usaremos en las primeras fases:

```bash
pip install pandas numpy matplotlib yfinance jupyterlab
```

· pandas, numpy: manipulación de datos.
· matplotlib: gráficos.
· yfinance: descarga de datos de Yahoo Finance (solo para pruebas iniciales, no para producción).
· jupyterlab: entorno interactivo para experimentar.

4.0.4 Primer script: descargar y visualizar datos

Abre Jupyter Lab ejecutando en la terminal:

```bash
jupyter lab
```

Crea un nuevo notebook (Python 3). En la primera celda, escribe y ejecuta:

```python
import yfinance as yf
import matplotlib.pyplot as plt

# Descargar 5 años de datos diarios del SPY
df = yf.download("SPY", start="2019-01-01", end="2024-01-01")

# Mostrar las primeras filas para ver la estructura
print(df.head())

# Graficar el precio de cierre ajustado
df['Adj Close'].plot(figsize=(12,6), title='SPY - Precio de Cierre Ajustado')
plt.ylabel('Precio (USD)')
plt.grid(True)
plt.show()
```

Meta de este paso: Ver un gráfico del SPY en tu pantalla. Has roto la barrera más grande: los datos fluyen hacia tu ordenador.

4.0.5 Cuenta en un broker con API (Alpaca Markets)

Para la ejecución en papel, usaremos Alpaca Markets por su simplicidad.

1. Ve a https://app.alpaca.markets/signup y crea una cuenta.
2. Una vez dentro, estarás en un entorno de Paper Trading por defecto (dinero ficticio).
3. Ve a la sección "API Keys" o "Generate API Key". Crea un nuevo par de claves. Copia el API Key y el Secret Key. Guárdalos de forma segura, no los subas nunca a GitHub.

4.0.6 Instalar la librería de Alpaca y probar la conexión

En tu terminal (con el entorno virtual activo):

```bash
pip install alpaca-py
```

Crea un nuevo notebook o script para probar la conexión:

```python
from alpaca.trading.client import TradingClient
import os

# Idealmente, usa variables de entorno para las claves
API_KEY = "TU_API_KEY_AQUI"
API_SECRET = "TU_SECRET_KEY_AQUI"

# Inicializa el cliente de trading en modo paper
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

# Obtén la información de la cuenta de papel
account = trading_client.get_account()
print(f"Estado de la cuenta: {account.status}")
print(f"Capital: ${account.equity}")
print(f"Poder de compra: ${account.buying_power}")
```

Si ves los datos de tu cuenta, ¡la conexión funciona!

Nota de seguridad profesional: En lugar de escribir las claves en el código, crea un archivo .env en tu proyecto:

```
ALPACA_API_KEY=TU_API_KEY
ALPACA_SECRET_KEY=TU_SECRET_KEY
```

Instala python-dotenv (pip install python-dotenv) y carga las variables así:

```python
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")
```

Añade .env a tu archivo .gitignore para no subirlo al repositorio.

---

Fase 1: Tu Primer Bot Caminando (2-4 Semanas)

En esta fase construiremos el ciclo completo: señal -> backtest simple -> ejecución automática en papel.

4.1.1 Elegir una estrategia ultra-simple

Para el MVP, no importa que la estrategia sea rentable. Buscamos montar la maquinaria. La estrategia elegida debe ser fácil de calcular y entender. Ejemplo clásico: Cruce de Medias Móviles (SMA Crossover).

· Regla: Si la media móvil rápida (ej. 5 periodos) cruza por encima de la media móvil lenta (ej. 20 periodos) -> Comprar (LONG). Si cruza por debajo -> Vender (o ponerse SHORT, simplificaremos solo con LONG/FLAT).
· Activo: SPY (ETF del S&P 500). Líquido, datos abundantes y representativo.

4.1.2 Backtest simple en Jupyter (sin frameworks)

Debemos implementar la lógica en un notebook para entender cada paso y evitar cajas negras al principio.

Paso 1: Cargar datos y calcular indicadores

```python
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Descargar datos
data = yf.download("SPY", start="2018-01-01", end="2023-12-31")
df = data[['Adj Close']].copy()
df.columns = ['close']

# Calcular medias móviles
df['SMA5'] = df['close'].rolling(window=5).mean()
df['SMA20'] = df['close'].rolling(window=20).mean()

# Visualizar
df[['close', 'SMA5', 'SMA20']].plot(figsize=(14,7))
plt.title('SPY con Medias Móviles 5 y 20')
plt.show()
```

Paso 2: Generar señales (con mucho cuidado con el look-ahead bias)

```python
# Creamos una columna de señal: 1 = largo, 0 = fuera del mercado
df['signal'] = 0
# La condición se debe evaluar con el cierre de ayer para decidir la posición de hoy
df.loc[df['SMA5'] > df['SMA20'], 'signal'] = 1
df['signal'] = df['signal'].shift(1)  # ¡CRUCIAL! La señal de ayer decide la operación de hoy

# Rellenamos NaN iniciales con 0 (fuera del mercado)
df['signal'] = df['signal'].fillna(0)
```

Paso 3: Calcular los retornos de la estrategia

```python
# Retorno diario del activo
df['returns'] = df['close'].pct_change()

# Retorno de la estrategia = señal de ayer * retorno de hoy
df['strategy_returns'] = df['signal'] * df['returns']

# Curva de capital acumulada
df['cumulative_market'] = (1 + df['returns']).cumprod()
df['cumulative_strategy'] = (1 + df['strategy_returns']).cumprod()

# Gráfico comparativo
plt.figure(figsize=(12,6))
df['cumulative_market'].plot(label='Buy & Hold SPY')
df['cumulative_strategy'].plot(label='Estrategia SMA Crossover')
plt.legend()
plt.title('Backtest Simple: SMA Crossover vs Buy & Hold')
plt.show()
```

Paso 4: Interpretar el resultado

Mira el gráfico. ¿La línea naranja está por encima de la azul? Probablemente no. La estrategia simple no batirá al mercado consistentemente, y es normal. Lo importante es que el flujo funciona.

4.1.3 Añadir comisiones y slippage básicos al backtest

Para hacerlo más realista, réstale una comisión fija por operación. Asumamos una comisión de $0.005 por acción y un slippage de 0.01% por operación.

```python
# Detectar cambios en la señal (entrada/salida)
df['trade_signal'] = df['signal'].diff().fillna(0)

# Asumimos un capital inicial fijo para el cálculo de comisiones (simplificado)
capital = 10000
# Número de acciones aproximadas que compraríamos (simplificación)
df['shares'] = capital / df['close']

# Coste por operación: comisión + slippage
commission_per_share = 0.005
slippage_pct = 0.0001  # 0.01%

# Ajustar retornos de estrategia
df['cost'] = 0.0
# Cuando entramos o salimos (trade_signal != 0), incurrimos en costes
df.loc[df['trade_signal'] != 0, 'cost'] = (df['shares'] * commission_per_share) + (df['shares'] * df['close'] * slippage_pct * abs(df['trade_signal']))
# Convertir el coste total a un porcentaje del capital
df['cost_pct'] = df['cost'] / capital
# Retorno de estrategia neto
df['strategy_returns_net'] = df['strategy_returns'] - df['cost_pct']

# Curva de capital neta
df['cumulative_strategy_net'] = (1 + df['strategy_returns_net']).cumprod()

# Comparación
df[['cumulative_market', 'cumulative_strategy_net']].plot(figsize=(12,6))
plt.title('Backtest con Comisiones y Slippage')
plt.show()
```

4.1.4 Convertir el backtest en un script de trading en vivo

Ahora tomamos la misma lógica y la conectamos a la API de Alpaca para que opere en papel automáticamente.

Estructura del script live_bot_sma.py:

```python
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")

SYMBOL = "SPY"
FAST_MA = 5
SLOW_MA = 20
QTY = 1  # Cantidad pequeña para pruebas en papel

# Clientes de Alpaca
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# Estado global (en producción, esto debería ir en una BD o Redis)
current_position = None  # 'long' o None

async def get_latest_signal():
    """Obtiene la última señal basada en cruce de medias."""
    end = datetime.now()
    start = end - timedelta(days=60)  # Suficientes días para calcular MA20
    
    request = StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame.Day,
        start=start,
        end=end
    )
    bars = data_client.get_stock_bars(request)
    df = bars.df
    # Si hay multi-índice, limpiar
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(SYMBOL, axis=1, level=1)
    
    df['SMA5'] = df['close'].rolling(FAST_MA).mean()
    df['SMA20'] = df['close'].rolling(SLOW_MA).mean()
    
    # Señal: 1 para largo, 0 para salir
    if df['SMA5'].iloc[-1] > df['SMA20'].iloc[-1]:
        return 1
    else:
        return 0

async def get_current_position():
    """Consulta la posición actual en el broker."""
    try:
        position = trading_client.get_open_position(SYMBOL)
        qty = float(position.qty)
        if qty > 0:
            return 'long'
        elif qty < 0:
            return 'short'
        else:
            return None
    except Exception:
        return None

async def submit_market_order(side: OrderSide):
    """Envía una orden de mercado."""
    order_data = MarketOrderRequest(
        symbol=SYMBOL,
        qty=QTY,
        side=side,
        time_in_force=TimeInForce.DAY
    )
    order = trading_client.submit_order(order_data)
    logger.info(f"Orden enviada: {side.name} {SYMBOL} - ID: {order.id}")
    return order

async def main_loop():
    global current_position
    logger.info("Bot de Paper Trading SMA Crossover iniciado.")
    
    # Al iniciar, sincronizar posición real del broker
    current_position = await get_current_position()
    logger.info(f"Posición inicial sincronizada: {current_position}")
    
    while True:
        try:
            # 1. Obtener señal
            signal = await get_latest_signal()
            logger.info(f"Señal calculada: {signal} | Posición actual: {current_position}")
            
            # 2. Lógica de trading
            if signal == 1 and current_position != 'long':
                # Si no tenemos posición larga, entrar
                if current_position == 'short':
                    # Cubrir corto primero
                    await submit_market_order(OrderSide.BUY)
                    await asyncio.sleep(2)  # Breve pausa para que se ejecute
                # Abrir largo
                await submit_market_order(OrderSide.BUY)
                current_position = 'long'
                
            elif signal == 0 and current_position == 'long':
                # Salir del largo
                await submit_market_order(OrderSide.SELL)
                current_position = None
            
            # Esperar 1 minuto antes del siguiente ciclo
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Error en el bucle principal: {e}", exc_info=True)
            # En caso de error grave, esperar y reintentar
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main_loop())
```

4.1.5 Ejecutar el bot en Paper Trading

1. Guarda el script como live_bot_sma.py.
2. Asegúrate de que el archivo .env está en la misma carpeta y contiene tus claves reales de Alpaca.
3. Ejecuta desde la terminal: python live_bot_sma.py.
4. Observa los logs. Verás cómo el bot calcula la señal y envía órdenes al mercado de papel.
5. Entra en tu panel de Alpaca y verifica que las órdenes se ejecutan y la posición cambia.

Posibles problemas y soluciones:

· Error de autenticación: Revisa API Key y Secret Key. Asegúrate de que sean del entorno Paper.
· Error "no se encuentra el símbolo": SPY es correcto. Comprueba que el mercado esté abierto.
· El bot no envía órdenes: Revisa los logs de señal. Es posible que la señal no haya cambiado durante la ejecución. Deja el bot corriendo varios días (o modifica temporalmente las medias para forzar una señal).

4.1.6 Tareas para completar la Fase 1

· Dejar el bot corriendo 1 semana completa en horario de mercado. Monitoriza los logs diariamente.
· Crear un archivo de log persistente: Modifica el logging.basicConfig para que escriba a un archivo bot.log.
· Añadir una notificación simple por Telegram cuando se realice una operación (opcional pero recomendado). Usa python-telegram-bot y un bot de Telegram que puedas crear con @BotFather.

```python
# Ejemplo de notificación por Telegram
import requests
TELEGRAM_TOKEN = "TU_TOKEN"
TELEGRAM_CHAT_ID = "TU_CHAT_ID"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, json=payload)

# Llamar a send_telegram_message() después de submit_market_order()
```

Meta final de la Fase 1: Tienes un bot que, sin tu intervención, recibe datos, calcula señales y envía órdenes en un entorno de simulación, con logs que te permiten auditar su comportamiento. El ciclo end-to-end está cerrado. ¡Enhorabuena!

---

En el siguiente documento (05_ruta_implementacion_fase2_fase3.md) añadiremos gestión de riesgo, backtesting serio con VectorBT, Docker y base de datos.

