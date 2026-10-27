# Commands documented in CLAUDE.md. Keep them working.

# Load .env when it exists (local development); CI passes env vars directly.
ENV_FILE := $(if $(wildcard .env),--env-file .env,)
UV_RUN := uv run --all-packages $(ENV_FILE)
TARGET ?= dev
SCALE ?= full

.PHONY: setup setup-py setup-web db-migrate db-migrate-prod data-generate data-append dbt-build db-users \
	api-dev web-dev test test-py test-web eval lint lint-py lint-web

setup: setup-py setup-web

setup-py:
	uv sync --all-packages

setup-web:
	pnpm install --frozen-lockfile

db-migrate:
	$(UV_RUN) python data/sql/migrate.py --target $(TARGET)

db-migrate-prod:
	$(UV_RUN) python data/sql/migrate.py --target prod

data-generate:
	$(UV_RUN) python -m generator --target $(TARGET) --scale $(SCALE)

data-append:
	$(UV_RUN) python -m generator --target $(TARGET) --scale $(SCALE) --append $(DATE)

dbt-build:
	$(UV_RUN) python data/dbt/run.py --target $(TARGET) build
	$(UV_RUN) python data/sql/apply_security.py --target $(TARGET)
	$(UV_RUN) python data/dbt/run.py --target $(TARGET) source freshness

db-users:
	$(UV_RUN) python data/sql/set_passwords.py --target $(TARGET)

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
	uv run --all-packages sqlfluff lint data/sql data/dbt/models

lint-web:
	pnpm --filter web lint
