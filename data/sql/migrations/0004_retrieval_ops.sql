-- Document retrieval tables and the ops tables behind the cost guards (spec §5.2, §16).
--
-- Documents: `make docs-embed` (running as the owner) loads data/documents/*.md into
-- retrieval.documents and retrieval.doc_chunks. Persona roles read chunks only, filtered by RLS:
-- a chunk is visible when session_user belongs to one of its allowed_roles and the chunk's region
-- matches the persona's region. dbt never rebuilds these tables, so the policy lives here.
--
-- Ops: only app_service writes rate limits and daily spend; persona logins cannot touch them.

-- Documents -------------------------------------------------------------------------------

create table if not exists retrieval.documents (
    doc_id text primary key,
    title text not null,
    source_path text not null,
    allowed_roles text[] not null,
    region text,
    content_hash text not null,
    updated_at timestamptz not null default now()
);

-- The vector dimension is fixed by the embedding model (ADR 0010). Changing model means a new
-- migration and a re-embed.
create table if not exists retrieval.doc_chunks (
    chunk_id text primary key,
    doc_id text not null references retrieval.documents (doc_id) on delete cascade,
    chunk_index integer not null,
    doc_title text not null,
    section text not null,  -- noqa: RF04
    content text not null,  -- noqa: RF04
    content_hash text not null,
    embedding vector(1024) not null,
    search_tsv tsvector generated always as (
        to_tsvector('english', doc_title || ' ' || section || ' ' || content)
    ) stored,
    allowed_roles text[] not null,
    region text,
    unique (doc_id, chunk_index)
);

create index if not exists doc_chunks_embedding_idx
on retrieval.doc_chunks using hnsw (embedding vector_cosine_ops);

create index if not exists doc_chunks_search_tsv_idx
on retrieval.doc_chunks using gin (search_tsv);

alter table retrieval.doc_chunks enable row level security;
drop policy if exists persona_doc_scope on retrieval.doc_chunks;
create policy persona_doc_scope on retrieval.doc_chunks
for select
to r_sales_rep, r_sales_manager, r_finance, r_support
using (
    exists (
        select 1
        from unnest(doc_chunks.allowed_roles) as allowed (role_name)
        where pg_has_role(session_user, allowed.role_name, 'member')
    )
    and exists (
        select 1
        from ops.persona_scope as ps
        where
            ps.db_user = session_user
            and (ps.region is null or doc_chunks.region is null or ps.region = doc_chunks.region)
    )
);

grant usage on schema retrieval to r_sales_rep, r_sales_manager, r_finance, r_support;
grant select on retrieval.doc_chunks to r_sales_rep, r_sales_manager, r_finance, r_support;

-- Cost guards -----------------------------------------------------------------------------

-- One row per (scope, key, day). IP keys are stored as a SHA-256 hash, never the raw address.
create table if not exists ops.rate_limits (
    scope text not null check (scope in ('session', 'ip')),
    limit_key text not null,
    window_date date not null,
    question_count integer not null default 0,
    primary key (scope, limit_key, window_date)
);

create table if not exists ops.daily_spend (
    spend_date date primary key,
    spend_usd numeric(12, 6) not null default 0,
    live_questions integer not null default 0,
    updated_at timestamptz not null default now()
);

alter role app_service set statement_timeout = '5s';
grant usage on schema ops to app_service;
grant select, insert, update on ops.rate_limits, ops.daily_spend to app_service;
