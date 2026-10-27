from datetime import date

import pytest

from app.semantic.compiler import (
    MetricNotAllowed,
    SemanticError,
    allowed_metrics,
    compile_metric,
    load_semantic_model,
    resolve_time_range,
)
from app.semantic.models import MetricRequest

TODAY = date(2026, 10, 27)
MVP_METRICS = {
    "revenue",
    "gross_margin",
    "gross_margin_pct",
    "order_count",
    "avg_discount_pct",
    "return_rate",
    "ar_overdue_amount",
    "tickets_opened",
    "sla_breach_rate",
}


def compile_for(role: str, **request: object) -> tuple[str, dict[str, object]]:
    compiled = compile_metric(MetricRequest.model_validate(request), role, today=TODAY)
    return compiled.sql, compiled.params


def test_yaml_defines_the_mvp_metrics() -> None:
    assert set(load_semantic_model().metrics) == MVP_METRICS


def test_metric_roles_follow_the_access_policy() -> None:
    assert "gross_margin" not in allowed_metrics("r_sales_rep")
    assert "ar_overdue_amount" not in allowed_metrics("r_sales_manager")
    assert set(allowed_metrics("r_support")) == {"tickets_opened", "sla_breach_rate"}
    assert set(allowed_metrics("r_finance")) == MVP_METRICS


def test_revenue_by_customer_last_quarter() -> None:
    compiled = compile_metric(
        MetricRequest(metric="revenue", dimensions=["customer"], time_range="last_quarter"),
        "r_sales_rep",
        today=TODAY,
    )
    assert compiled.sql == (
        "select c.customer_name as customer, sum(s.net_amount_nzd) as revenue\n"
        "from marts.fct_sales as s\n"
        "inner join marts.dim_customer as c on c.customer_key = s.customer_key\n"
        "where s.order_date between %(start_date)s and %(end_date)s\n"
        "group by 1\n"
        "order by 2 desc nulls last\n"
        "limit %(row_limit)s"
    )
    assert compiled.params == {
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 9, 30),
        "row_limit": 100,
    }
    assert compiled.columns == ["customer", "revenue"]
    assert "last_quarter = 2026-07-01 to 2026-09-30 (calendar dates)" in compiled.assumptions


def test_grain_orders_by_period_and_joins_once() -> None:
    sql, _ = compile_for(
        "r_finance",
        metric="gross_margin_pct",
        dimensions=["product_category", "product"],
        filters={"product_category": "Safety Equipment"},
        grain="month",
    )
    assert sql.startswith("select date_trunc('month', s.order_date)::date as period,")
    assert sql.count("join marts.dim_product") == 1
    assert "group by 1, 2, 3\norder by 1\n" in sql


def test_filter_values_are_bound_not_inlined() -> None:
    sneaky = "NZ-SOUTH' or 1=1 --"
    sql, params = compile_for("r_sales_manager", metric="revenue", filters={"region": sneaky})
    assert sneaky not in sql
    assert "s.region = any(%(filter_0)s)" in sql
    assert params["filter_0"] == [sneaky]


def test_metric_without_dimensions_has_no_group_by() -> None:
    sql, _ = compile_for("r_finance", metric="ar_overdue_amount")
    assert "group by" not in sql
    assert sql.startswith("select round(sum(i.outstanding_nzd) filter (where i.days_overdue > 0)")


def test_role_cannot_use_finance_metric() -> None:
    with pytest.raises(MetricNotAllowed):
        compile_for("r_sales_rep", metric="gross_margin")


@pytest.mark.parametrize(
    "request_fields",
    [
        {"metric": "profit"},
        {"metric": "revenue", "dimensions": ["colour"]},
        {"metric": "revenue", "dimensions": ["ticket_priority"]},  # tickets-only dimension
        {"metric": "tickets_opened", "dimensions": ["sales_rep"]},  # sales-only dimension
        {"metric": "revenue", "dimensions": ["region", "region"]},
        {"metric": "revenue", "filters": {"region": []}},
        {"metric": "revenue", "time_range": "last_fortnight"},
        {"metric": "revenue", "time_range": "2026-09-30..2026-07-01"},
    ],
)
def test_invalid_requests_are_rejected(request_fields: dict[str, object]) -> None:
    with pytest.raises(SemanticError):
        compile_for("r_finance", **request_fields)


def test_limit_is_capped_by_the_model() -> None:
    with pytest.raises(ValueError):
        MetricRequest(metric="revenue", limit=5000)


@pytest.mark.parametrize(
    ("preset", "start", "end"),
    [
        ("last_7_days", date(2026, 10, 21), TODAY),
        ("this_month", date(2026, 10, 1), TODAY),
        ("last_month", date(2026, 9, 1), date(2026, 9, 30)),
        ("this_quarter", date(2026, 10, 1), TODAY),
        ("last_quarter", date(2026, 7, 1), date(2026, 9, 30)),
        ("ytd", date(2026, 1, 1), TODAY),
        ("last_year", date(2025, 1, 1), date(2025, 12, 31)),
        ("2026-03-01..2026-04-30", date(2026, 3, 1), date(2026, 4, 30)),
    ],
)
def test_time_ranges(preset: str, start: date, end: date) -> None:
    resolved = resolve_time_range(preset, TODAY)
    assert (resolved.start, resolved.end) == (start, end)


def test_last_quarter_in_first_quarter_wraps_the_year() -> None:
    resolved = resolve_time_range("last_quarter", date(2026, 2, 10))
    assert (resolved.start, resolved.end) == (date(2025, 10, 1), date(2025, 12, 31))
