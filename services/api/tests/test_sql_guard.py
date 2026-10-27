import pytest

from app.agent.sql_guard import MAX_ROWS, SqlRejected, guard_sql


@pytest.mark.parametrize(
    "sql",
    [
        "select region, sum(net_amount_nzd) from fct_sales group by 1",
        "select * from marts.dim_customer where region = 'NZ-SOUTH'",
        "with q as (select date_trunc('month', order_date) as m, count(*) as n from fct_sales"
        " group by 1) select * from q order by m",
        "select to_char(order_date, 'YYYY-MM'), round(avg(discount_pct), 2) from fct_sales"
        " group by 1",
        "select customer_key, rank() over (order by sum(outstanding_nzd) desc)"
        " from fct_invoices group by 1",
        "select priority from fct_tickets union select priority from fct_tickets",
        "select coalesce(nullif(region, ''), 'unknown'), extract(year from opened_date)"
        " from fct_tickets",
        "select count(*) filter (where is_sla_breached) from fct_tickets",
        # Logical operators and predicates (sqlglot parses AND/OR/EXISTS as function nodes).
        "select r.rep_name, count(*) from fct_sales s join dim_sales_rep r"
        " on r.sales_rep_key = s.sales_rep_key where s.discount_pct > 15"
        " and s.order_date >= '2026-04-01' or not s.region = 'NZ-NORTH' group by 1",
        "select * from fct_tickets t where exists (select 1 from fct_sales s"
        " where s.customer_key = t.customer_key) and t.priority = any(array['P1', 'P2'])"
        " and t.opened_date between '2026-01-01' and '2026-01-31' and t.subject ilike '%zip%'",
    ],
)
def test_allows_read_only_queries(sql: str) -> None:
    guarded = guard_sql(sql)
    assert guarded.sql.upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("select 1; select 2", "exactly one statement"),
        ("delete from fct_sales", "only SELECT"),
        ("update fct_sales set discount_pct = 0", "only SELECT"),
        ("insert into fct_sales select * from fct_sales", "only SELECT"),
        ("drop table fct_sales", "only SELECT"),
        ("set role r_finance", "only SELECT"),
        ("reset role", "only SELECT"),
        ("copy fct_sales to stdout", "only SELECT"),
        ("explain select * from fct_sales", "only SELECT"),
        ("with d as (delete from fct_sales returning *) select * from d", "DELETE"),
        ("select * into tmp_copy from fct_sales", "INTO"),
        ("select * from fct_sales for update", "LOCK"),
        ("select set_config('app.region', 'AU-EAST', false)", "set_config"),
        ("select current_setting('app.region')", "current_setting"),
        ("select pg_sleep(10)", "pg_sleep"),
        ("select pg_read_file('/etc/passwd')", "pg_read_file"),
        ("select lo_import('/tmp/x')", "lo_import"),
        ("select * from pg_catalog.pg_roles", "only marts"),
        ("select * from pg_roles", "unknown table"),
        ("select * from information_schema.columns", "only marts"),
        ("select * from ops.persona_scope", "only marts"),
        ("select * from raw.erp_invoices", "only marts"),
        ("select * from retrieval.doc_chunks", "only marts"),
        ("select * from fct_salez", "unknown table"),
        ("select from where", "could not parse"),
    ],
)
def test_rejects_unsafe_sql(sql: str, reason: str) -> None:
    with pytest.raises(SqlRejected, match=reason):
        guard_sql(sql)


def test_adds_missing_limit() -> None:
    assert guard_sql("select * from fct_sales").sql.endswith(f"LIMIT {MAX_ROWS}")


def test_caps_large_limit() -> None:
    assert guard_sql("select * from fct_sales limit 50000").sql.endswith(f"LIMIT {MAX_ROWS}")


def test_keeps_small_limit() -> None:
    assert guard_sql("select * from fct_sales limit 5").sql.endswith("LIMIT 5")


def test_replaces_parameter_limit() -> None:
    assert guard_sql("select * from fct_sales limit $1").sql.endswith(f"LIMIT {MAX_ROWS}")


def test_limits_whole_union() -> None:
    sql = guard_sql("select region from fct_sales union select region from fct_tickets").sql
    assert sql.endswith(f"UNION SELECT region FROM fct_tickets LIMIT {MAX_ROWS}")


def test_reports_tables_used() -> None:
    guarded = guard_sql(
        "with x as (select * from fct_sales) select * from x join marts.dim_product using"
        " (product_key)"
    )
    assert guarded.tables == ("dim_product", "fct_sales")
