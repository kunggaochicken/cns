# syntax=docker/dockerfile:1.6

# ---- Stage 1: build the React frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim AS runtime

# uv is the dependency manager
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

# System deps Kuzu and sqlite-vec need
RUN apt-get update && apt-get install -y --no-install-recommends \
        libstdc++6 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY backend/pyproject.toml backend/uv.lock ./backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev

# Copy backend source
COPY backend/ /app/backend/

# Copy built frontend to where mount_frontend looks (parents[3]/frontend/dist
# from backend/app/api/frontend.py — that resolves to /app/frontend/dist).
COPY --from=frontend-build /src/dist /app/frontend/dist

# Data dir mounted as a volume in docker-compose; create with permissive ownership.
RUN mkdir -p /data && chown -R 1000:1000 /data && chown -R 1000:1000 /app

ENV GIGABRAIN_CONFIG=/app/backend/gigabrain.docker.yaml \
    PATH=/app/backend/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Run as a non-root user (no shell + writable home for any future cache dirs)
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /home/appuser
USER appuser
WORKDIR /app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
