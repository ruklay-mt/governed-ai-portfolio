# 0008 — One database login per persona; region scope from `session_user`

- Status: Accepted (amends spec §6 and CLAUDE.md rule 2)
- Date: 2026-10-27

## Context

Spec v0.2 had one API user, `app_agent`, that was a member of all four persona roles. Each request ran `SET LOCAL ROLE r_x` and `SET LOCAL app.region = '...'`, and RLS policies read `current_setting('app.region')`.

That design has two holes that a single `SELECT` can open, because `run_sql` accepts model-written SQL:

1. **Region spoofing.** `select set_config('app.region', 'AU-EAST', true), * from marts.fct_sales` is one SELECT statement. It changes the setting the RLS policy trusts, so a NZ-SOUTH sales rep sees AU-EAST rows.
2. **Role escalation.** Because `app_agent` is a member of every persona role, `set_config('role', 'r_finance', true)` acts like `SET ROLE` and lifts a sales rep to finance.

A "single SELECT only" rule does not stop either one. The SQL guard could block `set_config`, but then access control would depend on the guard being perfect. Rule 2 says access control must hold even when everything above the database is fooled.

## Decision

**1. One LOGIN user per persona, each a member of exactly one persona role.**

| Login user | Member of | Region scope |
|---|---|---|
| `agent_sales_rep_nz_south` | `r_sales_rep` | `NZ-SOUTH` |
| `agent_sales_manager` | `r_sales_manager` | all |
| `agent_finance` | `r_finance` | all |
| `agent_support` | `r_support` | all |

- Persona roles stay `NOLOGIN` and hold all the grants. Login users inherit them, so no `SET ROLE` is needed.
- No login user is a member of more than one persona role. There is nothing to escalate to.
- Login users own nothing and have no `BYPASSRLS`. Each has role-level defaults: `default_transaction_read_only = on` and `statement_timeout = '8s'`.
- The API keeps one connection pool per persona. Each persona's password is its own secret.

**2. RLS reads scope from a mapping keyed by `session_user`, never from a setting.**

```sql
create table ops.persona_scope (
    db_user name primary key,
    region text  -- null = all regions
);

create policy sales_rep_own_region on marts.fct_sales
    for select to r_sales_rep
    using (
        region = (select ps.region from ops.persona_scope as ps where ps.db_user = session_user)
    );
```

`session_user` is the login user. It cannot be changed with `set_config` or `SET ROLE`; only a superuser can run `SET SESSION AUTHORIZATION`. Persona roles may read `ops.persona_scope`, which holds only user→region pairs.

**3. The SQL guard uses a function allow-list instead of a deny-list.** Only known-safe functions are allowed: aggregates, date/time, maths, and basic string functions. `set_config`, `current_setting`, `pg_*`, `dblink` and anything not on the list are rejected. This is defence in depth. The database is still the boundary.

**4. `app_service` is a separate login.** It writes only to `ops.*` (rate limits, budget, pending actions) and `evals.*`, owns nothing and is not a member of any persona role. The Neon owner role is used only by migrations.

## Tests (Phase 1 access-control suite)

These must fail for the sales-rep login, through direct SQL and through `run_sql`:

- `set_config('app.region', ...)` and then reading another region
- `set_config('role', 'r_finance', ...)`, `SET ROLE`, `RESET ROLE`
- selecting a hidden column (`cost`, `margin`)
- any write, which `default_transaction_read_only` blocks even without the guard

## Consequences

- Four agent passwords to manage instead of one: four Secret Manager entries, four connection pools.
- Adding a persona means a migration (login user + `persona_scope` row) and a new secret, which suits a demo with fixed personas.
- The interview story: "I found that RLS keyed on a session variable can be spoofed with one SELECT, so I moved the trust anchor to `session_user` and gave each persona its own login."
