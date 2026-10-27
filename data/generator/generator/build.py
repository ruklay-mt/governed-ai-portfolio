"""Assemble every raw table's rows for a given seed, scale and as-of date."""

from datetime import date

from generator import daily
from generator import reference as ref
from generator.master import build_master


def build(seed: int, scale: str, as_of: date) -> dict[str, list[tuple[object, ...]]]:
    if as_of < ref.HISTORY_START:
        raise ValueError(f"as_of must be on or after {ref.HISTORY_START}")
    master = build_master(seed, scale)
    tables = daily.generate(master, seed, scale, as_of).rows

    domain = "harbourline.example"
    tables["crm_users"] = [
        (
            rep.user_id,
            rep.full_name,
            f"{rep.full_name.lower().replace(' ', '.')}@{domain}",
            rep.region,
            rep.title,
            True,
        )
        for rep in master.reps
    ]
    tables["erp_customers"] = [
        (
            c.customer_number,
            c.name,
            c.region,
            c.city,
            c.currency,
            c.segment,
            c.credit_limit,
            c.contact_name,
            c.contact_email,
            c.contact_phone,
            c.created_on,
            c.deleted_at,
        )
        for c in master.customers
    ]
    tables["crm_accounts"] = list(master.accounts)
    tables["erp_products"] = [
        (p.sku, p.name, p.category, p.list_price_nzd, p.unit_cost_nzd) for p in master.products
    ]
    tables["sd_sla_policies"] = [
        (priority, response, resolution)
        for priority, (response, resolution) in ref.SLA_HOURS.items()
    ]
    return dict(tables)
