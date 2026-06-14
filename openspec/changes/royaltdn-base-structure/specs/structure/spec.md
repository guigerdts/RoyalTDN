# Project Structure Specification

## Purpose

Define la estructura de directorios y la configuración del paquete Python para RoyalTDN. Sigue el src-layout estándar para evitar conflictos de import y separa responsabilidades por módulo según el roadmap.

## Requirements

### Requirement: src-layout package root

El proyecto MUST usar `src/royaltdn/` como raíz del paquete Python. El `pyproject.toml` MUST definir metadatos del proyecto (name, version, authors) y configurar `[build-system]` con setuptools.

#### Scenario: Package installs with pip install -e .

- GIVEN el proyecto clonado en `/root/RoyalTDN/`
- WHEN se ejecuta `pip install -e .` desde la raíz del proyecto
- THEN `python -c "import royaltdn"` SHALL importar sin error

#### Scenario: Conflict-free imports

- GIVEN un directorio `tests/` en la raíz del proyecto
- WHEN cualquier módulo en `tests/` importa `royaltdn`
- THEN Python SHALL resolver al paquete bajo `src/royaltdn/`, no a otro `royaltdn` en el PATH

### Requirement: Module directories as placeholders

Los subdirectorios `ingestion/`, `strategy/`, `risk/`, `execution/`, `models/`, `storage/`, `monitoring/`, `config/` bajo `src/royaltdn/` MUST existir. Cada uno SHALL contener solo un `__init__.py` con un comentario descriptivo de su responsabilidad futura. Ninguno SHALL contener código de implementación.

#### Scenario: All module directories exist

- GIVEN el paquete `src/royaltdn/`
- WHEN se listan sus subdirectorios
- THEN los ocho módulos SHALL existir con `__init__.py` cada uno

#### Scenario: Empty placeholder enforcement

- GIVEN cualquier módulo placeholder
- WHEN se inspecciona su contenido
- THEN NO SHALL contener archivos `.py` adicionales al `__init__.py`

### Requirement: Test directory mirrors source

`tests/` SHALL contener subdirectorios `unit/`, `integration/`, `smoke/`. Cada uno SHALL tener `__init__.py`. Test files SHOULD seguir la estructura de `src/royaltdn/`.

#### Scenario: Test directories exist

- GIVEN el directorio `tests/`
- WHEN se listan sus subdirectorios
- THEN `unit/`, `integration/`, `smoke/` SHALL existir

### Requirement: Data directory with subdirectories

`data/` SHALL contener `raw/`, `processed/`, `parquet/` para almacenar datos de mercado en distintos estados de procesamiento.

#### Scenario: Data subdirectories exist

- GIVEN el directorio `data/`
- WHEN se listan sus entradas
- THEN `raw/`, `processed/`, `parquet/` SHALL existir
