# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the React frontend
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime with uv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# uv from the official installer image (no pip installs — uv only).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV HF_HOME=/app/.cache/huggingface \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Lockfile first: dependency layer only changes when pyproject/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Bake the MiniLM embedder into the image so the container never downloads
# weights at boot (cold-start penalty) — HF_HOME points into the image.
RUN uv run --no-sync python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Application code. The repo-relative layout is preserved so:
#   - db.py's SCHEMA_PATH (../db/schema.sql) resolves to /app/db/schema.sql
#   - backend/main.py's DIST_DIR (frontend/dist) resolves to /app/frontend/dist
COPY soccer_agent/ soccer_agent/
COPY backend/ backend/
COPY db/ db/
COPY data/ data/
COPY --from=frontend-build /build/frontend/dist frontend/dist

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

# Shell form so ${PORT} is expanded at runtime (Cloud Run sets PORT=8080).
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
