"""Tool-level access tests: every agent tool, run as each persona against a real database.

These prove the phase criterion "run_sql cannot read a hidden column" at the tool boundary the
model actually calls, not only in direct SQL (data/sql/tests covers that). Skipped without a
database, persona passwords or built marts.
"""

from collections.abc import Iterator
from datetime import date

import psycopg
import pytest

from app.agent.db import PersonaPools
from app.agent.personas import PERSONAS, get_persona
from app.agent.tools import ToolContext, ToolResult, call_tool
from app.config import Settings, get_settings
from app.retrieval.embeddings import EMBEDDING_DIM


def _fake_embedding(_: str) -> list[float]:
    # A constant vector: the vector branch ranks arbitrarily, the full-text branch still works,
    # and RLS filtering is what these tests check. No Voyage call, no rate limits.
    return [1.0] * EMBEDDING_DIM


@pytest.fixture(scope="module")
def settings() -> Settings:
    settings = get_settings()
    if settings.database_url is None:
        pytest.skip("needs DATABASE_URL")
    if any(persona.password(settings) is None for persona in PERSONAS.values()):
        pytest.skip("needs persona passwords")
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("select to_regclass('marts.fct_sales') is not null").fetchone()
    if not row or not row[0]:
        pytest.skip("marts not built (run make data-generate dbt-build)")
    return settings


@pytest.fixture(scope="module")
def pools(settings: Settings) -> Iterator[PersonaPools]:
    pools = PersonaPools(settings)
    yield pools
    pools.close()


def call(pools: PersonaPools, persona_id: str, tool: str, **arguments: object) -> ToolResult:
    ctx = ToolContext(
        persona=get_persona(persona_id),
        pools=pools,
        embed_query=_fake_embedding,
        today=date(2026, 10, 27),
    )
    return call_tool(ctx, tool, arguments)


def test_persona_registry_matches_database(settings: Settings) -> None:
    assert settings.database_url is not None
    with psycopg.connect(settings.database_url) as conn:
        scope = dict(conn.execute("select db_user, region from ops.persona_scope").fetchall())
        for persona in PERSONAS.values():
            assert scope[persona.login] == persona.region
            member = conn.execute(
                "select pg_has_role(%s, %s, 'member')", (persona.login, persona.role)
            ).fetchone()
            assert member == (True,)


# run_sql ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "select margin_nzd from fct_sales limit 1",
        "select sum(cost_nzd) from fct_sales",
        "select * from fct_sales limit 1",
    ],
)
def test_run_sql_cannot_read_hidden_column_as_sales_rep(pools: PersonaPools, sql: str) -> None:
    result = call(pools, "sales_rep_nz_south", "run_sql", sql=sql)
    assert result.status == "denied"
    assert result.denied_by == "database privileges (column or table grant)"
    assert result.rows == []


def test_run_sql_reads_margin_as_finance(pools: PersonaPools) -> None:
    result = call(pools, "finance", "run_sql", sql="select sum(margin_nzd) from fct_sales")
    assert result.status == "ok"
    assert result.rows[0][0] is not None


def test_run_sql_support_cannot_read_sales(pools: PersonaPools) -> None:
    result = call(pools, "support", "run_sql", sql="select count(*) from fct_sales")
    assert result.status == "denied"


def test_run_sql_sales_rep_sees_only_own_region(pools: PersonaPools) -> None:
    result = call(
        pools,
        "sales_rep_nz_south",
        "run_sql",
        sql="select distinct region from fct_sales union select distinct region from fct_tickets",
    )
    assert result.status == "ok"
    assert {row[0] for row in result.rows} == {"NZ-SOUTH"}


def test_run_sql_region_filter_cannot_widen_scope(pools: PersonaPools) -> None:
    result = call(
        pools,
        "sales_rep_nz_south",
        "run_sql",
        sql="select count(*) from fct_sales where region = 'AU-EAST'",
    )
    assert result.status == "ok"
    assert result.rows == [[0]]


@pytest.mark.parametrize(
    "sql",
    [
        "select set_config('app.region', 'AU-EAST', false)",
        "select * from ops.persona_scope",
        "delete from fct_sales",
    ],
)
def test_run_sql_guard_rejects_before_the_database(pools: PersonaPools, sql: str) -> None:
    result = call(pools, "sales_rep_nz_south", "run_sql", sql=sql)
    assert result.status == "rejected"
    assert result.denied_by == "SQL guard"


def test_run_sql_guard_output_still_runs_on_postgres(pools: PersonaPools) -> None:
    # sqlglot re-renders the query; Postgres-specific functions must survive the round trip.
    sql = (
        "select to_char(order_date, 'YYYY-MM') as month, date_trunc('month', order_date) as m,"
        " string_agg(distinct region, ',') as regions, extract(year from order_date) as y,"
        " count(*) filter (where line_type = 'return') as returns"
        " from fct_sales group by 1, 2, 4 order by 1 desc limit 3"
    )
    result = call(pools, "finance", "run_sql", sql=sql)
    assert result.status == "ok", result.message
    assert result.row_count == 3


def test_run_sql_reports_errors_the_model_can_fix(pools: PersonaPools) -> None:
    result = call(pools, "finance", "run_sql", sql="select no_such_column from fct_sales")
    assert result.status == "error"
    assert result.message and "no_such_column" in result.message


# describe_tables -------------------------------------------------------------------------


def _columns(result: ToolResult, table: str) -> set[str]:
    return {row[1] for row in result.rows if row[0] == table}


def test_describe_tables_hides_columns_the_role_cannot_read(pools: PersonaPools) -> None:
    sales = call(pools, "sales_rep_nz_south", "describe_tables", tables=["fct_sales"])
    finance = call(pools, "finance", "describe_tables", tables=["fct_sales"])
    assert {"cost_nzd", "margin_nzd"} & _columns(sales, "fct_sales") == set()
    assert {"cost_nzd", "margin_nzd"} <= _columns(finance, "fct_sales")


def test_describe_tables_support_sees_no_sales_or_invoices(pools: PersonaPools) -> None:
    result = call(pools, "support", "describe_tables")
    tables = {row[0] for row in result.rows}
    assert "fct_tickets" in tables
    assert {"fct_sales", "fct_invoices"} & tables == set()


# get_metric ------------------------------------------------------------------------------


def test_get_metric_refuses_margin_for_sales_rep(pools: PersonaPools) -> None:
    result = call(pools, "sales_rep_nz_south", "get_metric", metric="gross_margin")
    assert result.status == "denied"
    assert result.denied_by == "semantic layer role check"


def test_get_metric_scopes_rows_to_region(pools: PersonaPools) -> None:
    result = call(
        pools, "sales_rep_nz_south", "get_metric", metric="revenue", dimensions=["region"]
    )
    assert result.status == "ok"
    assert [row[0] for row in result.rows] == ["NZ-SOUTH"]
    assert result.sql and result.assumptions


def test_get_metric_bad_input_is_an_error(pools: PersonaPools) -> None:
    result = call(pools, "finance", "get_metric", metric="revenue", limit=99999)
    assert result.status == "error"


# search_documents ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def docs_loaded(settings: Settings) -> None:
    assert settings.database_url is not None
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("select to_regclass('retrieval.doc_chunks') is not null").fetchone()
        has_rows = bool(row and row[0]) and conn.execute(
            "select exists (select from retrieval.doc_chunks)"
        ).fetchone() == (True,)
    if not has_rows:
        pytest.skip("documents not embedded (run make docs-embed)")


def _docs(result: ToolResult) -> set[str]:
    return {chunk.doc_id for chunk in result.chunks}


def test_search_finds_credit_terms_for_finance(pools: PersonaPools, docs_loaded: None) -> None:
    result = call(pools, "finance", "search_documents", query="credit terms overdue", k=8)
    assert result.status == "ok"
    assert "credit-terms" in _docs(result)


@pytest.mark.parametrize("persona_id", ["sales_rep_nz_south", "sales_manager", "support"])
def test_search_never_returns_finance_documents(
    pools: PersonaPools, docs_loaded: None, persona_id: str
) -> None:
    result = call(pools, persona_id, "search_documents", query="credit terms overdue", k=8)
    assert result.status == "ok"
    assert {"credit-terms", "collections-procedure"} & _docs(result) == set()


def test_search_sales_rep_gets_only_own_regional_guide(
    pools: PersonaPools, docs_loaded: None
) -> None:
    result = call(
        pools, "sales_rep_nz_south", "search_documents", query="regional sales guide", k=8
    )
    guides = {doc for doc in _docs(result) if doc.startswith("sales-guide-")}
    assert guides <= {"sales-guide-nz-south"}


def test_search_support_cannot_see_pricing(pools: PersonaPools, docs_loaded: None) -> None:
    result = call(pools, "support", "search_documents", query="discount cap 15%", k=8)
    assert "pricing-policy" not in _docs(result)
