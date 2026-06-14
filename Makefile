# RoyalTDN — Makefile
# Comandos comunes para desarrollo Fase 0
# Usa: make <comando>

.PHONY: install run check clean lint type test

# ── Instalación ────────────────────────────────────────────────────────────────

venv:
	python3 -m venv .venv
	@echo "✅ Entorno virtual creado. Activa con: source .venv/bin/activate"

install:
	pip install -e .
	@echo "✅ Dependencias instaladas (editable)"

install-dev: install
	pip install pytest pytest-asyncio ruff mypy
	@echo "✅ Dev dependencies instaladas"

# ── Ejecución ──────────────────────────────────────────────────────────────────

run:
	python -m royaltdn run

check:
	python -m royaltdn check

# ── Mantenimiento ──────────────────────────────────────────────────────────────

clean:
	rm -rf .venv/ __pycache__/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf *.egg-info/ dist/ build/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Limpieza completa"

lint:
	ruff check src/

type:
	mypy src/

test:
	python -m pytest tests/ -v

# ── Notebooks ──────────────────────────────────────────────────────────────────

jupyter:
	jupyter lab
