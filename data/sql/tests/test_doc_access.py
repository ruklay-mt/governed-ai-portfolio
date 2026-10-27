"""Document chunks are filtered by RLS on allowed_roles and region (spec §6, migration 0004)."""

from collections.abc import Callable

import psycopg
import pytest

from app.retrieval.ingest import load_documents

# login -> (persona role, region scope); mirrors data/sql/migrations/0003_roles.sql
SCOPES = {
    "agent_sales_rep_nz_south": ("r_sales_rep", "NZ-SOUTH"),
    "agent_sales_manager": ("r_sales_manager", None),
    "agent_finance": ("r_finance", None),
    "agent_support": ("r_support", None),
}


def expected_docs(login: str) -> set[str]:
    role, region = SCOPES[login]
    return {
        doc.doc_id
        for doc in load_documents()
        if role in doc.allowed_roles
        and (doc.region is None or region is None or doc.region == region)
    }


@pytest.fixture
def docs_loaded(owner_url: str) -> None:
    with psycopg.connect(owner_url) as conn:
        row = conn.execute("select to_regclass('retrieval.doc_chunks') is not null").fetchone()
        loaded = bool(row and row[0]) and conn.execute(
            "select exists (select from retrieval.doc_chunks)"
        ).fetchone() == (True,)
    if not loaded:
        pytest.skip("documents not embedded (run make docs-embed)")


@pytest.mark.parametrize("login", sorted(SCOPES))
def test_each_persona_sees_exactly_its_documents(
    connect_as: Callable[[str], psycopg.Connection], docs_loaded: None, login: str
) -> None:
    conn = connect_as(login)
    visible = {row[0] for row in conn.execute("select distinct doc_id from retrieval.doc_chunks")}
    assert visible == expected_docs(login)


def test_finance_only_documents_are_hidden_from_sales_and_support(
    connect_as: Callable[[str], psycopg.Connection], docs_loaded: None
) -> None:
    for login in ("agent_sales_rep_nz_south", "agent_sales_manager", "agent_support"):
        rows = connect_as(login).execute(
            "select count(*) from retrieval.doc_chunks where doc_id = 'credit-terms'"
        )
        assert rows.fetchone() == (0,)


def test_sales_rep_sees_only_own_regional_guide(
    connect_as: Callable[[str], psycopg.Connection], docs_loaded: None
) -> None:
    rows = connect_as("agent_sales_rep_nz_south").execute(
        "select distinct region from retrieval.doc_chunks where region is not null"
    )
    assert {row[0] for row in rows} == {"NZ-SOUTH"}


@pytest.mark.parametrize("login", sorted(SCOPES))
def test_personas_cannot_read_document_metadata_or_ops_tables(
    connect_as: Callable[[str], psycopg.Connection], docs_loaded: None, login: str
) -> None:
    conn = connect_as(login)
    for table in ("retrieval.documents", "ops.rate_limits", "ops.daily_spend"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(f"select 1 from {table} limit 1")


@pytest.mark.parametrize("login", sorted(SCOPES))
def test_personas_cannot_write_chunks(
    connect_as: Callable[[str], psycopg.Connection], docs_loaded: None, login: str
) -> None:
    conn = connect_as(login)
    denied = (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)
    with pytest.raises(denied):
        conn.execute("delete from retrieval.doc_chunks")
