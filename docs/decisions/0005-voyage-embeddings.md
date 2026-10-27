# 0005 — Hosted embeddings with Voyage AI

- Status: Accepted (resolves spec §7.4)
- Date: 2026-10-27

## Context

Document chunks are embedded in the pipeline; each search embeds the query at request time. The API runs on Cloud Run with scale to zero (ADR 0002).

## Options considered

- **Local model** (`bge-small`, `e5-small`) — no API cost, but adds a few hundred MB to the image, raises cold-start time and memory.
- **Voyage AI** — the embedding provider Anthropic recommends; generous free token allowance; one HTTP call per query.
- OpenAI embeddings — also fine; adds a second LLM vendor for no clear gain.

## Decision

- Use Voyage AI. The model name comes from env `EMBEDDING_MODEL` (default: a lite-tier Voyage model chosen when Phase 2 starts); the API key from `VOYAGE_API_KEY`.
- The vector dimension is fixed in the migration that creates `retrieval.doc_chunks`; changing model means a new migration and a re-embed, recorded in a new ADR.
- Retrieval quality is measured by the `retrieval` eval category, so a model change is tested, not assumed.

## Consequences

- One more account and secret.
- Query embedding adds a network round trip (tens of milliseconds) per search; visible in traces.
