"""Check SQL written by the LLM before it runs (spec §8.3, CLAUDE.md rule 4).

Generated SQL is untrusted. The guard allows exactly one read-only query over the marts:

- one statement, and it is a SELECT (or UNION/INTERSECT/EXCEPT of SELECTs);
- no data-modifying or DDL nodes anywhere, including inside CTEs (`with d as (delete ...)`);
- no `SELECT ... INTO` and no locking clauses (`FOR UPDATE`);
- only allow-listed functions: aggregates, window, date/time, maths and basic string functions.
  `set_config`, `current_setting`, `pg_*` and anything unlisted are rejected;
- only known mart tables (or CTE names), so no `pg_catalog`, `information_schema` or `ops`;
- a LIMIT of at most 1,000 rows, added when missing.

This is defence in depth. The database stays the boundary (ADR 0008): the query runs as a
read-only persona login whose grants and RLS policies decide what it can see.
"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

MAX_ROWS = 1000

# Tables in the marts schema (data/dbt/models/marts). A new mart must be added here before
# run_sql can read it.
MART_TABLES = frozenset(
    {
        "dim_customer",
        "dim_date",
        "dim_product",
        "dim_sales_rep",
        "fct_invoices",
        "fct_sales",
        "fct_tickets",
    }
)

# sqlglot parses known functions into typed nodes; these are their sqlglot names. Postgres
# spellings differ for a few: date_trunc -> TIMESTAMP_TRUNC, to_char -> TIME_TO_STR,
# string_agg -> GROUP_CONCAT, date_part -> EXTRACT, strpos/position -> STR_POSITION.
ALLOWED_FUNCTIONS = frozenset(
    {
        # aggregates
        "AVG", "COUNT", "MAX", "MIN", "SUM", "MEDIAN", "STDDEV", "STDDEV_POP", "STDDEV_SAMP",
        "VARIANCE", "VARIANCE_POP", "PERCENTILE_CONT", "PERCENTILE_DISC", "GROUP_CONCAT",
        "ARRAY_AGG", "LOGICAL_AND", "LOGICAL_OR",
        # window
        "ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
        # conditional, casts and predicates
        "EXISTS", "ARRAY", "CASE", "IF", "COALESCE", "NULLIF", "GREATEST", "LEAST", "CAST",
        "TRY_CAST",
        # date and time
        "CURRENT_DATE", "CURRENT_TIMESTAMP", "EXTRACT", "TIMESTAMP_TRUNC", "DATE_TRUNC",
        "TIME_TO_STR", "DATE_ADD", "DATE_SUB", "DATE_DIFF",
        # maths
        "ABS", "CEIL", "FLOOR", "ROUND", "SIGN", "SQRT", "POWER", "EXP", "LN", "LOG",
        # strings
        "LOWER", "UPPER", "INITCAP", "LENGTH", "SUBSTRING", "TRIM", "LEFT", "RIGHT", "REPLACE",
        "CONCAT", "CONCAT_WS", "SPLIT_PART", "STR_POSITION",
    }
)  # fmt: skip
# Functions sqlglot does not know parse as Anonymous; allowed by their Postgres name.
ALLOWED_ANONYMOUS = frozenset({"age", "make_date", "date_part", "to_char", "strpos"})

FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Set,
    exp.Into,
    exp.Lock,
)


class SqlRejected(ValueError):
    """The SQL breaks a guard rule. The message is safe to show the model and the user."""


@dataclass(frozen=True)
class GuardedSql:
    sql: str  # normalised Postgres SQL with the row limit applied
    tables: tuple[str, ...]


def _function_name(node: exp.Func) -> str:
    return node.name.lower() if isinstance(node, exp.Anonymous) else node.sql_name()


def _is_allowed(node: exp.Func) -> bool:
    # sqlglot models the logical operators AND / OR as function nodes; they are not functions.
    if isinstance(node, exp.Connector):
        return True
    if isinstance(node, exp.Anonymous):
        return node.name.lower() in ALLOWED_ANONYMOUS
    return node.sql_name() in ALLOWED_FUNCTIONS


def guard_sql(sql: str) -> GuardedSql:
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as error:
        raise SqlRejected(f"could not parse SQL: {error}") from None
    if len(statements) != 1:
        raise SqlRejected("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Select | exp.SetOperation):
        raise SqlRejected("only SELECT queries are allowed")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlRejected(f"{node.key.upper()} is not allowed; only read-only SELECT")

    if bad := sorted({_function_name(f) for f in tree.find_all(exp.Func) if not _is_allowed(f)}):
        raise SqlRejected(f"functions not allowed: {', '.join(bad)}")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        name, schema = table.name.lower(), table.db.lower()
        if table.catalog or (schema and schema != "marts"):
            raise SqlRejected(f"only marts tables are allowed, not {table.sql('postgres')}")
        if not schema and name in cte_names:
            continue
        if name not in MART_TABLES:
            raise SqlRejected(
                f"unknown table {name!r}; marts tables: {', '.join(sorted(MART_TABLES))}"
            )
        tables.add(name)

    limit = tree.args.get("limit")
    limit_value = limit.expression if isinstance(limit, exp.Limit) else None
    if not (
        isinstance(limit_value, exp.Literal)
        and limit_value.is_int
        and int(limit_value.this) <= MAX_ROWS
    ):
        tree.set("limit", exp.Limit(expression=exp.Literal.number(MAX_ROWS)))

    return GuardedSql(sql=tree.sql(dialect="postgres"), tables=tuple(sorted(tables)))
