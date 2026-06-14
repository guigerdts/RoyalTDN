```

---

## Archivo 5: `05_ruta_implementacion_fase2_fase3.md`

```markdown
# 5. Ruta de Implementación: Fase 2 y Fase 3 – Profesionalización del Bot

Tras tener el MVP (Fase 0 y 1), es el momento de añadir las capas que transforman un prototipo funcional en un sistema robusto, controlado y mantenible. La Fase 2 se centra en la investigación rigurosa y el control de riesgo. La Fase 3 introduce la infraestructura profesional (Docker, base de datos, CI/CD).

---

## Fase 2: Del Juguete al Laboratorio de Investigación (1-3 Meses)

### 5.2.1 Backtesting serio con VectorBT

Dejamos el backtest manual en pandas y adoptamos VectorBT. Esta herramienta vectoriza las operaciones y permite optimización masiva y walk-forward analysis en pocas líneas.

**Instalación:**

```bash
pip install vectorbt
```

Backtest con cruce de medias optimizado:

```python
import vectorbt as vbt
import numpy as np
import pandas as pd
import yfinance as yf

# 1. Descargar datos
data = yf.download("SPY", start="2015-01-01", end="2023-12-31")['Adj Close']

# 2. Definir parámetros a probar
fast_periods = np.arange(2, 30, 2)
slow_periods = np.arange(30, 200, 10)

# 3. Calcular indicadores y señales de cruce
fast_ma = vbt.MA.run(data, window=fast_periods)
slow_ma = vbt.MA.run(data, window=slow_periods)
entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

# 4. Walk-Forward Analysis
# Dividimos en 5 ventanas (cada una con parte in-sample y out-of-sample)
portfolio = vbt.Portfolio.from_signals(
    data,
    entries,
    exits,
    freq='D',
    commission=0.001,
    slippage=0.001,
    # Configuración del Walk-Forward
    optimization_options=dict(
        split=5,
        split_value=np.linspace(0.3, 1.0, 6)  # 30% IS, 70% OOS en cada split
    )
)

# 5. Resultados
print(portfolio.stats())
portfolio.plot().show()
```

Análisis con QuantStats: VectorBT puede exportar los retornos para analizar con QuantStats.

```python
import quantstats as qs

# Extender pandas para que muestren gráficos en el notebook
qs.extend_pandas()

# Obtener los retornos del mejor par de parámetros en el periodo OOS
# (VectorBT internamente guarda métricas, aquí un ejemplo simplificado)
returns = portfolio.returns()
qs.reports.html(returns, output='report.html')
```

5.2.2 Validación de robustez

Una vez tengas candidatos de estrategia, debes someterlos a pruebas de estrés:

1. Cambio de parámetros: Si cambias el periodo rápido de 10 a 12, ¿el Sharpe cae de 1.5 a -0.2? Mala señal.
2. Distintos regímenes: Divide el tiempo en bull market, bear market, sideways. ¿La estrategia funciona en todos? Si solo gana en bull, básicamente estás apalancado al mercado.
3. Monte Carlo sobre trades: Toma los retornos diarios de la estrategia, reordénalos aleatoriamente 1000 veces y recalcula la curva de capital. Si tu resultado real está en el extremo superior de la distribución, podrías haber tenido suerte.
4. Prueba en otro activo: Aplica la misma lógica a QQQ, IWM, DIA. Si no funciona en ningún otro lado, tu alfa es probablemente espurio.

5.2.3 Implementar el módulo de gestión de riesgos

Tomamos nuestro live_bot_sma.py y le añadimos un gestor de riesgos rudimentario pero efectivo. Este módulo actuará como un guardián entre la señal y la orden.

Nuevas funcionalidades a añadir:

· Sizing basado en volatilidad (ATR):
  ```python
  import numpy as np
  # Supongamos que tenemos df con columna 'ATR' (Average True Range)
  risk_per_trade_pct = 0.02  # 2% del capital
  capital = float(account.equity)
  atr_value = df['ATR'].iloc[-1]  # ATR del último día
  stop_distance = atr_value * 2  # Stop a 2 ATR
  shares_to_buy = int((capital * risk_per_trade_pct) / stop_distance)
  ```
· Stop Loss diario (Kill Switch): Al inicio del día, registra el equity. Tras cada operación, calcula el P&L diario:
  ```python
  initial_equity = float(account.last_equity)  # Equity del cierre anterior
  current_equity = float(account.equity)
  daily_pnl_pct = (current_equity - initial_equity) / initial_equity
  if daily_pnl_pct <= -0.03:  # -3%
      logger.critical("KILL SWITCH: Pérdida diaria > 3%. Cerrando todo.")
      trading_client.close_all_positions()
      # Enviar alerta y detener el bot
      exit()
  ```
· Máximo de operaciones perdedoras consecutivas:
  ```python
  consecutive_losses = 0
  # Después de cada operación cerrada, actualizar
  if trade_pnl < 0:
      consecutive_losses += 1
  else:
      consecutive_losses = 0
  if consecutive_losses >= 5:
      logger.critical("KILL SWITCH: 5 pérdidas consecutivas. Deteniendo bot.")
      # Detener lógica
  ```

5.2.4 Logs y monitorización mejorada

· CSV de operaciones: Cada cierre de posición, añadir una fila a un archivo CSV con: fecha entrada, fecha salida, precio entrada, precio salida, tamaño, comisión, P&L, duración.
· Dashboard con Streamlit (alternativa ligera a Grafana):
  ```bash
  pip install streamlit
  ```
  Crea un app_dashboard.py que lea el CSV y muestre una curva de equity, drawdown, etc. Ejecuta con streamlit run app_dashboard.py. Ideal para una visualización rápida sin montar Prometheus.

Meta de la Fase 2: Tu bot ahora hace backtesting serio, sabe cuánto arriesgar, se apaga en emergencias y te muestra sus tripas en un dashboard básico. Ya no es un juguete.

---

Fase 3: Infraestructura de “Mesa de Trading” Personal (3-6 Meses)

Aquí convertimos nuestro script en un servicio robusto, escalable y gestionable profesionalmente.

5.3.1 Dockerizar el bot

Paso 1: Crear Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema si fueran necesarias (ej. ta-lib)
# RUN apt-get update && apt-get install -y build-essential

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "live_bot_sma.py"]
```

Paso 2: Crear requirements.txt

Lista todas las dependencias con sus versiones exactas (puedes generarlo con pip freeze > requirements.txt).

```
alpaca-py==0.18.0
pandas==2.1.4
numpy==1.26.2
python-dotenv==1.0.0
```

Paso 3: Construir y ejecutar

```bash
docker build -t mi-bot:v1.0 .
docker run -d --name bot-paper --env-file .env mi-bot:v1.0
```

El bot ahora corre aislado. Puedes ver sus logs con docker logs -f bot-paper.

5.3.2 Almacenar datos en TimescaleDB

¿Por qué TimescaleDB?

· Es PostgreSQL + optimizaciones para time-series.
· Puedes hacer SQL tradicional, joins, etc., y además comprime y acelera consultas temporales.

Despliegue con Docker Compose: Crea un archivo docker-compose.yml para levantar el bot y la base de datos juntos.

```yaml
version: '3.8'
services:
  db:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_USER: botuser
      POSTGRES_PASSWORD: secretpassword
      POSTGRES_DB: trading_bot
    ports:
      - "5432:5432"
    volumes:
      - timescale_data:/var/lib/postgresql/data

  bot:
    build: .
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://botuser:secretpassword@db:5432/trading_bot
    depends_on:
      - db

volumes:
  timescale_data:
```

Desde tu bot, conectar y escribir datos:

```python
import psycopg2
from psycopg2.extras import execute_values

conn = psycopg2.connect(os.getenv("DATABASE_URL"))

# Crear tabla hypertable para velas
with conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_bars (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            open        DOUBLE PRECISION,
            high        DOUBLE PRECISION,
            low         DOUBLE PRECISION,
            close       DOUBLE PRECISION,
            volume      DOUBLE PRECISION
        );
        SELECT create_hypertable('market_bars', 'time', if_not_exists => TRUE);
    """)
    conn.commit()

# Insertar datos
def insert_bar(symbol, bar):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO market_bars (time, symbol, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (bar.timestamp, symbol, bar.open, bar.high, bar.low, bar.close, bar.volume))
        conn.commit()
```

De igual forma, crea tablas para orders y trades y registra cada operación.

5.3.3 Dashboard con Grafana

Grafana se conecta directamente a TimescaleDB (PostgreSQL).

1. Añade Grafana a tu docker-compose.yml.
2. Configura un datasource apuntando a db:5432.
3. Crea dashboards con consultas SQL:
   · Curva de equity: SELECT time, SUM(pnl) OVER (ORDER BY time) as equity FROM trades;
   · Drawdown, P&L diario, etc.

5.3.4 Integración continua (CI/CD) con GitHub Actions

Crea la carpeta .github/workflows/ en tu repositorio y un archivo deploy.yml:

```yaml
name: Test and Deploy Bot

on:
  push:
    branches: [ main ]

jobs:
  test-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run unit tests
        run: python -m pytest tests/
      - name: Run smoke backtest
        run: python tests/smoke_backtest.py
      - name: Build and push Docker image
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: your-dockerhub-username/mi-bot:latest
      - name: Deploy to server
        uses: appleboy/ssh-action@v0.1.10
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            docker pull your-dockerhub-username/mi-bot:latest
            docker stop bot-paper || true
            docker rm bot-paper || true
            docker run -d --name bot-paper --env-file /opt/bot/.env your-dockerhub-username/mi-bot:latest
```

Esto despliega automáticamente cada cambio que pushees a la rama principal si los tests pasan.

Meta de la Fase 3: Tu sistema se despliega con un simple git push, almacena datos en una base de datos profesional, se monitoriza con dashboards, y corre en un entorno aislado y reproducible. Ahora sí, tienes una mesa de trading personal.

---

En el siguiente documento (06_ruta_implementacion_fase4_y_codigos_ejemplo.md) abordamos el salto profesional definitivo.
