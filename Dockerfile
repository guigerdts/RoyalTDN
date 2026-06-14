# RoyalTDN — Dockerfile Multi-Stage
# Roadmap Fase 3: Infraestructura Profesional
# Documento 05, sección 5.3.1

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1: Builder — compilar dependencias nativas
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.10-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copiar requirements primero para cachear capa de instalación
COPY requirements/ ./requirements/

# Instalar dependencias base
RUN pip install --no-cache-dir --user \
    -r requirements/fase0.txt

# Instalar dependencias Fase 2 (vectorbt, risk, telegram)
RUN pip install --no-cache-dir --user \
    -r requirements/fase2.txt 2>/dev/null || true

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2: Production — runtime mínimo
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.10-slim AS production

LABEL maintainer="RoyalTDN"
LABEL description="RoyalTDN — Algoritmic Trading Bot"
LABEL phase="fase3"

# Dependencias runtime mínimas (sin build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias instaladas desde builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Crear usuario no-root
RUN groupadd -r royaltdn && useradd -r -g royaltdn -d /app royaltdn

WORKDIR /app

# Copiar el código fuente
COPY src/ ./src/
COPY pyproject.toml .

# Instalar el paquete en modo no-editable (solo runtime)
RUN pip install --no-cache-dir --no-deps .

# Directorios de datos
RUN mkdir -p /app/data/raw /app/data/processed /app/logs && \
    chown -R royaltdn:royaltdn /app

USER royaltdn

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import royaltdn; print('OK')" || exit 1

ENTRYPOINT ["python", "-m", "royaltdn"]
CMD ["run"]
