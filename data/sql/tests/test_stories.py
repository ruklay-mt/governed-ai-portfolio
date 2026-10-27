"""The planted stories (spec §4.1) are visible to the roles that should see them, and only those.

These checks run at whatever scale is loaded (small in CI, full on Neon dev), so they test the
shape of each story rather than exact numbers. They are the seed for the eval ground truth.
"""

from collections.abc import Callable

import psycopg
import pytest

Connect = Callable[[str], psycopg.Connection]

SALES_REP = "agent_sales_rep_nz_south"
MANAGER = "agent_sales_manager"
FINANCE = "agent_finance"
SUPPORT = "agent_support"


def _row(conn: psycopg.Connection, query: str) -> tuple[object, ...]:
    row = conn.execute(query).fetchone()  # type: ignore[arg-type]
    assert row is not None
    return tuple(row)


OVER_CAP_DISCOUNTS = """
    select
        avg(s.discount_pct) filter (where r.rep_name = 'Jake Morrison') as jake,
        avg(s.discount_pct) filter (where r.rep_name <> 'Jake Morrison') as others,
        max(s.discount_pct) filter (where r.rep_name <> 'Jake Morrison') as others_max
    from marts.fct_sales as s
    inner join marts.dim_product as p on s.product_key = p.product_key
    inner join marts.dim_sales_rep as r on s.sales_rep_key = r.sales_rep_key
    where s.region = 'AU-EAST' and p.category = 'Safety Equipment'
      and s.line_type = 'sale' and s.order_date >= date '2026-04-01'
"""


def test_discounting_story_visible_to_finance(connect_as: Connect) -> None:
    jake, others, others_max = _row(connect_as(FINANCE), OVER_CAP_DISCOUNTS)
    assert float(jake) > 15 > float(others_max)  # type: ignore[arg-type]
    assert float(jake) > 2 * float(others)  # type: ignore[arg-type]


def test_discounting_margin_is_hidden_from_sales(connect_as: Connect) -> None:
    conn = connect_as(MANAGER)
    _row(conn, OVER_CAP_DISCOUNTS)  # managers can see the discounts...
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("select sum(margin_nzd) from marts.fct_sales")  # ...but not the margin hit


def test_discounting_story_not_visible_to_nz_south_rep(connect_as: Connect) -> None:
    jake, _, _ = _row(connect_as(SALES_REP), OVER_CAP_DISCOUNTS)
    assert jake is None


RETURNS_SPIKE = """
    select count(*)
    from marts.fct_sales
    where line_type = 'return' and return_reason = 'Faulty zip'
      and product_key = 'CMP-0001' and region = 'NZ-NORTH'
"""


def test_returns_spike_visible_to_manager(connect_as: Connect) -> None:
    (returns,) = _row(connect_as(MANAGER), RETURNS_SPIKE)
    assert int(returns) >= 1  # type: ignore[call-overload]


def test_returns_spike_tickets_visible_to_support(connect_as: Connect) -> None:
    (tickets,) = _row(
        connect_as(SUPPORT),
        "select count(*) from marts.fct_tickets "
        "where product_key = 'CMP-0001' and subject like '%zip failure'",
    )
    assert int(tickets) >= 1  # type: ignore[call-overload]


def test_returns_spike_not_visible_to_nz_south_rep(connect_as: Connect) -> None:
    assert _row(connect_as(SALES_REP), RETURNS_SPIKE) == (0,)


LATE_PAYER = """
    select
        avg(days_to_pay) filter (where invoice_date >= date '2026-07-01') as recent,
        avg(days_to_pay) filter (where invoice_date < date '2025-01-01') as before
    from marts.fct_invoices
    where customer_key = 'C-00001' and days_to_pay is not null
"""


def test_late_payer_visible_to_finance(connect_as: Connect) -> None:
    recent, before = _row(connect_as(FINANCE), LATE_PAYER)
    assert float(recent) >= 65  # type: ignore[arg-type]
    assert float(before) < 40  # type: ignore[arg-type]


@pytest.mark.parametrize("login", [SALES_REP, MANAGER, SUPPORT])
def test_late_payer_hidden_from_non_finance(connect_as: Connect, login: str) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        connect_as(login).execute(LATE_PAYER)  # type: ignore[arg-type]


SLA_BREACH_RATE = """
    select
        avg(is_sla_breached::int) filter (
            where opened_date between date '2026-01-05' and date '2026-01-31'
        ) as story,
        avg(is_sla_breached::int) filter (
            where opened_date between date '2025-09-01' and date '2025-12-31'
        ) as before
    from marts.fct_tickets
    where region = 'AU-WEST' and priority in ('P1', 'P2')
"""


def test_sla_cluster_visible_to_support(connect_as: Connect) -> None:
    story, before = _row(connect_as(SUPPORT), SLA_BREACH_RATE)
    assert float(story) >= 0.5  # type: ignore[arg-type]
    assert float(before) <= 0.3  # type: ignore[arg-type]
