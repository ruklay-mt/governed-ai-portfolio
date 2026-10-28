# API image for Cloud Run. Build from the repo root:
#   docker build -f infra/api.Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/srv/.venv

RUN pip install --no-cache-dir uv==0.12.5

WORKDIR /srv

# Dependencies first, so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/
COPY data/generator/pyproject.toml data/generator/
RUN uv sync --frozen --no-dev --package harbourline-api --no-install-workspace

COPY services/api services/api
# Presets for "Try to break it" are the eval cases marked `preset: true` (ADR 0013).
COPY evals/cases evals/cases
RUN uv sync --frozen --no-dev --package harbourline-api

RUN useradd --system --no-create-home app
USER app

ENV PATH=/srv/.venv/bin:$PATH \
    PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
