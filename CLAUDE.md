# CLAUDE.md

Guidance for Claude Code working in this repository. Read this file, then `docs/spec.md` and `docs/phases.md`, before starting any task.

## What this repo is

A public portfolio for a Senior Data & AI Engineer. One website with two live demos that hiring managers can try in under 3 minutes:

1. **Governed AI Data Assistant** (main project) — an AI agent over a fictional company's ERP, CRM, service-desk and policy-document data. Answers change by role, every answer shows its evidence (SQL, citations), and access control is enforced in the database, not the prompt.
2. **Document-to-Data Pipeline** (secondary project) — upload an invoice or PO, the LLM extracts structured data, deterministic rules validate it, and it is matched against ERP data.

The audience is technical hiring managers in NZ/AU. Quality of engineering decisions matters more than feature count.

## Repo layout

```
apps/web/                 Next.js frontend (portfolio site + both demos)
services/api/             FastAPI backend (agent, docflow, read APIs)
  app/agent/              agent loop, tools, guardrails, prompts
  app/semantic/           YAML semantic layer -> SQL compiler
  app/retrieval/          hybrid search over documents
  app/docflow/            Project 2: extraction, validation, matching
  app/mcp/                MCP server exposing the agent tools
  app/evals/              eval runner, checkers, LLM judge, report
data/generator/           Python synthetic data generator
data/dbt/                 dbt project (staging -> intermediate -> marts)
data/sql/                 migrations: schemas, roles, RLS policies, grants
evals/                    golden-set cases (YAML), gate config, reports
infra/                    API Dockerfile, GCP bootstrap script
.github/workflows/        ci, evals, pipeline (daily data run), deploy
docs/                     spec.md, phases.md, decisions/ (ADRs)
notes/                    author's local study notes (git-ignored, never commit)
```

## Stack (see `docs/spec.md` §2 and `docs/decisions/`)

- Python 3.12, managed with `uv`. Node 20+, managed with `pnpm`.
- Postgres on Neon + `pgvector`. dbt Core (`dbt-postgres`). No orchestration platform: the daily pipeline is a scheduled GitHub Actions workflow.
- FastAPI + Anthropic Python SDK (Claude API, tool use). Pydantic v2. Voyage AI embeddings.
- API on Google Cloud Run (`australia-southeast1`); web on Vercel. No VPS, no local Docker needed.
- Next.js (App Router, TypeScript). Tailwind. Charts with Recharts.
- Langfuse Cloud for traces. GitHub Actions for CI and deploy.

## Focus

The portfolio's primary signal is AI engineering (ADR 0001): evals, agent + tools, DB-enforced access control, observability and cost. Keep the data layer just big enough for the agent and evals. Phases 0–4 in `docs/phases.md` are a one-week MVP.

## Commands

Keep these working; update this section when you add or change one.

```
make setup          # install python + node deps
make db-migrate     # apply schema, roles, RLS policies (DATABASE_URL, Neon dev)
make db-migrate-prod  # same, against DATABASE_URL_PROD (Neon main)
make data-generate  # full rebuild of synthetic source data into raw (SCALE=small for CI)
make data-append    # add today's data (DATE=YYYY-MM-DD for another day); idempotent
make dbt-build      # dbt build (models + tests), re-apply marts access policy, freshness
make docs-embed     # chunk + embed data/documents/*.md into retrieval.* (changed files only)
make db-users       # set persona login passwords from .env (ADR 0008)
                    # data and dbt targets take TARGET=dev|prod (default dev)
make api-dev        # run FastAPI locally
make web-dev        # run Next.js locally
make agent-smoke    # run sample questions live, check expectations (spends tokens; ARGS="--only id")
make samples-build  # same, and write passing answers to services/api/app/samples/answers/
make test           # unit tests (pytest + vitest)
make eval           # run golden-set evals on dev, write report to evals/reports/, fail under
                    # the gate (spends tokens, ~US$0.45; ARGS="--only id" / "--repeat 3")
make lint           # ruff, mypy, eslint, sqlfluff
```

## Non-negotiable rules

1. **Synthetic data only.** Never use, copy or paraphrase code, schemas, semantic models or data from any real employer or client.
2. **Access control lives in the database.** Every query and every document search runs as the caller's own persona login (one read-only DB user per persona, ADR 0008), inside a transaction. RLS scope comes from `session_user`, never from a session setting the SQL could change (`set_config`). Never filter by role only in Python or in the prompt. If a tool can bypass RLS or change its own scope, it is a bug.
3. **The LLM never gets a privileged connection.** The agent's DB user is read-only and owns nothing. Writes (e.g. create ticket) go through a separate, narrow endpoint that requires user confirmation.
4. **Generated SQL is untrusted.** Parse with `sqlglot`, allow a single `SELECT`, enforce `LIMIT` and `statement_timeout`.
5. **No secrets in the repo.** Use `.env` (git-ignored) and `.env.example`. Model names come from env vars, not hard-coded strings.
6. **Cost is a feature.** Respect the budget guards in `docs/spec.md` §14. Never remove rate limits or spend caps to make a test pass.
7. **Evals gate merges.** A change to prompts, tools, retrieval or the semantic layer must run `make eval`. Do not lower thresholds to pass.

## How to work

- Work one phase at a time from `docs/phases.md`. Start each phase in plan mode; list files to create/change and how you will verify them.
- A task is done only when its acceptance criteria in `docs/phases.md` pass. Tick the checkbox there in the same commit.
- Record any decision that changes the spec as a short ADR in `docs/decisions/NNNN-title.md` and update `docs/spec.md`.
- Small, focused commits with conventional-commit messages (`feat(agent): ...`, `fix(dbt): ...`).
- Write tests alongside code: pytest for Python, vitest for web utilities, dbt tests for every mart's keys and not-null columns.
- Prefer boring, readable code over clever code. This repo will be read by reviewers.

## Style

- Python: ruff + mypy (strict on `app/`), type hints everywhere, Pydantic models at API boundaries.
- SQL: lowercase keywords, snake_case, one CTE per logical step, sqlfluff (postgres dialect).
- TypeScript: strict mode, server components by default, no `any`.
- All user-facing text in English, Australian/NZ spelling.
