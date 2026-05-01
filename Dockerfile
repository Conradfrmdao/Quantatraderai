# ── QuntaTradeAI — Python API Server ──────────────────────────────
# Multi-stage build: builder installs deps, runner is minimal.
#
# Build:  docker build -t quntatradeai .
# Run:    docker run --env-file .env -p 8000:8000 quntatradeai
#
# ──────────────────────────────────────────────────────────────────

# Stage 1: build — install Poetry and all dependencies
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_IN_PROJECT=true

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --no-interaction --no-ansi --without dev

# Stage 2: runtime — copy only what's needed
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /app/.venv ./.venv

# Copy application source
COPY src     ./src
COPY risk.yaml ./risk.yaml

# Non-root user for security
RUN useradd -r -u 1001 qunta && chown -R qunta:qunta /app
USER qunta

# API server port
ENV API_PORT=8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${API_PORT}/api/status')" || exit 1

CMD ["python", "src/server.py"]
