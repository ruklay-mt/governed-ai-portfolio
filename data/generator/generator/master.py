"""Master data: sales reps, customers, CRM accounts and products. Seeded once, never changes."""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from random import Random

from generator import reference as ref
from generator import stories


@dataclass(frozen=True)
class Rep:
    user_id: int
    full_name: str
    region: str
    title: str


@dataclass(frozen=True)
class Customer:
    customer_number: str
    name: str
    region: str
    city: str
    currency: str
    segment: str
    credit_limit: float
    contact_name: str
    contact_email: str
    contact_phone: str
    created_on: date
    deleted_at: datetime | None
    owner_user_id: int
    order_weight: float

    def is_active(self, day: date) -> bool:
        return self.created_on <= day and (self.deleted_at is None or self.deleted_at.date() > day)


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    list_price_nzd: float
    unit_cost_nzd: float
    popularity: float


@dataclass(frozen=True)
class Scale:
    customers: int
    products_per_category: int
    orders_per_day: float
    tickets_per_day: float


SCALES = {
    "full": Scale(customers=2000, products_per_category=125, orders_per_day=55, tickets_per_day=27),
    "small": Scale(customers=200, products_per_category=15, orders_per_day=6, tickets_per_day=4),
}

# Named people that the personas and stories refer to.
FIXED_REPS = (
    ("Mia Tane", "NZ-SOUTH", "Account Manager"),
    ("Jake Morrison", "AU-EAST", "Account Manager"),
    ("Liam Chen", "NZ-NORTH", "Sales Manager"),
)
REPS_PER_REGION = 5


@dataclass(frozen=True)
class Master:
    reps: tuple[Rep, ...]
    customers: tuple[Customer, ...]
    products: tuple[Product, ...]
    accounts: tuple[tuple[object, ...], ...]

    def account_managers(self, region: str) -> list[Rep]:
        return [r for r in self.reps if r.region == region and r.title == "Account Manager"]


def _person(rng: Random) -> str:
    return f"{rng.choice(ref.FIRST_NAMES)} {rng.choice(ref.LAST_NAMES)}"


def _email(name: str, domain: str) -> str:
    return f"{name.lower().replace(' ', '.')}@{domain}"


def build_reps(rng: Random) -> tuple[Rep, ...]:
    reps: list[Rep] = []
    taken = {name for name, _, _ in FIXED_REPS}
    for name, region_code, title in FIXED_REPS:
        reps.append(Rep(len(reps) + 1, name, region_code, title))
    for region in ref.REGIONS:
        while len([r for r in reps if r.region == region.code and r.title != "Sales Manager"]) < (
            REPS_PER_REGION
        ):
            name = _person(rng)
            if name in taken:
                continue
            taken.add(name)
            reps.append(Rep(len(reps) + 1, name, region.code, "Account Manager"))
    return tuple(reps)


def _company_name(rng: Random, currency: str) -> str:
    suffix = "Ltd" if currency == "NZD" else "Pty Ltd"
    return (
        f"{rng.choice(ref.NAME_PREFIXES)} {rng.choice(ref.NAME_TRADES)} "
        f"{rng.choice(ref.NAME_KINDS)} {suffix}"
    )


def build_customers(rng: Random, scale: Scale, reps: tuple[Rep, ...]) -> tuple[Customer, ...]:
    regions = list(ref.REGIONS)
    shares = [region.customer_share for region in regions]
    used_names = {stories.LATE_PAYER_NAME}
    customers: list[Customer] = []
    for n in range(1, scale.customers + 1):
        number = f"C-{n:05d}"
        if number == stories.LATE_PAYER_CUSTOMER_NUMBER:
            region = ref.REGIONS_BY_CODE[stories.LATE_PAYER_REGION]
            name, segment = stories.LATE_PAYER_NAME, "key"
        else:
            region = rng.choices(regions, shares)[0]
            segment = "key" if rng.random() < 0.05 else "standard"
            name = _company_name(rng, region.currency)
            while name in used_names:
                name = _company_name(rng, region.currency)
        used_names.add(name)
        city = rng.choice(region.cities)
        owners = [r for r in reps if r.region == region.code and r.title == "Account Manager"]
        contact = _person(rng)
        created_on = ref.HISTORY_START - timedelta(days=rng.randint(30, 1500))
        if rng.random() < 0.10:  # some customers join during the history window
            created_on = ref.HISTORY_START + timedelta(days=rng.randint(0, 900))
        deleted_at = None
        if segment == "standard" and rng.random() < 0.02:
            deleted_at = datetime.combine(
                created_on + timedelta(days=rng.randint(200, 900)),
                datetime.min.time(),
                tzinfo=UTC,
            )
        weight = rng.uniform(6, 10) if segment == "key" else rng.lognormvariate(0, 0.6)
        domain = name.split(" ")[0].lower() + (".co.nz" if region.currency == "NZD" else ".com.au")
        customers.append(
            Customer(
                customer_number=number,
                name=name,
                region=region.code,
                city=city,
                currency=region.currency,
                segment=segment,
                credit_limit=float(
                    rng.choice((5, 10, 20, 50)) * 1000 * (5 if segment == "key" else 1)
                ),
                contact_name=contact,
                contact_email=_email(contact, domain),
                contact_phone=f"+{64 if region.currency == 'NZD' else 61} {rng.randint(200, 999)} "
                f"{rng.randint(1000, 9999)}",
                created_on=created_on,
                deleted_at=deleted_at,
                owner_user_id=rng.choice(owners).user_id,
                order_weight=weight,
            )
        )
    return tuple(customers)


def _product_name(rng: Random, category: ref.Category) -> str:
    return f"{rng.choice(ref.BRANDS)} {rng.choice(category.nouns)} {rng.randint(1, 99)}"


def build_products(rng: Random, scale: Scale) -> tuple[Product, ...]:
    products: list[Product] = []
    for category in ref.CATEGORIES:
        names: set[str] = set()
        for n in range(1, scale.products_per_category + 1):
            sku = f"{category.sku_prefix}-{n:04d}"
            if sku == stories.RETURNS_SKU:
                name = stories.RETURNS_PRODUCT_NAME
                popularity = 0.0  # set below, once the rest of the category is known
            else:
                name = _product_name(rng, category)
                while name in names:
                    name = _product_name(rng, category)
                popularity = rng.paretovariate(1.5)
            names.add(name)
            low, high = category.price_range_nzd
            price = round(rng.uniform(low, high), 2)
            cost = round(price * category.cost_ratio * rng.uniform(0.9, 1.1), 2)
            products.append(Product(sku, name, category.name, price, cost, popularity))

    # Give the story tent a fixed share of its category at every scale.
    tent = next(p for p in products if p.sku == stories.RETURNS_SKU)
    rest = sum(p.popularity for p in products if p.category == tent.category and p is not tent)
    share = stories.RETURNS_SKU_CATEGORY_SHARE
    products[products.index(tent)] = replace(tent, popularity=rest * share / (1 - share))
    return tuple(products)


def _crm_ref(rng: Random, customer_number: str) -> str | None:
    """Hand-typed ERP reference in the CRM: usually right, sometimes formatted differently."""
    digits = customer_number.split("-")[1]
    roll = rng.random()
    if roll < 0.70:
        return customer_number
    if roll < 0.88:
        return f"C{digits}"
    if roll < 0.97:
        return f"c-{int(digits)}"
    return None


def build_accounts(rng: Random, customers: tuple[Customer, ...]) -> tuple[tuple[object, ...], ...]:
    """CRM accounts (raw.crm_accounts rows), including a few duplicates."""
    rows: list[tuple[object, ...]] = []
    order = list(customers)
    rng.shuffle(order)
    for customer in order:
        copies = 2 if rng.random() < 0.01 else 1
        for copy in range(copies):
            account_id = f"ACC-{len(rows) + 1:05d}"
            name = customer.name if copy == 0 else customer.name.upper()
            rows.append(
                (
                    account_id,
                    name,
                    _crm_ref(rng, customer.customer_number) if copy == 0 else None,
                    customer.owner_user_id,
                    customer.region,
                    rng.choice(ref.INDUSTRIES),
                    customer.created_on + timedelta(days=copy * rng.randint(30, 300)),
                )
            )
    return tuple(rows)


def build_master(seed: int, scale_name: str) -> Master:
    rng = Random(f"{seed}:master:{scale_name}")
    scale = SCALES[scale_name]
    reps = build_reps(rng)
    customers = build_customers(rng, scale, reps)
    products = build_products(rng, scale)
    accounts = build_accounts(rng, customers)
    return Master(reps, customers, products, accounts)
