"""Hybrid document search: pgvector similarity + Postgres full-text, merged with RRF (spec §8.2).

The query runs on the caller's persona connection, so the RLS policy on retrieval.doc_chunks
filters every branch: a chunk the persona may not read never reaches the ranking.
"""

from collections.abc import Sequence

import psycopg
from pydantic import BaseModel

from app.retrieval.embeddings import to_pgvector

# Candidates taken from each branch before fusion, and the RRF constant (Cormack et al., 2009).
CANDIDATES = 20
RRF_K = 60
MAX_K = 8

# Persona logins have search_path = marts, so pgvector's type and operator (installed in public)
# are schema-qualified here rather than widening the search path.
HYBRID_SEARCH_SQL = f"""
with vector_candidates as (
    select chunk_id, embedding operator(public.<=>) %(embedding)s::public.vector as distance
    from retrieval.doc_chunks
    order by distance
    limit {CANDIDATES}
),

vector_hits as (
    select chunk_id, row_number() over (order by distance) as rank
    from vector_candidates
),

text_query as (
    select websearch_to_tsquery('english', %(query)s) as q
),

text_hits as (
    select
        c.chunk_id,
        row_number() over (order by ts_rank_cd(c.search_tsv, t.q) desc) as rank
    from retrieval.doc_chunks as c
    cross join text_query as t
    where c.search_tsv @@ t.q
    order by ts_rank_cd(c.search_tsv, t.q) desc
    limit {CANDIDATES}
),

fused as (
    select chunk_id, sum(1.0 / ({RRF_K} + rank)) as score
    from (
        select chunk_id, rank from vector_hits
        union all
        select chunk_id, rank from text_hits
    ) as hits
    group by chunk_id
)

select c.chunk_id, c.doc_id, c.doc_title, c.section, c.content, round(f.score, 5) as score
from fused as f
inner join retrieval.doc_chunks as c on f.chunk_id = c.chunk_id
order by f.score desc, c.chunk_id
limit %(k)s
"""


class DocChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    content: str
    score: float

    @property
    def source(self) -> str:
        return f"data/documents/{self.doc_id}.md"


def hybrid_search(
    conn: psycopg.Connection, query: str, embedding: Sequence[float], k: int = 5
) -> list[DocChunk]:
    k = max(1, min(k, MAX_K))
    rows = conn.execute(
        HYBRID_SEARCH_SQL, {"embedding": to_pgvector(embedding), "query": query, "k": k}
    ).fetchall()
    fields = DocChunk.model_fields
    return [DocChunk(**dict(zip(fields, row, strict=True))) for row in rows]
