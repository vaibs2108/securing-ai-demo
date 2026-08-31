# ── Stage 1: build the React frontend ──────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime serving the FastAPI backend + built frontend ───
FROM python:3.11-slim

# uv — the same package manager used for local development
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /usr/local/bin/

# Create a non-root user with UID 1000 (required for Hugging Face Spaces)
RUN useradd -m -u 1000 user

WORKDIR /app

# Install system dependencies required for FAISS and compiling packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy project files with ownership given to the non-root user
COPY --chown=user:user . /app/
COPY --chown=user:user --from=frontend-build /frontend/dist /app/frontend/dist

# Ensure the data directory exists and is owned by the user
RUN mkdir -p /app/data && chown -R user:user /app

# Switch to the non-root user
USER user

# Install Python dependencies exactly as locked in uv.lock, no dev extras (pytest etc.)
RUN uv sync --frozen --no-dev

# Default port for local `docker run` / Hugging Face Spaces. Render and Cloud Run
# inject their own $PORT at runtime, which the shell-form ENTRYPOINT below picks up
# automatically — the same image/Dockerfile works unmodified on all three.
ENV PORT=7860
EXPOSE $PORT

HEALTHCHECK CMD curl --fail http://localhost:${PORT}/healthz || exit 1

# Serves the React frontend (frontend/dist) and the REST API from one process —
# the exact same command used locally (see README.md), just bound to 0.0.0.0:$PORT
# instead of 127.0.0.1:<port>. Shell form (not exec-array form) so $PORT expands.
ENTRYPOINT uv run uvicorn backend.main:app --host=0.0.0.0 --port=${PORT}
