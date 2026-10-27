"""Access control is enforced by the database (CLAUDE.md rule 2, ADR 0008).

Each test logs in as a persona and tries to reach data that persona must not see, including
through the tricks a model-written query could use: set_config, SET ROLE, SET SESSION
AUTHORIZATION, flipping the transaction to read-write, and reading raw schemas.
"""

from collections.abc import Callable

import psycopg
import pytest

from set_passwords import PERSONA_LOGINS

Connect = Callable[[str], psycopg.Connection]
LOGINS = tuple(PERSONA_LOGINS)

SALES_REP = "agent_sales_rep_nz_south"
MANAGER = "agent_sales_manager"
FINANCE = "agent_finance"
SUPPORT = "agent_support"
REGIONAL_TABLES = ("dim_customer", "fct_sales", "fct_invoices", "fct_tickets")
ALL_REGIONS = {"NZ-NORTH", "NZ-SOUTH", "AU-EAST", "AU-WEST"}

# The full column matrix. `None` = every column; a set = exactly those columns hidden;
# absent = no access to the table at all. Mirrors data/sql/security.sql.
ALL = None
EXPECTED_ACCESS: dict[str, dict[str, set[str] | None]] = {
    SALES_REP: {
        "dim_date": ALL,
        "dim_product": ALL,
        "dim_sales_rep": ALL,
        "dim_customer": {"credit_limit"},
        "fct_sales": {"cost_nzd", "margin_nzd"},
        "fct_tickets": ALL,
    },
    MANAGER: {
        "dim_date": ALL,
        "dim_product": ALL,
        "dim_sales_rep": ALL,
        "dim_customer": {"credit_limit"},
        "fct_sales": {"cost_nzd", "margin_nzd"},
        "fct_tickets": ALL,
    },
    FINANCE: {
        "dim_date": ALL,
        "dim_product": ALL,
        "dim_sales_rep": ALL,
        "dim_customer": {"contact_name", "contact_email", "contact_phone"},
        "fct_sales": ALL,
        "fct_invoices": ALL,
        "fct_tickets": {"description"},
    },
    SUPPORT: {
        "dim_date": ALL,
        "dim_product": ALL,
        "dim_customer": {
            "segment",
            "currency",
            "credit_limit",
            "contact_name",
            "contact_email",
            "contact_phone",
            "crm_account_id",
            "industry",
            "account_owner_rep_key",
            "created_on",
        },
        "fct_tickets": ALL,
    },
}


def _value(conn: psycopg.Connection, query: str) -> object:
    row = conn.execute(query).fetchone()  # type: ignore[arg-type]
    assert row is not None
    return row[0]


# --- The policy is in place ------------------------------------------------------------------


def test_regional_tables_have_rls_and_the_scope_policy(owner_url: str, marts_built: None) -> None:
    with psycopg.connect(owner_url) as conn:
        rows = conn.execute(
            "select c.relname, c.relrowsecurity, count(p.polname) "
            "from pg_class as c join pg_namespace as n on n.oid = c.relnamespace "
            "left join pg_policy as p on p.polrelid = c.oid "
            "where n.nspname = 'marts' and c.relname = any(%s) group by 1, 2",
            (list(REGIONAL_TABLES),),
        ).fetchall()
    assert {name: (rls, policies) for name, rls, policies in rows} == {
        table: (True, 1) for table in REGIONAL_TABLES
    }


@pytest.mark.parametrize("login", LOGINS)
def test_column_privileges_match_the_matrix(owner_url: str, marts_built: None, login: str) -> None:
    """Every column of every mart, checked against EXPECTED_ACCESS. Catches drift both ways."""
    with psycopg.connect(owner_url) as conn:
        rows = conn.execute(
            "select table_name, column_name, "
            "has_column_privilege(%s, format('marts.%%I', table_name), column_name, 'select') "
            "from information_schema.columns where table_schema = 'marts'",
            (login,),
        ).fetchall()
    readable: dict[str, set[str]] = {}
    columns: dict[str, set[str]] = {}
    for table, column, allowed in rows:
        columns.setdefault(table, set()).add(column)
        if allowed:
            readable.setdefault(table, set()).add(column)

    expected = {
        table: columns[table] - (hidden or set())
        for table, hidden in EXPECTED_ACCESS[login].items()
    }
    assert readable == expected


# --- Identity cannot be changed --------------------------------------------------------------


@pytest.mark.parametrize("login", LOGINS)
def test_session_user_is_the_persona(connect_as: Connect, login: str) -> None:
    conn = connect_as(login)
    assert conn.execute("select session_user, current_user").fetchone() == (login, login)


@pytest.mark.parametrize(
    "statement",
    [
        "set role r_finance",
        "set role agent_finance",
        "select set_config('role', 'r_finance', false)",
        "set session authorization agent_finance",
        "set role r_sales_rep",  # not even its own persona role: membership is inherit-only
    ],
)
def test_sales_rep_cannot_change_identity(connect_as: Connect, statement: str) -> None:
    conn = connect_as(SALES_REP)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)  # type: ignore[arg-type]
    assert _value(conn, "select current_user") == SALES_REP


# --- Rows: region scope ----------------------------------------------------------------------


@pytest.mark.parametrize("table", ["dim_customer", "fct_sales", "fct_tickets"])
def test_sales_rep_sees_only_own_region(connect_as: Connect, table: str) -> None:
    conn = connect_as(SALES_REP)
    regions = {r[0] for r in conn.execute(f"select distinct region from marts.{table}")}  # type: ignore[arg-type]
    assert regions == {"NZ-SOUTH"}


@pytest.mark.parametrize("login", [MANAGER, FINANCE])
def test_all_region_personas_see_every_region(connect_as: Connect, login: str) -> None:
    conn = connect_as(login)
    regions = {r[0] for r in conn.execute("select distinct region from marts.fct_sales")}
    assert regions == ALL_REGIONS


@pytest.mark.parametrize(
    "spoof",
    [
        "select set_config('app.region', 'AU-EAST', false)",
        "set app.region = 'AU-EAST'",
        "select set_config('ops.region', 'AU-EAST', false)",
    ],
)
def test_region_cannot_be_spoofed_with_settings(connect_as: Connect, spoof: str) -> None:
    """The ADR 0008 hole: a single SELECT used to be able to move the RLS scope."""
    conn = connect_as(SALES_REP)
    conn.execute(spoof)  # type: ignore[arg-type]
    assert _value(conn, "select count(*) from marts.fct_sales where region = 'AU-EAST'") == 0
    assert (
        _value(
            conn,
            "select count(*) from ("
            "select set_config('app.region', 'AU-EAST', true), customer_key "
            "from marts.dim_customer where region = 'AU-EAST') as t",
        )
        == 0
    )


def test_sales_rep_cannot_rewrite_its_scope(connect_as: Connect) -> None:
    conn = connect_as(SALES_REP)
    conn.execute("set default_transaction_read_only = off")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("update ops.persona_scope set region = null")


# --- Columns and tables ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("login", "query"),
    [
        (SALES_REP, "select margin_nzd from marts.fct_sales"),
        (SALES_REP, "select * from marts.fct_sales"),
        (MANAGER, "select sum(cost_nzd) from marts.fct_sales"),
        (SALES_REP, "select credit_limit from marts.dim_customer"),
        (MANAGER, "select * from marts.fct_invoices"),
        (FINANCE, "select description from marts.fct_tickets"),
        (FINANCE, "select contact_email from marts.dim_customer"),
        (SUPPORT, "select * from marts.fct_sales"),
        (SUPPORT, "select * from marts.fct_invoices"),
        (SUPPORT, "select credit_limit from marts.dim_customer"),
    ],
)
def test_hidden_columns_and_tables_are_refused(connect_as: Connect, login: str, query: str) -> None:
    conn = connect_as(login)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(query)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "schema_table",
    ["raw.erp_customers", "staging.stg_erp__customers", "intermediate.int_sales_lines_nzd"],
)
@pytest.mark.parametrize("login", LOGINS)
def test_upstream_schemas_are_unreachable(
    connect_as: Connect, login: str, schema_table: str
) -> None:
    conn = connect_as(login)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(f"select * from {schema_table} limit 1")  # type: ignore[arg-type]


# --- Writes ----------------------------------------------------------------------------------


@pytest.mark.parametrize("login", LOGINS)
def test_logins_are_read_only_by_default(connect_as: Connect, login: str) -> None:
    conn = connect_as(login)
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute("create temp table scratch (a int)")


@pytest.mark.parametrize("login", LOGINS)
def test_writes_fail_even_after_switching_to_read_write(connect_as: Connect, login: str) -> None:
    """default_transaction_read_only is a soft default; missing privileges are the hard stop."""
    conn = connect_as(login)
    conn.execute("set default_transaction_read_only = off")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("delete from marts.dim_product")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("create table marts.backdoor (a int)")
