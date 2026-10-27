# 0011 — Answer card built from tool results; cached sample answers

- Status: Accepted
- Date: 2026-10-27

## Context

Spec §8.1 had the main model return the final answer as structured output, including the table and chart. Phase 2 surfaced three problems:

1. A model that retypes a table can change a number, and nothing in the card would show it.
2. Constraining every text block to JSON (`output_config.format`) while tools were available made the model pad with no-op tool calls (`select 1`, repeated identical queries) instead of answering: it had nowhere to write between calls. Forced tool choice is not available on current models, so the answer could not be forced through a tool either.
3. The late-payer story ("pays later each quarter") had no metric, so the agent fell back to exploratory SQL and often ran out of steps.

## Decision

- **The model finishes by calling a `final_answer` tool** (strict schema, not forced; the prompt says to call it last). Its input holds `text`, `assumptions`, `table_result_id`, `table_rows`, `chart` and `citations`. A plain-text ending is still shown, flagged in `issues`.
- **Tables come from tool results, not from the model.** Every tool result has an id; the answer points at one (and optionally its first N rows). The API builds the table, checks that chart columns exist in it, keeps only citations that were actually retrieved, and attaches the SQL and any denials from the stored results. Anything that does not resolve is dropped and listed in `issues`.
- **Identical repeat tool calls are refused** with a pointer to the earlier result id.
- **Sample answers are precomputed and committed** (`services/api/app/samples/answers/*.json`), built with `make samples-build`, which runs each sample live and writes only answers that pass their expectations. The API serves them for sample questions (free and instant) and they back replay mode. The spec's "built at deploy" would spend LLM budget on every deploy and make deploys depend on the model API.
- **New metric `avg_days_to_pay`** (finance only), the tenth semantic-layer metric, for the late-payer story.

## Consequences

- The card cannot show a number that no tool returned, and the eval runner (Phase 3) can check answers against tool results directly.
- Sample answers can go stale as the daily pipeline adds data; rebuild them when prompts, tools or data shape change (they record `built_at`).
- On the 21 samples: 21/21 pass; most answers use one tool call, ~$0.014 and 6–8 s each.
