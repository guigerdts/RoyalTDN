# Data Models Specification

## Purpose

Define los modelos de datos compartidos para bars, órdenes, señales y posiciones del bot de trading. Estos modelos sirven como contracto entre módulos a lo largo de todas las fases del roadmap.

## Requirements

### Requirement: Bar model

`src/royaltdn/models/bar.py` MUST definir un modelo `Bar` con los campos: `symbol: str`, `timestamp: datetime`, `open: float`, `high: float`, `low: float`, `close: float`, `volume: float`. SHOULD ser un `@dataclass` o Pydantic `BaseModel`.

#### Scenario: Bar construction with required fields

- GIVEN symbol `"SPY"`, timestamp `2024-01-05 09:30:00`, OHLC y volume
- WHEN se construye `Bar(symbol="SPY", timestamp=..., open=450.0, high=451.0, low=449.5, close=450.5, volume=1000000)`
- THEN todos los campos SHALL ser accesibles como atributos

#### Scenario: Bar rejects negative volume

- GIVEN volume = -100
- WHEN se construye `Bar(volume=-100)`
- THEN el modelo SHALL lanzar `ValueError` (si Pydantic) o permitir validación manual (si dataclass)

### Requirement: Order model

`src/royaltdn/models/order.py` MUST definir `Order` con: `id: str`, `symbol: str`, `side: Literal["buy","sell"]`, `qty: float`, `type: Literal["market","limit","stop"]`, `status: str`, `filled_qty: float`, `filled_avg_price: float | None`, `created_at: datetime`, `updated_at: datetime`.

#### Scenario: Order lifecycle tracking

- GIVEN una orden creada con status `"new"`
- WHEN `status` cambia a `"filled"`
- THEN `filled_qty` y `filled_avg_price` SHALL estar poblados

### Requirement: Signal model

`src/royaltdn/models/signal.py` MUST definir `Signal` con: `symbol: str`, `direction: int` (1=long, -1=short, 0=neutral), `confidence: float` (0.0-1.0), `timestamp: datetime`, `metadata: dict`.

#### Scenario: Signal carries strategy metadata

- GIVEN una señal generada por estrategia SMA crossover
- WHEN se construye con metadata `{"fast_ma": 5, "slow_ma": 20}`
- THEN `signal.metadata["fast_ma"]` SHALL ser `5`

### Requirement: Position model

`src/royaltdn/models/position.py` MUST definir `Position` con: `symbol: str`, `qty: float`, `entry_price: float`, `current_price: float`, `unrealized_pl: float`, `timestamp: datetime`.

#### Scenario: Position P&L calculation

- GIVEN qty=10, entry_price=100.0, current_price=105.0
- WHEN se accede a `unrealized_pl`
- THEN SHALL calcularse como `(current_price - entry_price) * qty` = 50.0

### Requirement: Reusable across phases

Todos los modelos SHOULD ser importables desde `from royaltdn.models import Bar, Order, Signal, Position`.

#### Scenario: Unified import path

- GIVEN `royaltdn/models/__init__.py` que reexporta todos los modelos
- WHEN se importa `from royaltdn.models import Bar`
- THEN SHALL resolver sin error
