# 0009 — Mart access policy is re-applied after every dbt build, and fails closed

- Status: Accepted
- Date: 2026-10-27

## Context

The marts are dbt `table` models. On every build, dbt creates the new table and swaps it in for the old one, so any grants and RLS policies on the old table are lost. Access control has to survive daily rebuilds without anyone remembering to re-run something.

## Options considered

- **dbt `grants` config and post-hooks**: these keep grants next to each model, but spread the security policy across many YAML and Jinja files. RLS policies would also be built by string templating.
- **Stable tables owned by migrations, filled by dbt** (truncate and insert): policies would never be lost, but every column list would live in two places (migration DDL and the dbt model).
- **One idempotent `security.sql`, applied straight after `dbt build`**: the whole policy sits in one reviewable SQL file.

## Decision

- `data/sql/security.sql` holds every mart grant and RLS policy. It starts by revoking all, then grants explicit column lists per persona role and recreates one region-scope policy per regional table.
- `make dbt-build` runs `dbt build`, then `data/sql/apply_security.py` (one transaction), then source freshness. The daily pipeline uses the same target.
- Stable objects (persona roles, logins, `ops.persona_scope`) stay in migrations.

## Why this fails closed

- A table dbt has just rebuilt has no grants, so between the rebuild and `apply_security.py` every persona gets `permission denied`. The data is never exposed during that window.
- If `dbt build` fails, the script does not run, so personas stay locked out until the next successful build. Failing closed is the right trade-off for access control: a locked-out demo is a bug; a data leak is an incident.
- A column dbt adds later stays hidden until `security.sql` lists it. The access-control suite compares every mart column against the expected matrix, so drift fails CI.

## Consequences

- `dbt build` on its own (without the make target) leaves personas locked out. That is safe, but confusing, so CLAUDE.md documents `make dbt-build` as the only way to build.
- Row-level security is not `FORCE`d, so the owner role (migrations, dbt and its tests) still sees every row. Agents never use the owner role.
