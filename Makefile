# Commands documented in CLAUDE.md. Keep them working.

# Load .env when it exists (local development); CI passes env vars directly.
ENV_FILE := $(if $(wildcard .env),--env-file .env,)
UV_RUN := uv run --all-packages $(ENV_FILE)

.PHONY: setup setup-py setup-web db-migrate db-migrate-prod data-generate dbt-build \
	api-dev web-dev test test-py test-web eval lint lint-py lint-web

setup: setup-py setup-web

setup-py:
	uv sync --all-packages

setup-web:
	pnpm install --frozen-lockfile

db-migrate:
	$(UV_RUN) python data/sql/migrate.py --target dev

db-migrate-prod:
	$(UV_RUN) python data/sql/migrate.py --target prod

data-generate:
	@echo "data-generate: not implemented yet (Phase 1)"

dbt-build:
	@echo "dbt-build: not implemented yet (Phase 1)"

api-dev:
	$(UV_RUN) uvicorn app.main:app --reload --port 8000

web-dev:
	pnpm --filter web dev

test: test-py test-web

test-py:
	$(UV_RUN) pytest

test-web:
	pnpm --filter web test

eval:
	@echo "eval: not implemented yet (Phase 3)"

lint: lint-py lint-web

lint-py:
	uv run --all-packages ruff check .
	uv run --all-packages ruff format --check .
	uv run --all-packages mypy
	uv run --all-packages sqlfluff lint data/sql

lint-web:
	pnpm --filter web lint
