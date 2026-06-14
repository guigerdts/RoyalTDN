# Configuration Specification

## Purpose

Define cómo RoyalTDN carga configuración desde variables de entorno y archivo `.env`. Usa `pydantic-settings` para validación y autocompletado.

## Requirements

### Requirement: Settings class with pydantic-settings

`src/royaltdn/config/settings.py` MUST exponer una clase `Settings` que hereda de `BaseSettings` (pydantic-settings). SHALL cargar valores desde variables de entorno con prefijo `ALPACA_` y desde un archivo `.env` en la raíz del proyecto.

#### Scenario: Settings load from .env file

- GIVEN un archivo `.env` con `ALPACA_API_KEY=test123` y `ALPACA_SECRET_KEY=secret456`
- WHEN se instancia `Settings()`
- THEN `settings.ALPACA_API_KEY` SHALL ser `"test123"` y `settings.ALPACA_SECRET_KEY` SHALL ser `"secret456"`

#### Scenario: Missing .env raises validation error

- GIVEN que NO existe archivo `.env`
- WHEN se instancia `Settings()`
- THEN pydantic-settings SHALL lanzar `ValidationError` por campos requeridos faltantes

#### Scenario: Environment variable override

- GIVEN `ALPACA_API_KEY` seteada en el entorno del sistema
- WHEN se instancia `Settings()`
- THEN la variable de entorno SHALL tener prioridad sobre `.env`

### Requirement: Mandatory and optional fields

El modelo `Settings` MUST incluir estos campos con tipos explícitos:

| Campo | Tipo | Requerido | Propósito |
|-------|------|-----------|-----------|
| `ALPACA_API_KEY` | `str` | MUST | Autenticación Alpaca |
| `ALPACA_SECRET_KEY` | `str` | MUST | Autenticación Alpaca |
| `ALPACA_PAPER` | `bool` | MUST (default True) | Modo paper trading |
| `POLYGON_API_KEY` | `Optional[str]` | MAY | Datos Polygon.io (Fase 4) |
| `DATABASE_URL` | `Optional[str]` | MAY | TimescaleDB (Fase 3) |
| `REDIS_URL` | `Optional[str]` | MAY | Redis (Fase 3) |
| `TELEGRAM_TOKEN` | `Optional[str]` | MAY | Alertas Telegram (Fase 2) |
| `TELEGRAM_CHAT_ID` | `Optional[str]` | MAY | Alertas Telegram (Fase 2) |
| `LOG_LEVEL` | `str` | SHOULD (default INFO) | Nivel de logging |

#### Scenario: Default values apply when optional

- GIVEN un `.env` con solo `ALPACA_API_KEY` y `ALPACA_SECRET_KEY`
- WHEN se instancia `Settings()`
- THEN `settings.LOG_LEVEL` SHALL ser `"INFO"` y `settings.ALPACA_PAPER` SHALL ser `True`

### Requirement: Logging configuration

`src/royaltdn/config/logging.py` SHOULD configurar logging estructurado con formato timestamp, nivel, módulo y mensaje. SHALL usar `logging.config.dictConfig` para configuración programática.

#### Scenario: Logging initializes from settings

- GIVEN `Settings(LOG_LEVEL="DEBUG")`
- WHEN se llama a `setup_logging(settings)`
- THEN `logging.getLogger("royaltdn").level` SHALL ser `logging.DEBUG`
