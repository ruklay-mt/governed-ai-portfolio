"""The planted stories (spec §4.1) are visible through the semantic layer, for the right persona.

Each query is compiled for the persona's role and runs as that persona's login, the way the
agent's get_metric tool will run it.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

import psycopg

from app.semantic.compiler import compile_metric
from app.semantic.models import MetricRequest

TODAY = date(2026, 10, 27)
ROLES = {
    "agent_sales_rep_nz_south": "r_sales_rep",
    "agent_sales_manager": "r_sales_manager",
    "agent_finance": "r_finance",
    "agent_support": "r_support",
}


def run(
    connect_as: Callable[[str], psycopg.Connection], login: str, **request: Any
) -> list[tuple[Any, ...]]:
    compiled = compile_metric(MetricRequest.model_validate(request), ROLES[login], today=TODAY)
    return connect_as(login).execute(compiled.sql, compiled.params).fetchall()


def test_discount_story_finance_sees_over_cap_rep(
    connect_as: Callable[[str], psycopg.Connection],
) -> None:
    rows = run(
        connect_as,
        "agent_finance",
        metric="avg_discount_pct",
        dimensions=["sales_rep"],
        filters={"region": "AU-EAST", "product_category": "Safety Equipment"},
        time_range="2026-04-01..2026-10-27",
    )
    top_rep, top_discount = rows[0]
    assert top_rep == "Jake Morrison"
    assert top_discount > 15


def test_returns_story_trailpeak_rate_spikes(
    connect_as: Callable[[str], psycopg.Connection],
) -> None:
    def tent_return_rate(regions: list[str]) -> float:
        rows = run(
            connect_as,
            "agent_sales_manager",
            metric="return_rate",
            filters={"region": regions, "product": "TrailPeak 2-Person Tent"},
            time_range="2026-03-01..2026-04-30",
        )
        return float(rows[0][0] or 0)

    # Same tent, same months: NZ-NORTH (faulty batch) against the other regions.
    spike = tent_return_rate(["NZ-NORTH"])
    elsewhere = tent_return_rate(["NZ-SOUTH", "AU-EAST", "AU-WEST"])
    assert spike > 0
    assert spike >= 2 * elsewhere  # about 4x at full scale; small CI data is noisier


def test_late_payer_story_has_overdue_balance(
    connect_as: Callable[[str], psycopg.Connection],
) -> None:
    rows = run(
        connect_as,
        "agent_finance",
        metric="ar_overdue_amount",
        filters={"customer": "Southern Cross Builders Pty Ltd"},
    )
    assert rows[0][0] > 0


def test_sla_story_au_west_breaches_jump_in_january(
    connect_as: Callable[[str], psycopg.Connection],
) -> None:
    def au_west_breach_rate(time_range: str) -> float:
        rows = run(
            connect_as,
            "agent_support",
            metric="sla_breach_rate",
            filters={"region": "AU-WEST", "ticket_priority": ["P1", "P2"]},
            time_range=time_range,
        )
        return float(rows[0][0] or 0)

    story = au_west_breach_rate("2026-01-05..2026-01-31")
    before = au_west_breach_rate("2025-09-01..2025-12-31")
    assert story >= 50
    assert before <= 30


def test_sales_rep_revenue_is_scoped_to_own_region(
    connect_as: Callable[[str], psycopg.Connection],
) -> None:
    rows = run(connect_as, "agent_sales_rep_nz_south", metric="revenue", dimensions=["region"])
    assert [row[0] for row in rows] == ["NZ-SOUTH"]
