# 0007 — Plain SQL migrations with a small runner

- Status: Accepted
- Date: 2026-10-27

## Context

Most of the schema work in this project is Postgres security: roles, grants, row-level security policies, column grants. These are easiest to review as SQL. The tables themselves are mostly built by dbt (Phase 1), not by the API.

## Options considered

- **Alembic** — the usual Python choice; strong for ORM-driven schemas. Here it would wrap raw SQL in Python files and add an ORM-shaped tool to a project without an ORM.
- **dbmate / Flyway / Sqitch** — solid, but another binary to install in CI and on every machine.
- **Numbered `.sql` files + ~60-line Python runner** — reviewers read the SQL directly; no extra tooling.

## Decision

- Migrations live in `data/sql/migrations/NNNN_name.sql` and are applied in order by `data/sql/migrate.py` (`make db-migrate`, `make db-migrate-prod`).
- Each file runs in its own transaction and is recorded in `public.schema_migrations`; re-running applies nothing.
- A Postgres advisory lock stops two runs interleaving.
- Migrations are forward-only. A mistake is fixed by a new migration, not by editing an applied one.

## Consequences

- No automatic down-migrations. Neon branches give a cheap way to try a migration before running it on prod.
- CI applies every migration to a fresh pgvector container on each PR, so a broken migration fails before merge.
