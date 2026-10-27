# 0010 — Embedding model, vector dimension and where documents live

- Status: Accepted (resolves spec §18 "Exact Voyage model and vector dimension")
- Date: 2026-10-27

## Context

ADR 0005 chose Voyage AI and left the model and dimension for the start of Phase 2. Phase 1 did not create any policy documents, and the spec planned to load them into `raw.doc_files` from the generator.

## Decision

- **Model:** `voyage-4-lite`, set in `EMBEDDING_MODEL`. It is Voyage's current lite tier, aimed at low latency and cost, with a 32k-token context. The corpus is ~15 short documents (~5k tokens), so a larger model buys nothing we could measure yet.
- **Dimension:** 1024 (the model's default). It is fixed in `retrieval.doc_chunks.embedding vector(1024)` (migration 0004) and in `EMBEDDING_DIM` in code. At this corpus size, storage and index speed are irrelevant, so we keep the default rather than tune it.
- **Input types:** documents are embedded with `input_type="document"`, queries with `input_type="query"`.
- **Documents live in the repo** as markdown with YAML front matter (`data/documents/*.md`: `id`, `title`, `allowed_roles`, `region`), not in `raw.doc_files`. Reviewers can read the policies the agent cites, and access metadata sits next to the text it protects. `make docs-embed` chunks them at `##` headings, skips unchanged files by hash, and writes `retrieval.documents` / `retrieval.doc_chunks` as the owner. The daily pipeline runs it after `dbt build`.

## Consequences

- Changing model or dimension means a new migration and a full re-embed, recorded in a new ADR; the `retrieval` eval category (Phase 3) measures whether the change helped.
- Without a payment method on the Voyage account, the rate limit is 3 requests/minute and 10k tokens/minute. Ingest sends one request for all changed documents to fit. Live query embedding at that limit would cap the demo at 3 searches a minute, so a payment method must be added before launch (free tokens still apply).
- `raw.doc_files` is dropped from spec §5.1.
