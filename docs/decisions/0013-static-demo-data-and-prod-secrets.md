# 0013 — Static demo data in the web bundle; presets from eval cases; production secrets

- Status: Accepted
- Date: 2026-10-28

## Context

Phase 4 puts the demo online. Three things needed deciding:

- **Cold starts.** Cloud Run and Neon both scale to zero, so the first request after a quiet spell takes several seconds. Yet the first sample answer must appear instantly.
- **Preset attacks.** The "Try to break it" panel must test the same thing the CI gate tests (spec §10), not a separate list that can drift.
- **Production secrets.** Until now Cloud Run received only an owner `DATABASE_URL`.

## Decision

- **Demo data is static.** `make samples-build` (and the token-free `make samples-export`) writes `apps/web/data/demo.json`, which the web bundle imports at build time. It holds the personas, the sample questions with their precomputed answers, and the presets with their cached answers.
  - Clicking a sample makes no network call.
  - The landing page and `/assistant` call `/api/health` in the background so the live path is warm by the time a visitor types.
  - A test fails if the committed file is stale.
- **Presets are the eval cases marked `preset: true`.**
  - `GET /api/presets` and `demo.json` read them from `evals/cases/`, which the API image now copies. Each card links to its case on GitHub.
  - Presets run live. `samples-build` caches a preset answer only when it passes that case's eval checks.
  - The cached answer is served when live answers are paused (budget or rate limit) or the API cannot be reached.
- **Cloud Run never holds the owner password.**
  - The production `database-url` secret contains only host, database and `sslmode`.
  - The API connects as persona logins (ADR 0008) and `app_service`, including for `/api/health`.
- **Secrets live in GCP Secret Manager**, one per value:
  - `database-url`;
  - four `agent-db-password-*`;
  - `app-service-db-password`;
  - `anthropic-api-key`, a production-only key with its own Console spend limit, separate from the CI key;
  - `voyage-api-key`;
  - `langfuse-secret-key`.

  Non-secret settings (model names, Langfuse host and public key, `CORS_ORIGINS`) come from GitHub repository variables. `infra/gcp-bootstrap.sh` creates the secret containers and the accessor bindings; the owner adds the values.
- **The daily pipeline runs on both `dev` and `prod`** so relative periods ("last quarter") stay current on the live site.
- **The deploy smoke test requires `db: ok` and a non-empty preset list.** `db: ok` proves `app_service` can log in, which the cost guards depend on.

## Consequences

- Sample answers can lag the live data by up to a rebuild. They record `built_at`, and the cost badge marks them as precomputed.
- Changing a preset's question means re-running `make samples-build` for it. Otherwise the replay falls back to the generic "live answers are paused" message.
- Deploys now also trigger on `evals/cases/**`, so editing a preset ships to the API.
