"""Load generated rows into the `raw` schema.

Full load: truncate every raw table, then COPY.
Append: COPY into a temp table, then upsert. Unchanged rows are left alone, new rows are
inserted, and rows that changed (a ticket resolved, an invoice paid) are updated with a new
`_loaded_at`. Running the same append twice changes nothing.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import psycopg
from psycopg import sql


@dataclass(frozen=True)
class RawTable:
    name: str
    columns: tuple[str, ...]
    key: tuple[str, ...]


RAW_TABLES = (
    RawTable("ref_fx_rates", ("rate_date", "aud_to_nzd"), ("rate_date",)),
    RawTable(
        "crm_users", ("user_id", "full_name", "email", "region", "title", "is_active"), ("user_id",)
    ),
    RawTable(
        "erp_customers",
        (
            "customer_number",
            "customer_name",
            "region",
            "city",
            "currency",
            "segment",
            "credit_limit",
            "contact_name",
            "contact_email",
            "contact_phone",
            "created_on",
            "deleted_at",
        ),
        ("customer_number",),
    ),
    RawTable(
        "crm_accounts",
        (
            "account_id",
            "account_name",
            "erp_customer_ref",
            "owner_user_id",
            "region",
            "industry",
            "created_on",
        ),
        ("account_id",),
    ),
    RawTable(
        "erp_products",
        ("sku", "product_name", "category", "list_price_nzd", "unit_cost_nzd"),
        ("sku",),
    ),
    RawTable("sd_sla_policies", ("priority", "response_hours", "resolution_hours"), ("priority",)),
    RawTable(
        "erp_sales_orders",
        ("order_number", "order_type", "customer_number", "sales_rep_id", "order_date", "currency"),
        ("order_number",),
    ),
    RawTable(
        "erp_sales_order_lines",
        (
            "order_number",
            "line_number",
            "sku",
            "quantity",
            "unit_price",
            "discount_pct",
            "return_reason",
        ),
        ("order_number", "line_number"),
    ),
    RawTable(
        "erp_invoices",
        (
            "invoice_number",
            "order_number",
            "customer_number",
            "invoice_date",
            "due_date",
            "currency",
            "amount_excl_tax",
            "tax_amount",
        ),
        ("invoice_number",),
    ),
    RawTable(
        "erp_payments",
        ("payment_id", "invoice_number", "payment_date", "amount", "currency"),
        ("payment_id",),
    ),
    RawTable(
        "sd_tickets",
        (
            "ticket_id",
            "customer_number",
            "sku",
            "opened_at",
            "priority",
            "category",
            "subject",
            "description",
            "status",
            "first_response_at",
            "resolved_at",
        ),
        ("ticket_id",),
    ),
)


def _copy(
    conn: psycopg.Connection,
    target: sql.Composable,
    columns: Sequence[str],
    rows: Iterable[tuple[object, ...]],
) -> None:
    statement = sql.SQL("copy {} ({}) from stdin").format(
        target, sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with conn.cursor().copy(statement) as copy:
        for row in rows:
            copy.write_row(row)


def full_load(conn: psycopg.Connection, data: dict[str, list[tuple[object, ...]]]) -> None:
    with conn.transaction():
        names = sql.SQL(", ").join(sql.Identifier("raw", t.name) for t in RAW_TABLES)
        conn.execute(sql.SQL("truncate {}").format(names))
        for table in RAW_TABLES:
            _copy(conn, sql.Identifier("raw", table.name), table.columns, data.get(table.name, []))


def upsert(conn: psycopg.Connection, data: dict[str, list[tuple[object, ...]]]) -> dict[str, int]:
    """Insert new rows and update changed ones. Returns rows written per table."""
    written: dict[str, int] = {}
    with conn.transaction():
        for table in RAW_TABLES:
            target = sql.Identifier("raw", table.name)
            staging = sql.Identifier(f"tmp_{table.name}")
            conn.execute(
                sql.SQL("create temp table {} (like {} including defaults) on commit drop").format(
                    staging, target
                )
            )
            _copy(conn, staging, table.columns, data.get(table.name, []))
            columns = sql.SQL(", ").join(map(sql.Identifier, table.columns))
            non_key = [c for c in table.columns if c not in table.key]
            updates = sql.SQL(", ").join(
                sql.SQL("{0} = excluded.{0}").format(sql.Identifier(c)) for c in non_key
            )
            changed = sql.SQL("({}) is distinct from ({})").format(
                sql.SQL(", ").join(sql.SQL("t.{}").format(sql.Identifier(c)) for c in non_key),
                sql.SQL(", ").join(
                    sql.SQL("excluded.{}").format(sql.Identifier(c)) for c in non_key
                ),
            )
            statement = sql.SQL(
                "insert into {target} as t ({columns}) select {columns} from {staging} "
                "on conflict ({key}) do update set {updates}, _loaded_at = now() where {changed}"
            ).format(
                target=target,
                columns=columns,
                staging=staging,
                key=sql.SQL(", ").join(map(sql.Identifier, table.key)),
                updates=updates,
                changed=changed,
            )
            written[table.name] = conn.execute(statement).rowcount
    return written


def row_counts(conn: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in RAW_TABLES:
        query = sql.SQL("select count(*) from {}").format(sql.Identifier("raw", table.name))
        row = conn.execute(query).fetchone()
        counts[table.name] = row[0] if row else 0
    return counts
