"""Generator tests that need no database: determinism, append consistency, planted stories."""

import hashlib
from collections import defaultdict
from datetime import date

import pytest

from generator import reference as ref
from generator import stories
from generator.build import build

SEED = 20231101
AS_OF = date(2026, 10, 27)


@pytest.fixture(scope="module")
def small() -> dict[str, list[tuple[object, ...]]]:
    return build(SEED, "small", AS_OF)


@pytest.fixture(scope="module")
def full() -> dict[str, list[tuple[object, ...]]]:
    """Stories are checked at full scale, where their size matches the demo."""
    return build(SEED, "full", AS_OF)


def _digest(data: dict[str, list[tuple[object, ...]]]) -> str:
    h = hashlib.sha256()
    for table in sorted(data):
        for row in data[table]:
            h.update(repr(row).encode())
    return h.hexdigest()


def test_same_seed_gives_identical_data(small: dict[str, list[tuple[object, ...]]]) -> None:
    assert _digest(build(SEED, "small", AS_OF)) == _digest(small)


def test_different_seed_gives_different_data(small: dict[str, list[tuple[object, ...]]]) -> None:
    assert _digest(build(SEED + 1, "small", AS_OF)) != _digest(small)


def test_next_day_only_adds_or_updates_rows(small: dict[str, list[tuple[object, ...]]]) -> None:
    """An append for the next day must keep every existing key (rows never disappear)."""
    next_day = build(SEED, "small", date(2026, 10, 28))
    for table, rows in small.items():
        keys_today = {row[0] if table != "erp_sales_order_lines" else row[:2] for row in rows}
        keys_next = {
            row[0] if table != "erp_sales_order_lines" else row[:2] for row in next_day[table]
        }
        assert keys_today <= keys_next, table
    # Immutable history: orders dated before today are identical.
    old_orders = [r for r in small["erp_sales_orders"] if r[4] < AS_OF]
    assert set(old_orders) <= set(next_day["erp_sales_orders"])


def test_keys_are_unique(small: dict[str, list[tuple[object, ...]]]) -> None:
    for table, rows in small.items():
        keys = [row[:2] if table == "erp_sales_order_lines" else row[0] for row in rows]
        assert len(keys) == len(set(keys)), table


def test_nothing_is_dated_after_as_of(small: dict[str, list[tuple[object, ...]]]) -> None:
    assert max(r[4] for r in small["erp_sales_orders"]) <= AS_OF
    assert max(r[3] for r in small["erp_invoices"]) <= AS_OF
    assert max(r[2] for r in small["erp_payments"]) <= AS_OF


# --- Planted stories (spec §4.1) -------------------------------------------------------------


def _sales_lines(data: dict[str, list[tuple[object, ...]]]) -> list[dict[str, object]]:
    orders = {r[0]: r for r in data["erp_sales_orders"]}
    customers = {r[0]: r for r in data["erp_customers"]}
    reps = {r[0]: r[1] for r in data["crm_users"]}
    products = {r[0]: r for r in data["erp_products"]}
    lines = []
    for order_number, _, sku, quantity, _, discount, reason in data["erp_sales_order_lines"]:
        order = orders[order_number]
        lines.append(
            {
                "type": order[1],
                "date": order[4],
                "region": customers[order[2]][2],
                "rep": reps[order[3]],
                "sku": sku,
                "category": products[sku][2],
                "quantity": quantity,
                "discount": discount,
                "reason": reason,
            }
        )
    return lines


def test_story_discounting(full: dict[str, list[tuple[object, ...]]]) -> None:
    lines = [
        line
        for line in _sales_lines(full)
        if line["type"] == "sale"
        and line["region"] == stories.DISCOUNT_REGION
        and line["category"] == stories.DISCOUNT_CATEGORY
        and line["date"] >= stories.DISCOUNT_START  # type: ignore[operator]
    ]
    jake = [line for line in lines if line["rep"] == stories.DISCOUNT_REP_NAME]
    others = [line for line in lines if line["rep"] != stories.DISCOUNT_REP_NAME]
    assert jake and others
    assert min(float(line["discount"]) for line in jake) > ref.DISCOUNT_CAP_PCT  # type: ignore[arg-type]
    assert max(float(line["discount"]) for line in others) <= ref.DISCOUNT_CAP_PCT  # type: ignore[arg-type]


def test_story_returns_spike(full: dict[str, list[tuple[object, ...]]]) -> None:
    lines = [line for line in _sales_lines(full) if line["sku"] == stories.RETURNS_SKU]
    story = [line for line in lines if line["reason"] == stories.RETURNS_REASON]
    assert len(story) >= 8
    assert all(line["region"] == stories.RETURNS_REGION for line in story)

    def return_ratio(region: str, start: date, end: date) -> float:
        """Units returned per unit sold, for the story tent, by order date."""
        in_window = [
            line
            for line in lines
            if line["region"] == region and start <= line["date"] <= end  # type: ignore[operator]
        ]
        sold = sum(int(line["quantity"]) for line in in_window if line["type"] == "sale")  # type: ignore[call-overload]
        returned = -sum(int(line["quantity"]) for line in in_window if line["type"] == "return")  # type: ignore[call-overload]
        return returned / sold

    spike = return_ratio(stories.RETURNS_REGION, date(2026, 3, 15), date(2026, 5, 20))
    usual = return_ratio(stories.RETURNS_REGION, date(2025, 3, 15), date(2025, 5, 20))
    assert spike >= 3 * usual
    tickets = [t for t in full["sd_tickets"] if t[2] == stories.RETURNS_SKU and "zip" in str(t[6])]
    assert tickets


def test_story_late_payer(full: dict[str, list[tuple[object, ...]]]) -> None:
    invoices = {
        r[0]: r[3] for r in full["erp_invoices"] if r[2] == stories.LATE_PAYER_CUSTOMER_NUMBER
    }
    days_by_quarter: dict[tuple[int, int], list[int]] = defaultdict(list)
    for _, invoice_number, payment_date, _, _ in full["erp_payments"]:
        if invoice_number in invoices:
            invoice_date = invoices[invoice_number]
            quarter = (invoice_date.year, (invoice_date.month - 1) // 3 + 1)  # type: ignore[attr-defined]
            days_by_quarter[quarter].append((payment_date - invoice_date).days)  # type: ignore[operator]
    average = {q: sum(d) / len(d) for q, d in days_by_quarter.items()}
    assert average[(2026, 3)] >= 70
    assert average[(2024, 3)] < 35
    assert average[(2025, 1)] < average[(2025, 3)] < average[(2026, 1)] < average[(2026, 3)]


def test_story_sla_breach_cluster(full: dict[str, list[tuple[object, ...]]]) -> None:
    customers = {r[0]: r[2] for r in full["erp_customers"]}
    resolution_sla = {p: h[1] for p, h in ref.SLA_HOURS.items()}

    def breach_rate(region: str, start: date, end: date) -> float:
        tickets = [
            t
            for t in full["sd_tickets"]
            if customers[str(t[1])] == region
            and t[4] in stories.SLA_PRIORITIES
            and start <= t[3].date() <= end  # type: ignore[attr-defined]
            and t[10] is not None
        ]
        breached = [
            t
            for t in tickets
            if (t[10] - t[3]).total_seconds() / 3600 > resolution_sla[str(t[4])]  # type: ignore[operator]
        ]
        return len(breached) / len(tickets)

    story = breach_rate(stories.SLA_REGION, stories.SLA_START, stories.SLA_END)
    before = breach_rate(stories.SLA_REGION, date(2025, 9, 1), date(2025, 12, 31))
    assert story >= 0.6
    assert before <= 0.25
