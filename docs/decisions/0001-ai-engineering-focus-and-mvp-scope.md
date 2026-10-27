# 0001 — AI engineering focus and a one-week MVP

- Status: Accepted
- Date: 2026-10-27

## Context

The spec (v0.1) gave equal weight to data engineering (generator, dbt, Dagster, lineage) and AI engineering (agent, evals, guardrails). The author already has professional data engineering experience that is easy to evidence on a CV and in interviews. AI engineering is the gap the portfolio needs to close.

The author also wants a live MVP link for the CV within the first week, built with Claude Code as a pair.

## Decision

1. **Primary signal is AI engineering.** Effort goes first to: evals as a merge gate, agent + tools, database-enforced access control as the defence against prompt injection, tracing and cost per answer, retrieval quality, and an MCP server.
2. **The data side is "just enough".** Generator and dbt marts exist so questions have interesting, correct answers. They keep tests and quality, but no model is built unless the agent or an eval needs it. No orchestration platform (see ADR 0003).
3. **MVP in one week** (Phases 0–4 in `docs/phases.md`). Out of MVP: compare, pipeline, trace and evals pages; MCP server; model comparison; `create_ticket`; Turnstile; Document-to-Data Pipeline.
4. **Evals start with the agent, not after it.** The MVP ships with ~30 cases and a CI gate; `access_control` must be 100%.
5. **New post-MVP item: model comparison.** Run the same eval set against the main and small models and report quality, latency and cost per answer.
6. **Snowflake edition (D2) is dropped.**

## Working with Claude Code

Code is written with Claude Code. To keep every decision defensible in an interview: small PRs reviewed by the author, an ADR for every significant choice (including rejected alternatives), and tests that prove the security claims rather than describe them.

## Consequences

- Phase plan is rewritten around the MVP; the data phase shrinks from two weeks to about one day.
- The pipeline/lineage page loses prominence; it can return later using the dbt manifest.
- Risk: a one-week MVP leaves little slack. Day 5 (getting evals green) is the most likely to overrun; the cut line is the web polish, never the eval gate or cost guards.
