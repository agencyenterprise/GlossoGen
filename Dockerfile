FROM python:3.12-slim

# System deps for weasyprint (PDF export), git (run history), and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Phase 1: install dependencies (cached unless pyproject.toml or uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Phase 2: install the project itself
COPY src/ src/
RUN uv sync --frozen --no-dev

RUN mkdir -p /data/runs

ENV SCHMIDT_RUNS_DIR=/data/runs

# Railway injects $PORT at runtime
CMD uv run --no-sync python -m schmidt serve --runs-dir /data/runs --port ${PORT:-8000}
