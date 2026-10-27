# 0004 — Langfuse Cloud instead of self-hosted Langfuse

- Status: Accepted (amends D6 "Langfuse self-hosted on VPS")
- Date: 2026-10-27

## Context

Self-hosted Langfuse v3 needs Postgres, ClickHouse, Redis and object storage — roughly 4 GB of RAM — which does not fit a serverless setup (ADR 0002).

## Decision

- Use **Langfuse Cloud, Hobby (free) tier**. Pick the region at sign-up; all traced data is synthetic, so residency is not a concern.
- The API sends traces with the Langfuse Python SDK; keys come from env (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`).
- The public trace page (post-MVP) reads a trimmed view through the API, never directly from Langfuse in the browser.
- Tracing must never block or fail a request: if Langfuse is unreachable, the answer is still returned and the failure is logged.

## Consequences

- Free-tier quotas and retention apply; check the current limits at sign-up and sample traces if the quota gets close.
- The same tracing code works against a self-hosted instance by changing `LANGFUSE_HOST`, so this is easy to reverse.
