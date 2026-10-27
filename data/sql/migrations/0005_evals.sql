-- Eval results (spec §12, ADR 0012): one row per `make eval` run and one per case in it.
--
-- The runner writes as app_service (insert + select only). Persona logins have no access:
-- eval answers include rows from every persona, so they must not be readable by any one of them.

create table if not exists evals.eval_runs (
    run_id uuid primary key,
    started_at timestamptz not null,
    finished_at timestamptz,
    git_sha text,
    run_trigger text not null,  -- local | ci | manual
    model_main text not null,
    model_small text not null,
    total_cases integer not null,
    passed_cases integer not null,
    pass_rate numeric(5, 4) not null,
    by_category jsonb not null,
    cost_usd numeric(12, 6) not null,
    gate_passed boolean not null,
    gate_reasons jsonb not null default '[]'
);

create table if not exists evals.eval_results (
    run_id uuid not null references evals.eval_runs (run_id) on delete cascade,
    case_id text not null,
    attempt integer not null default 1,
    category text not null,
    persona text not null,
    question text not null,
    passed boolean not null,
    checks jsonb not null,
    answer jsonb,
    latency_ms integer,
    cost_usd numeric(12, 6),
    trace_id text,
    primary key (run_id, case_id, attempt)
);

grant usage on schema evals to app_service;
grant select, insert, update on evals.eval_runs to app_service;
grant select, insert on evals.eval_results to app_service;
