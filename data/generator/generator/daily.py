"""Transactions generated day by day.

Each day uses its own RNG, seeded with (seed, scale, date), so the rows for a day are the same
whether they come from a full build or a later append. A day can create rows dated after it
(returns, payments, ticket updates); those only appear once `as_of` reaches their date.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from random import Random
from zoneinfo import ZoneInfo

from generator import reference as ref
from generator import stories
from generator.master import SCALES, Customer, Master, Product

WEEKDAY_FACTOR = (1.15, 1.15, 1.15, 1.15, 1.10, 0.45, 0.25)  # Monday first
YEARLY_GROWTH = 0.08
BASE_RETURN_RATE = 0.03


@dataclass
class Tables:
    rows: dict[str, list[tuple[object, ...]]] = field(default_factory=lambda: defaultdict(list))

    def add(self, table: str, row: tuple[object, ...]) -> None:
        self.rows[table].append(row)


def fx_rates(seed: int, as_of: date) -> dict[date, float]:
    """AUD→NZD daily rate: a bounded random walk around 1.09."""
    rng = Random(f"{seed}:fx")
    rate, rates, day = 1.09, {}, ref.HISTORY_START
    while day <= as_of:
        rate = min(1.16, max(1.03, rate + rng.gauss(0, 0.002)))
        rates[day] = round(rate, 6)
        day += timedelta(days=1)
    return rates


def _days_to_pay(rng: Random, customer: Customer, invoice_date: date) -> int | None:
    if customer.customer_number == stories.LATE_PAYER_CUSTOMER_NUMBER:
        story_days = stories.late_payer_days(invoice_date)
        if story_days is not None:
            return story_days + rng.randint(-4, 4)
        return rng.randint(20, 34)
    roll = rng.random()
    if roll < 0.02:
        return None  # never paid
    if roll < 0.72:
        return rng.randint(10, 32)
    if roll < 0.95:
        return rng.randint(33, 60)
    return rng.randint(61, 95)


def _local(day: date, hour: float, region: str) -> datetime:
    tz = ZoneInfo(ref.REGIONS_BY_CODE[region].timezone)
    start = datetime.combine(day, time(0, 0), tzinfo=tz)
    return start + timedelta(hours=hour)


class DayGenerator:
    def __init__(self, master: Master, seed: int, scale_name: str, rates: dict[date, float]):
        self.master = master
        self.seed = seed
        self.scale_name = scale_name
        self.rates = rates
        self.reps_by_id = {rep.user_id: rep for rep in master.reps}
        self.products_by_category: dict[str, list[Product]] = defaultdict(list)
        for product in master.products:
            self.products_by_category[product.category].append(product)
        self.story_products = self.products_by_category[stories.DISCOUNT_CATEGORY]
        self.scale = SCALES[scale_name]

    def _volume(self, day: date, base: float) -> float:
        years = (day - ref.HISTORY_START).days / 365
        return base * WEEKDAY_FACTOR[day.weekday()] * (1 + YEARLY_GROWTH * years)

    def _pick_product(self, rng: Random, day: date) -> Product:
        categories = list(ref.CATEGORIES)
        weights = [c.weight * c.season[day.month - 1] for c in categories]
        category = rng.choices(categories, weights)[0]
        options = self.products_by_category[category.name]
        return rng.choices(options, [p.popularity for p in options])[0]

    def _price(self, product: Product, currency: str, day: date) -> float:
        if currency == "NZD":
            return product.list_price_nzd
        return round(product.list_price_nzd / self.rates[day], 2)

    def generate(self, day: date, as_of: date, out: Tables) -> None:
        rng = Random(f"{self.seed}:{self.scale_name}:{day.isoformat()}")
        active = [c for c in self.master.customers if c.is_active(day)]
        weights = [c.order_weight for c in active]
        self._orders(rng, day, as_of, active, weights, out)
        self._tickets(rng, day, as_of, active, weights, out)

    def _orders(
        self,
        rng: Random,
        day: date,
        as_of: date,
        active: list[Customer],
        weights: list[float],
        out: Tables,
    ) -> None:
        n_orders = max(0, round(rng.gauss(self._volume(day, self.scale.orders_per_day), 2)))
        for n in range(1, n_orders + 1):
            customer = rng.choices(active, weights)[0]
            rep = self.reps_by_id[customer.owner_user_id]
            order_number = f"SO-{day:%Y%m%d}-{n:04d}"
            out.add(
                "erp_sales_orders",
                (
                    order_number,
                    "sale",
                    customer.customer_number,
                    rep.user_id,
                    day,
                    customer.currency,
                ),
            )
            lines = [self._pick_product(rng, day) for _ in range(rng.randint(1, 5))]
            if stories.is_discount_story(
                rep.full_name, customer.region, stories.DISCOUNT_CATEGORY, day
            ):
                lines += [
                    rng.choice(self.story_products) for _ in range(stories.DISCOUNT_EXTRA_LINES)
                ]
            subtotal = 0.0
            returns: list[tuple[Product, int, float, float]] = []
            for line_number, product in enumerate(lines, start=1):
                category = ref.CATEGORIES_BY_NAME[product.category]
                quantity = rng.randint(1, category.max_quantity)
                if stories.is_discount_story(rep.full_name, customer.region, product.category, day):
                    discount = round(rng.uniform(*stories.DISCOUNT_RANGE_PCT) * 2) / 2
                else:
                    roll = rng.random()
                    if roll < 0.6:
                        discount = 0.0
                    elif roll < 0.9:
                        discount = round(rng.uniform(2, 10) * 2) / 2
                    else:
                        discount = round(rng.uniform(10, ref.DISCOUNT_CAP_PCT) * 2) / 2
                unit_price = self._price(product, customer.currency, day)
                out.add(
                    "erp_sales_order_lines",
                    (order_number, line_number, product.sku, quantity, unit_price, discount, None),
                )
                subtotal += quantity * unit_price * (1 - discount / 100)
                return_rate = (
                    stories.RETURNS_RATE
                    if stories.in_returns_story(product.sku, customer.region, day)
                    else BASE_RETURN_RATE
                )
                if rng.random() < return_rate:
                    returns.append((product, quantity, unit_price, discount))
            self._invoice(rng, day, as_of, customer, order_number, subtotal, out)
            for k, (product, quantity, unit_price, discount) in enumerate(returns, 1):
                self._return(
                    rng,
                    day,
                    as_of,
                    customer,
                    rep.user_id,
                    order_number,
                    k,
                    product,
                    quantity,
                    unit_price,
                    discount,
                    out,
                )

    def _invoice(
        self,
        rng: Random,
        day: date,
        as_of: date,
        customer: Customer,
        order_number: str,
        subtotal: float,
        out: Tables,
    ) -> None:
        # Draw every random value before filtering by `as_of`, so the RNG stream for a day is
        # the same whatever `as_of` is.
        invoice_date = day + timedelta(days=rng.randint(0, 2))
        days = _days_to_pay(rng, customer, invoice_date)
        if invoice_date > as_of:
            return
        invoice_number = "INV-" + order_number.removeprefix("SO-")
        amount = round(subtotal, 2)
        tax = round(amount * ref.GST_RATE[customer.currency], 2)
        due_date = invoice_date + timedelta(days=ref.PAYMENT_TERMS_DAYS)
        out.add(
            "erp_invoices",
            (
                invoice_number,
                order_number,
                customer.customer_number,
                invoice_date,
                due_date,
                customer.currency,
                amount,
                tax,
            ),
        )
        if days is not None and invoice_date + timedelta(days=days) <= as_of:
            out.add(
                "erp_payments",
                (
                    "PAY-" + invoice_number.removeprefix("INV-"),
                    invoice_number,
                    invoice_date + timedelta(days=days),
                    round(amount + tax, 2),
                    customer.currency,
                ),
            )

    def _return(
        self,
        rng: Random,
        day: date,
        as_of: date,
        customer: Customer,
        rep_id: int,
        order_number: str,
        k: int,
        product: Product,
        quantity: int,
        unit_price: float,
        discount: float,
        out: Tables,
    ) -> None:
        story = stories.in_returns_story(product.sku, customer.region, day)
        return_date = day + timedelta(days=rng.randint(5, 30))
        reason = stories.RETURNS_REASON if story else rng.choice(ref.RETURN_REASONS)
        returned = rng.randint(1, quantity)
        if return_date > as_of:
            return
        return_number = f"RO-{order_number.removeprefix('SO-')}-{k}"
        out.add(
            "erp_sales_orders",
            (
                return_number,
                "return",
                customer.customer_number,
                rep_id,
                return_date,
                customer.currency,
            ),
        )
        out.add(
            "erp_sales_order_lines",
            (return_number, 1, product.sku, -returned, unit_price, discount, reason),
        )

    def _tickets(
        self,
        rng: Random,
        day: date,
        as_of: date,
        active: list[Customer],
        weights: list[float],
        out: Tables,
    ) -> None:
        base = self._volume(day, self.scale.tickets_per_day)
        n_tickets = max(0, round(rng.gauss(base, 1.5)))
        planned: list[tuple[Customer, str | None]] = [
            (rng.choices(active, weights)[0], None) for _ in range(n_tickets)
        ]
        # Story 4: AU-WEST gets extra tickets while short-staffed.
        if stories.SLA_START <= day <= stories.SLA_END:
            au_west = [c for c in active if c.region == stories.SLA_REGION]
            share = ref.REGIONS_BY_CODE[stories.SLA_REGION].customer_share
            expected = base * share * (stories.SLA_VOLUME_MULTIPLIER - 1)
            extra = int(expected) + (rng.random() < expected % 1)
            planned += [(rng.choice(au_west), None) for _ in range(extra)]
        # Story 2: tent fault tickets from NZ-NORTH customers.
        if stories.RETURNS_START <= day <= stories.RETURNS_END:
            nz_north = [c for c in active if c.region == stories.RETURNS_REGION]
            count = round(rng.uniform(0, 2 * stories.RETURNS_TICKETS_PER_DAY))
            planned += [(rng.choice(nz_north), stories.RETURNS_SKU) for _ in range(count)]

        products_by_sku = {p.sku: p for p in self.master.products}
        for n, (customer, story_sku) in enumerate(planned, start=1):
            ticket_id = f"T-{day:%Y%m%d}-{n:04d}"
            if story_sku:
                category, priority = "Product fault", rng.choice(("P2", "P3"))
                product: Product | None = products_by_sku[story_sku]
            else:
                category = rng.choices(
                    list(ref.TICKET_CATEGORY_WEIGHTS), list(ref.TICKET_CATEGORY_WEIGHTS.values())
                )[0]
                priority = rng.choices(
                    list(ref.TICKET_PRIORITY_WEIGHTS), list(ref.TICKET_PRIORITY_WEIGHTS.values())
                )[0]
                needs_product = category in ("Product fault", "Returns", "Technical support")
                product = self._pick_product(rng, day) if needs_product else None
            subject_t, description_t = ref.TICKET_CATEGORIES[category]
            values = {
                "order": f"SO-{day:%Y%m%d}-{rng.randint(1, 60):04d}",
                "city": customer.city,
                "contact": customer.contact_name,
                "phone": customer.contact_phone,
                "product": product.name if product else "",
            }
            subject = subject_t.format(**values)
            description = description_t.format(**values)
            if story_sku:
                subject = f"{stories.RETURNS_PRODUCT_NAME}: zip failure"
                description = (
                    f"{customer.contact_name} reports the zip on the "
                    f"{stories.RETURNS_PRODUCT_NAME} split on first use."
                )

            opened_at = _local(day, rng.uniform(8, 17.5), customer.region)
            response_sla, resolution_sla = ref.SLA_HOURS[priority]
            response_hours = rng.expovariate(1 / (response_sla * 0.4))
            resolution_hours = rng.lognormvariate(0, 0.45) * resolution_sla * 0.55
            if priority in stories.SLA_PRIORITIES and stories.in_sla_story(customer.region, day):
                resolution_hours *= stories.SLA_RESOLUTION_MULTIPLIER
                response_hours *= 2
            responded = opened_at + timedelta(hours=response_hours)
            resolved = opened_at + timedelta(hours=max(resolution_hours, response_hours + 0.25))

            # Hide what hasn't happened yet as of the end of `as_of` (local time).
            as_of_end = datetime.combine(as_of + timedelta(days=1), time(0, 0), opened_at.tzinfo)
            first_response_at: datetime | None = responded if responded < as_of_end else None
            resolved_at: datetime | None = resolved if resolved < as_of_end else None
            if resolved_at is not None:
                status = "resolved"
            elif first_response_at is not None:
                status = "in_progress"
            else:
                status = "open"
            out.add(
                "sd_tickets",
                (
                    ticket_id,
                    customer.customer_number,
                    product.sku if product else None,
                    opened_at,
                    priority,
                    category,
                    subject,
                    description,
                    status,
                    first_response_at,
                    resolved_at,
                ),
            )


def generate(master: Master, seed: int, scale_name: str, as_of: date) -> Tables:
    """All transactional rows up to and including `as_of`."""
    rates = fx_rates(seed, as_of)
    out = Tables()
    for day, rate in rates.items():
        out.add("ref_fx_rates", (day, rate))
    generator = DayGenerator(master, seed, scale_name, rates)
    day = ref.HISTORY_START
    while day <= as_of:
        generator.generate(day, as_of, out)
        day += timedelta(days=1)
    return out
