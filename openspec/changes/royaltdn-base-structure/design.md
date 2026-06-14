# Design: RoyalTDN Base Structure — Fase 0

## Technical Approach

Crear la estructura de directorios y configuración base del proyecto RoyalTDN usando src-layout (`src/royaltdn/`), módulos vacíos con `__init__.py`, y un entry point asyncio mínimo. Fase 0 sienta los cimientos — sin infraestructura pesada (Docker, CI, Redis, TimescaleDB) hasta Fase 2+.

## Architecture Decisions

| Decisión | Opciones | Tradeoff | Decisión |
|----------|----------|----------|----------|
| **Package layout** | `src/royaltdn/` vs `royaltdn/` en raíz | src-layout evita conflictos de import, requiere `pip install -e .` | `src/royaltdn/` |
| **Config loading** | `pydantic-settings` vs `os.getenv` | Validación + autocompletado vs cero dependencias | `pydantic-settings` |
| **Async framework** | `asyncio` stdlib vs `anyio`/`trio` | Roadmap usa asyncio, es estándar | `asyncio` |
| **CLI framework** | `argparse` vs `click`/`typer` | Sin CLI aún — Fase 0 solo `asyncio.run()` | Ninguno |
| **Requirements** | `fase0.txt` único vs `base/dev/research/prod` | Empezar minimalista, crecer por fase | `fase0.txt` |
| **Módulos vacíos** | Crear todo vs crear solo lo necesario | YAGNI — estructura lista, implementación cuando el roadmap la requiera | Solo `__init__.py` |
| **Testing** | `pytest` ahora vs después | Sin código que probar aún en Fase 0 | Después (Fase 1) |

## Directory Structure

```
RoyalTDN/
├── src/
│   └── royaltdn/
│       ├── __init__.py
│       ├── main.py                    # asyncio.run(main()) simple
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py            # pydantic-settings + .env
│       ├── models/
│       │   ├── __init__.py
│       │   └── bar.py                 # Data models: Bar, Order, Signal, Position
│       ├── ingestion/
│       │   └── __init__.py            # Vacío hasta Fase 1
│       ├── strategy/
│       │   └── __init__.py            # Vacío hasta Fase 1
│       ├── risk/
│       │   └── __init__.py            # Vacío hasta Fase 2
│       ├── execution/
│       │   └── __init__.py            # Vacío hasta Fase 1
│       ├── storage/
│       │   └── __init__.py            # Vacío hasta Fase 3
│       └── monitoring/
│           └── __init__.py            # Vacío hasta Fase 2
├── tests/
│   └── __init__.py                    # Vacío hasta Fase 1
├── notebooks/                         # Jupyter para exploración Fase 0-1
├── data/
│   └── .gitkeep
├── requirements/
│   └── fase0.txt                      # pandas, numpy, alpaca-py, python-dotenv, pydantic-settings
├── .env.example
├── .gitignore
├── pyproject.toml                     # [project] + [build-system]
└── Makefile                           # install, run, clean
```

## File Changes

| File | Acción | Descripción |
|------|--------|-------------|
| `src/royaltdn/__init__.py` | Crear | Paquete principal vacío |
| `src/royaltdn/main.py` | Crear | Entry point asyncio simple |
| `src/royaltdn/config/__init__.py` | Crear | Subpaquete de configuración |
| `src/royaltdn/config/settings.py` | Crear | Settings vía pydantic-settings |
| `src/royaltdn/models/__init__.py` | Crear | Subpaquete de modelos |
| `src/royaltdn/models/bar.py` | Crear | Modelos Bar, Order, Signal, Position |
| `src/royaltdn/ingestion/__init__.py` | Crear | Módulo vacío (Fase 1) |
| `src/royaltdn/strategy/__init__.py` | Crear | Módulo vacío (Fase 1) |
| `src/royaltdn/risk/__init__.py` | Crear | Módulo vacío (Fase 2) |
| `src/royaltdn/execution/__init__.py` | Crear | Módulo vacío (Fase 1) |
| `src/royaltdn/storage/__init__.py` | Crear | Módulo vacío (Fase 3) |
| `src/royaltdn/monitoring/__init__.py` | Crear | Módulo vacío (Fase 2) |
| `tests/__init__.py` | Crear | Tests vacío (Fase 1) |
| `requirements/fase0.txt` | Crear | Dependencias iniciales |
| `pyproject.toml` | Crear | Metadata del proyecto |
| `.env.example` | Crear | Template de variables de entorno |
| `.gitignore` | Crear | Ignorar __pycache__, .env, data/, notebooks/ |
| `Makefile` | Crear | Comandos comunes |
| `data/.gitkeep` | Crear | Mantener directorio data/ en git |

## Data Flow

```
[.env] ──→ pydantic-settings ──→ Settings object
                                       │
[main.py] asyncio.run(main(settings))  │
    │                                   │
    └── main_loop():                    │
        while running:                  │
            datos ← feed (future)       │
            señal ← strategy (future)   │
            riesgo ← risk (future)      │
            orden ← execution (future)  │
            await asyncio.sleep(1)      │
                                       │
[SIGINT/SIGTERM] ──→ graceful_shutdown()
```

En Fase 0, `main_loop()` es un placeholder que imprime heartbeat. La conexión Alpaca Paper se prueba como script independiente.

## Interfaces / Contracts

### Settings (pydantic-settings)

```python
class Settings(BaseSettings):
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    log_level: str = "INFO"
    symbols: list[str] = ["SPY", "QQQ"]

    model_config = SettingsConfigDict(env_file=".env")
```

### Main Loop Signature

```python
async def main_loop(settings: Settings) -> None:
    """Heartbeat loop. Placeholder for Fase 0."""
```

### Data Models

```python
@dataclass
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class Order:
    id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    type: Literal["market", "limit"]
    status: str

@dataclass
class Signal:
    symbol: str
    direction: Literal["long", "short", "flat"]
    confidence: float
    timestamp: datetime

@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    current_price: float
```

## Testing Strategy

| Capa | Qué probar | Cómo |
|------|-----------|------|
| Humo | `python -c "import royaltdn; print('OK')"` | Verificar que el paquete importa |
| Humo | `python -m royaltdn` (o entry point) | Verificar que main loop arranca y hace graceful shutdown con Ctrl+C |
| Unidad | Settings carga .env | Probar con vars seteadas y con .env faltante |
| Unidad | Modelos de datos | Crear instancias, validar tipos |

No hay pytest configurado aún en Fase 0 — las pruebas son scripts manuales.

## Migration / Rollout

No migration required — proyecto greenfield. El rollout es:

1. Crear estructura de directorios y archivos
2. `pip install -e .` para desarrollo
3. Copiar `.env.example` a `.env` y configurar claves Alpaca
4. Ejecutar `python src/royaltdn/main.py` para verificar heartbeat
5. Siguiente: script independiente de prueba de conexión Alpaca Paper

## Open Questions

- Ninguna — las decisiones están tomadas por el roadmap y las condiciones del usuario.
