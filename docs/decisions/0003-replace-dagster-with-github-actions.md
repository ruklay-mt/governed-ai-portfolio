# 0003 — Replace Dagster with a scheduled GitHub Actions workflow

- Status: Accepted (replaces D3 "Dagster")
- Date: 2026-10-27

## Context

Dagster's webserver and daemon need an always-on host, which went away with the VPS (ADR 0002). Orchestration is also not the signal this portfolio is optimising for (ADR 0001); the author's orchestration experience is evidenced elsewhere.

The pipeline itself is small: append a day of synthetic data, run `dbt build` (models + tests + source freshness), embed any new or changed documents.

## Options considered

- Dagster+ Serverless — managed, but a paid plan for a one-person demo.
- Dagster on Cloud Run Jobs + Cloud Scheduler — possible, but still needs a persistent run store and a UI host.
- **GitHub Actions scheduled workflow** — free for a public repo, logs are public, no extra infrastructure.

## Decision

- `.github/workflows/pipeline.yml` runs daily (and on manual dispatch): generator append → `dbt build` → embed changed documents → write a run summary row to `ops.pipeline_runs`.
- The same steps run locally via `make data-generate && make dbt-build`.
- The dbt `manifest.json` and `run_results.json` are kept as workflow artefacts; the future pipeline page reads lineage from the manifest and status from `ops.pipeline_runs`.
- `data/orchestration/` is removed from the layout.

## Consequences

- No asset-graph UI. Lineage can be shown later from the dbt manifest.
- GitHub disables scheduled workflows after 60 days without repository activity; the daily health check (Phase 7) watches for a stale `ops.pipeline_runs`.
- If orchestration becomes worth showing later, the steps map one-to-one onto Dagster assets.
