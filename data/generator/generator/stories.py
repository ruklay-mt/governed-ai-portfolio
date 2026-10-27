"""The four planted stories (spec §4.1).

Each story is a named, explicit deviation from normal behaviour, so the demo has answers worth
finding and the evals have known ground truth. Everything else in the generator is "normal".
"""

from datetime import date

# 1. Discounting erodes margin: one AU-EAST rep discounts Safety Equipment above the 15% cap
#    for the last two quarters, and sells more of it.
DISCOUNT_REP_NAME = "Jake Morrison"
DISCOUNT_REGION = "AU-EAST"
DISCOUNT_CATEGORY = "Safety Equipment"
DISCOUNT_START = date(2026, 4, 1)
DISCOUNT_RANGE_PCT = (18.0, 28.0)
DISCOUNT_EXTRA_LINES = 2

# 2. Returns spike: a faulty zip batch on one tent in NZ-NORTH.
RETURNS_SKU = "CMP-0001"
RETURNS_PRODUCT_NAME = "TrailPeak 2-Person Tent"
RETURNS_REGION = "NZ-NORTH"
RETURNS_START = date(2026, 3, 1)
RETURNS_END = date(2026, 4, 30)
RETURNS_RATE = 0.14  # about 4-5x the normal per-line return probability
RETURNS_SKU_CATEGORY_SHARE = 0.25  # a best-seller: a quarter of all Camping sales
RETURNS_REASON = "Faulty zip"
RETURNS_TICKETS_PER_DAY = 1.5

# 3. Late-paying key account: pays a little later every quarter.
LATE_PAYER_CUSTOMER_NUMBER = "C-00001"
LATE_PAYER_NAME = "Southern Cross Builders Pty Ltd"
LATE_PAYER_REGION = "AU-EAST"
LATE_PAYER_FROM = date(2025, 1, 1)
LATE_PAYER_BASE_DAYS = 35
LATE_PAYER_DAYS_PER_QUARTER = 7

# 4. SLA breach cluster: AU-WEST support is short-staffed in January 2026.
SLA_REGION = "AU-WEST"
SLA_START = date(2026, 1, 5)
SLA_END = date(2026, 1, 31)
SLA_PRIORITIES = ("P1", "P2")
SLA_RESOLUTION_MULTIPLIER = 3.5
SLA_VOLUME_MULTIPLIER = 1.5


def is_discount_story(rep_name: str, region: str, category: str, day: date) -> bool:
    return (
        rep_name == DISCOUNT_REP_NAME
        and region == DISCOUNT_REGION
        and category == DISCOUNT_CATEGORY
        and day >= DISCOUNT_START
    )


def in_returns_story(sku: str, region: str, day: date) -> bool:
    return sku == RETURNS_SKU and region == RETURNS_REGION and RETURNS_START <= day <= RETURNS_END


def late_payer_days(invoice_date: date) -> int | None:
    """Days to pay for the late payer, or None before the story starts."""
    if invoice_date < LATE_PAYER_FROM:
        return None
    quarters = (invoice_date.year - LATE_PAYER_FROM.year) * 4 + (invoice_date.month - 1) // 3
    return LATE_PAYER_BASE_DAYS + LATE_PAYER_DAYS_PER_QUARTER * quarters


def in_sla_story(region: str, day: date) -> bool:
    return region == SLA_REGION and SLA_START <= day <= SLA_END
