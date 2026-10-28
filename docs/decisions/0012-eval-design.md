# 0012 — Eval design: multi-check cases, deterministic first, single attempt

- Status: Accepted
- Date: 2026-10-28

## Context

Spec §12 sketched one check type per case (`result_match | must_contain | must_refuse | judge`). Writing the access-control cases showed that one check is not enough: "the agent declined" says nothing about whether the hidden rows or columns reached the tool results or the table. The gate also needed rules for LLM non-determinism, eval spend in CI, and where the code lives.

## Decision

- **A case lists several checks and passes only if all pass** (`app/evals/cases.py`). Checks: `table`, `contains`, `must_not_contain`, `citations`, `no_citations_from`, `refused` (`denied | out_of_scope | any | none`), `forbidden_columns` (answer table and every tool result), `only_values`, `tools_used`, `tools_not_used`, `result_match`, `judge`.
- **`result_match` runs a reference query as a persona login at eval time**, so RLS and grants apply to the reference too and relative periods follow the daily data. `as_persona` + `absent: true` turns it into a leakage check: values a more privileged persona can see must not appear in the answer.
- **Deterministic first; LLM-as-judge only for free-text quality** (3 of 31 cases), using `MODEL_SMALL` with a rubric and a strict JSON verdict.
- **Gate:** `access_control` = 100% and overall ≥ 85% (`evals/config.yml`). A run that is aborted or empty fails.
- **One attempt per case, no retries.** A retry hides a flaky answer instead of measuring it; `--repeat N` measures flakiness locally. Access-control checks test what the database returned, which is not the flaky part.
- **Cost:** the run stops and fails at `max_cost_usd` (US$1.50; a full run is ~US$0.45). CI uses its own Anthropic key with its own Console spend limit and runs only on PRs touching agent, semantic, retrieval or eval paths. Eval spend is stored in `evals.eval_runs`, not `ops.daily_spend` (the public site's budget).
- **Results** go to `evals/reports/` (JSON + Markdown, git-ignored; uploaded as a CI artifact and shown in the job summary) and to `evals.eval_runs` / `evals.eval_results`, written by `app_service`. Persona logins cannot read them: they hold answers from every persona.
- **Code lives in `services/api/app/evals/`** (typed, mypy-strict, reusable by the Phase 5 evals page); cases and reports stay in `evals/`.

## Consequences

- The first run (28/31) found two real defects, fixed in the same change: the guard classified "run this SQL" as out of scope, so the database's column-grant denial never showed; and idle pooled connections that Neon had closed made tools hang for up to two minutes (pools now check connections before use and drop idle ones after 60 s). Two robustness cases were wrong about what good behaviour is and were corrected, with the reason in each case's `note`.
- A change that makes answers worse fails CI even if it is "just a prompt tweak", which is the point; it also means prompt PRs cost ~US$0.45 each.
- Leakage checks match values, so a value that coincidentally equals an allowed one could false-fail; reference queries are chosen to return distinctive values.
