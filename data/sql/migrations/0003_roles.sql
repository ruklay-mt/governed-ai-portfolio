-- Persona roles, per-persona logins and scope mapping (ADR 0008).
--
-- Persona roles (NOLOGIN) hold privileges. Each agent login is a member of exactly one persona
-- role, inherits its privileges, and cannot SET ROLE to it or to anything else. Logins are
-- created without a password; `make db-users` sets them. RLS policies (data/sql/security.sql)
-- read the region from ops.persona_scope keyed by session_user, which SQL cannot change.

do $$
declare
    persona_role text;
begin
    foreach persona_role in array array['r_sales_rep', 'r_sales_manager', 'r_finance', 'r_support']
    loop
        if not exists (select from pg_roles where rolname = persona_role) then
            execute format('create role %I nologin', persona_role);
        end if;
    end loop;
end
$$;

do $$
declare
    login_and_role text[];
begin
    foreach login_and_role slice 1 in array array[
        ['agent_sales_rep_nz_south', 'r_sales_rep'],
        ['agent_sales_manager', 'r_sales_manager'],
        ['agent_finance', 'r_finance'],
        ['agent_support', 'r_support']
    ]
    loop
        if not exists (select from pg_roles where rolname = login_and_role[1]) then
            execute format(
                'create role %I login nosuperuser nocreatedb nocreaterole nobypassrls inherit',
                login_and_role[1]
            );
        end if;
        execute format(
            'grant %I to %I with inherit true, set false', login_and_role[2], login_and_role[1]
        );
        -- Soft defaults: SQL could change these, which is why the SQL guard blocks SET.
        -- The hard boundary is privileges and RLS.
        execute format('alter role %I set default_transaction_read_only = on', login_and_role[1]);
        execute format('alter role %I set statement_timeout = %L', login_and_role[1], '8s');
        execute format('alter role %I set search_path = marts', login_and_role[1]);
        execute format('alter role %I connection limit 10', login_and_role[1]);
    end loop;

    -- Writes to ops.* (rate limits, budget, pending actions) in Phase 2. No persona role.
    if not exists (select from pg_roles where rolname = 'app_service') then
        create role app_service login nosuperuser nocreatedb nocreaterole nobypassrls;
    end if;
end
$$;

-- Nothing is readable by default outside what security.sql grants.
revoke all on schema raw, staging, intermediate, marts, retrieval, ops, evals, docflow from public;

create table if not exists ops.persona_scope (
    db_user name primary key,
    persona text not null,
    region text  -- null = all regions
);

insert into ops.persona_scope (db_user, persona, region) values
('agent_sales_rep_nz_south', 'Mia Tane, sales rep', 'NZ-SOUTH'),
('agent_sales_manager', 'Liam Chen, sales manager', null),
('agent_finance', 'Raj Patel, finance', null),
('agent_support', 'Sophie Williams, support', null)
on conflict (db_user) do update
    set persona = excluded.persona, region = excluded.region;

create table if not exists ops.pipeline_runs (
    run_id bigint generated always as identity primary key,
    target_branch text not null,
    as_of date not null,
    status text not null,
    dbt_passed integer,
    dbt_failed integer,
    run_url text,
    finished_at timestamptz not null default now()
);

grant usage on schema marts, ops to r_sales_rep, r_sales_manager, r_finance, r_support;
-- RLS policies look up the caller's scope, so every persona can read the mapping (it holds
-- only login names and regions).
grant select on ops.persona_scope to r_sales_rep, r_sales_manager, r_finance, r_support;
