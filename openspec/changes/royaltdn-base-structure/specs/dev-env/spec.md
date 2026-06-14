# Development Environment Specification

## Purpose

Define el entorno de desarrollo para RoyalTDN Fase 0: dependencias divididas por fase, reglas de git, variables de entorno, y automatización con Makefile.

## Requirements

### Requirement: Requirements split by phase

Las dependencias MUST organizarse en archivos separados bajo `requirements/`. Fase 0 usa `fase0.txt`. Los archivos posteriores (`fase1.txt`, `fase2.txt`, etc.) deben referenciar al anterior con `-r`.

#### Scenario: Install Fase 0 dependencies

- GIVEN el archivo `requirements/fase0.txt` con pandas, numpy, alpaca-py, python-dotenv, jupyterlab, matplotlib, yfinance
- WHEN se ejecuta `pip install -r requirements/fase0.txt`
- THEN todas las dependencias SHALL instalarse sin error

### Requirement: .gitignore covers all project layers

`.gitignore` MUST ignorar: `__pycache__/`, `*.py[cod]`, `*.egg-info/`, `venv/`, `.venv/`, `.env`, `.env.local`, `data/raw/*`, `data/processed/*`, `data/parquet/*`, `.ipynb_checkpoints/`, `.vscode/`, `.idea/`, `.DS_Store`.

#### Scenario: .env is ignored by git

- GIVEN un archivo `.env` con claves API
- WHEN se ejecuta `git status`
- THEN `.env` NO SHALL aparecer en el listado

#### Scenario: Data subdirectories preserve gitkeep

- GIVEN que `data/raw/` está vacío
- WHEN se listan archivos en git
- THEN `data/**/.gitkeep` SHALL existir para preservar la estructura

### Requirement: .env.example documents all variables

`.env.example` MUST documentar todas las variables configurables con nombres, comentario de propósito, y marcadas como opcionales por fase. NO SHALL contener valores reales.

#### Scenario: Template matches Settings model

- GIVEN que `config/settings.py` define un campo `TELEGRAM_TOKEN`
- WHEN se inspecciona `.env.example`
- THEN `TELEGRAM_TOKEN` SHALL aparecer comentado con su propósito y fase

### Requirement: Makefile for common tasks

Un `Makefile` SHOULD existir en la raíz con comandos: `install` (pip install -e .), `dev` (pip install -r requirements/fase0.txt), `test` (pytest), `lint` (ruff check), `clean` (remove __pycache__ y .pyc), `run` (python -m royaltdn.main run).

#### Scenario: Make install sets up editable package

- GIVEN `pyproject.toml` configurado
- WHEN se ejecuta `make install`
- THEN `pip install -e .` SHALL ejecutarse y el paquete SHALL ser importable como `royaltdn`

### Requirement: No Docker or CI in Fase 0

NO SHALL existir `Dockerfile`, `docker-compose.yml`, ni `.github/workflows/` en Fase 0. Estos SHALL añadirse en Fase 2+ según el roadmap.

#### Scenario: Verify no Docker infrastructure

- GIVEN la raíz del proyecto
- WHEN se buscan archivos `Dockerfile` o `docker-compose.yml`
- THEN NO SHALL existir ninguno
