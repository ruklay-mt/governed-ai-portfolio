# Phases

Work one phase at a time. Start each phase in plan mode. Tick a box only when its acceptance check passes.

Phases 0–4 are the **one-week MVP** (ADR 0001): one phase per day or two, ending with a live link for the CV. The cut line if the week runs short is web polish — never the eval gate, access-control tests or cost guards.

Before Phase 0, the author creates accounts and keys (Claude cannot enter credentials). The step-by-step sign-up guide and working notes are kept locally in `notes/` (git-ignored).
- GitHub repo (public), Neon project (Sydney, `main` = prod + `dev` branch)
- Google Cloud project with billing, budget alert ~US$5, `gcloud` CLI installed
- Anthropic API key with a monthly spend limit; Langfuse Cloud (Hobby); Vercel (Hobby); Voyage AI key

---

## MVP

### Phase 0 — Repo, CI and deploy skeleton (day 1)

- [x] Monorepo skeleton matching `CLAUDE.md` layout; `Makefile` with all listed targets (stubs allowed)
- [x] `uv` workspace for Python, `pnpm` workspace for web; `.env.example` with every variable used
- [x] Plain-SQL migration runner; `make db-migrate` creates schemas `raw`, `staging`, `intermediate`, `marts`, `retrieval`, `ops`, `evals`, `docflow` and the `vector` extension, on Neon `dev` and `main`
- [x] FastAPI skeleton with `/api/health`; Next.js skeleton
- [x] GitHub Actions `ci.yml`: lint + unit tests + migration smoke test (pgvector service container) on every PR
- [x] GitHub Actions `deploy.yml`: build image, push to Artifact Registry, deploy to Cloud Run via Workload Identity Federation

**Done when:** a fresh clone runs `make setup && make db-migrate && make test` green; CI passes on an empty PR; the Cloud Run URL returns 200 from `/api/health`.

### Phase 1 — Data foundation, just enough (day 2)

- [x] Seeded generator for the **[MVP]** sources in spec §5.1, with the four planted stories (spec §4.1) and daily append mode
- [x] dbt staging → intermediate → **[MVP]** marts (spec §5.2), with key, relationship and freshness tests
- [x] Per-persona read-only logins and `app_service` (ADR 0008); persona roles, `ops.persona_scope`, RLS policies and column grants per spec §6 in `data/sql/`
- [x] Access-control test suite: for every role, forbidden rows and columns are unreachable via direct SQL, including `set_config` spoofing, `SET ROLE` and writes
- [x] `pipeline.yml`: daily generator append → `dbt build` → row in `ops.pipeline_runs`

**Done when:** `make data-generate && make dbt-build` succeeds with all tests green; access-control suite passes for all 4 roles; a manual run of `pipeline.yml` succeeds against `dev`.

### Phase 2 — Agent core (days 3–4)

- [x] ~15 policy documents, chunked and embedded (Voyage) into `retrieval.doc_chunks` with `allowed_roles`; ADR note for the chosen model and dimension
- [x] Semantic layer YAML (9 MVP metrics) + compiler with unit tests (spec §7)
- [x] **[MVP]** tools (spec §8.2), each running under the caller's role in a transaction
- [x] SQL guard with sqlglot; tests for blocked statements
- [x] Hybrid document search with RLS
- [x] Agent loop with guard step, streaming SSE, structured final answer
- [x] API: health, personas, samples, chat
- [x] Langfuse tracing for every request; `trace_id` returned
- [x] Cost guards (spec §16): per-session/IP limits and daily budget in `ops.*`, replay mode

**Done when:** locally, each persona gets a correct answer to 5 sample questions; a sales rep asking for margin gets a clear refusal; tool-level tests prove `run_sql` cannot read a hidden column; exceeding the budget switches to replay mode.

### Phase 3 — Eval gate (day 5)

- [x] Eval case format and runner (spec §12); ~30 cases across 4 categories
- [x] Deterministic checkers; LLM-as-judge with rubric only where needed
- [x] `evals.yml` runs on relevant PRs against Neon `dev` and fails under threshold (broken-prompt check: #14)
- [x] Out-of-scope and injection cases pass

**Done when:** `make eval` writes a report to `evals/reports/`; `access_control` is 100% and overall ≥ 85%; a deliberately broken prompt change fails CI.

### Phase 4 — Web and launch (days 6–7)

- [x] `/assistant`: persona switcher, sample questions (precomputed answers), streamed answer, Show SQL, citations, cost/latency badge, "How this answer was built" steps, access-denied explanation, warming-up state
- [x] "Try to break it" panel: preset attacks run live (precomputed in replay mode), each linked to its eval case (spec §10)
- [x] Plain `/` landing page with links to CV, LinkedIn, GitHub
- [x] Prod data loaded on Neon `main`; API on Cloud Run with secrets from Secret Manager; web on Vercel; CORS locked to the site domain
- [x] README: what it is, architecture diagram, how it was built with Claude Code, local run instructions

**Done when:** on the live URL, each persona gets a correct answer to 5 sample questions, the margin refusal works, every "Try to break it" preset is refused, and the first sample answer shows instantly on a cold start. **MVP link goes on the CV.**

---

## After MVP

### Phase 5 — Deepen the AI engineering story

- [ ] Remote MCP server + `/assistant/mcp` page (spec §11)
- [ ] Model comparison on the eval set: pass rate, latency, cost per answer (spec §12)
- [ ] Expand evals to ~80 cases; documents to ~40
- [ ] API + pages: evals (latest, history, model comparison), trace view
- [ ] `/assistant/compare` with cached answers for sample questions
- [ ] `create_ticket` with confirmation flow; `get_ticket` / `list_tickets`
- [ ] Turnstile before the first live question
- [ ] `/about`, `/assistant/architecture`; visual design pass; 2-minute demo video

**Done when:** Claude Desktop connects to the MCP server and answers a metric question; the evals page shows a model comparison; a first-time visitor on mobile and desktop completes the 3-minute journey without errors.

### Phase 6 — Document-to-Data Pipeline

- [ ] ERP purchasing tables and marts needed for matching (spec §5)
- [ ] Sample document generator (~50 docs) with ground-truth JSON
- [ ] Extraction with structured output and per-field confidence
- [ ] Validation rules and 3-way matching against ERP marts
- [ ] Review queue and correction endpoint
- [ ] `/docflow` page per final design
- [ ] Field-level evals and metrics endpoint

**Done when:** the sample set reaches the target field accuracy agreed after the first run; all planted errors are caught by rules or flagged for review; page works end to end on the live site.

### Phase 7 — Extras

- [ ] Daily health check and alert (GitHub Actions cron), including a stale `ops.pipeline_runs` check
- [ ] Optional pipeline/lineage page from the dbt manifest
- [ ] LinkedIn write-up of key design decisions

**Done when:** the health check alerts on a forced failure.
