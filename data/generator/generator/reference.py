"""Static reference data for Harbourline Supply Co.: regions, categories, names and policies."""

from dataclasses import dataclass
from datetime import date

HISTORY_START = date(2023, 11, 1)

# Policies that the planted stories break and the policy documents describe.
DISCOUNT_CAP_PCT = 15.0
PAYMENT_TERMS_DAYS = 30
GST_RATE = {"NZD": 0.15, "AUD": 0.10}


@dataclass(frozen=True)
class Region:
    code: str
    currency: str
    timezone: str
    cities: tuple[str, ...]
    customer_share: float


REGIONS = (
    Region(
        "NZ-NORTH",
        "NZD",
        "Pacific/Auckland",
        ("Auckland", "Hamilton", "Tauranga", "Whangarei", "Napier"),
        0.30,
    ),
    Region(
        "NZ-SOUTH",
        "NZD",
        "Pacific/Auckland",
        ("Christchurch", "Dunedin", "Queenstown", "Nelson", "Invercargill"),
        0.20,
    ),
    Region(
        "AU-EAST",
        "AUD",
        "Australia/Sydney",
        ("Sydney", "Brisbane", "Newcastle", "Gold Coast", "Canberra"),
        0.35,
    ),
    Region(
        "AU-WEST",
        "AUD",
        "Australia/Perth",
        ("Perth", "Fremantle", "Bunbury", "Kalgoorlie", "Geraldton"),
        0.15,
    ),
)
REGIONS_BY_CODE = {region.code: region for region in REGIONS}

# Month multipliers, January first. Southern Hemisphere: summer is Dec-Feb.
SUMMER = (1.5, 1.4, 1.1, 0.9, 0.7, 0.6, 0.6, 0.7, 0.9, 1.1, 1.3, 1.6)
WINTER = (0.5, 0.5, 0.7, 1.0, 1.4, 1.7, 1.8, 1.5, 1.0, 0.7, 0.5, 0.5)
FLAT = (1.0,) * 12


@dataclass(frozen=True)
class Category:
    name: str
    sku_prefix: str
    price_range_nzd: tuple[float, float]
    cost_ratio: float
    max_quantity: int
    weight: float
    season: tuple[float, ...]
    nouns: tuple[str, ...]


CATEGORIES = (
    Category(
        "Camping",
        "CMP",
        (40, 900),
        0.58,
        8,
        1.2,
        SUMMER,
        ("Tent", "Sleeping Bag", "Camp Stove", "Camp Chair", "Cooler", "Tarp"),
    ),
    Category(
        "Hiking",
        "HIK",
        (20, 600),
        0.55,
        10,
        1.0,
        SUMMER,
        ("Daypack", "Trekking Poles", "Rain Jacket", "Gaiters", "Hydration Pack"),
    ),
    Category(
        "Climbing",
        "CLM",
        (15, 500),
        0.57,
        10,
        0.5,
        SUMMER,
        ("Harness", "Rope", "Carabiner Set", "Helmet", "Belay Device"),
    ),
    Category(
        "Water Sports",
        "WTR",
        (30, 1500),
        0.60,
        6,
        0.7,
        SUMMER,
        ("Kayak", "Paddle", "Life Jacket", "Wetsuit", "Dry Bag"),
    ),
    Category(
        "Safety Equipment",
        "SAF",
        (10, 400),
        0.52,
        30,
        1.3,
        FLAT,
        ("Hard Hat", "Hi-Vis Vest", "Safety Glasses", "Ear Muffs", "Fall Arrest Kit"),
    ),
    Category(
        "Workwear",
        "WRK",
        (25, 250),
        0.50,
        20,
        1.0,
        FLAT,
        ("Work Boots", "Work Pants", "Softshell Jacket", "Work Gloves", "Thermal Top"),
    ),
    Category(
        "Power Tools",
        "PWR",
        (80, 1200),
        0.65,
        6,
        0.9,
        FLAT,
        ("Drill Driver", "Circular Saw", "Angle Grinder", "Impact Driver", "Jigsaw"),
    ),
    Category(
        "Hand Tools",
        "HND",
        (10, 200),
        0.48,
        20,
        0.8,
        FLAT,
        ("Hammer", "Spanner Set", "Pliers", "Tape Measure", "Spirit Level"),
    ),
    Category(
        "Lighting",
        "LGT",
        (15, 350),
        0.55,
        15,
        0.6,
        FLAT,
        ("Headlamp", "Work Light", "Lantern", "Torch", "Flood Light"),
    ),
    Category(
        "Heating",
        "HTG",
        (60, 1500),
        0.62,
        5,
        0.6,
        WINTER,
        ("Gas Heater", "Diesel Heater", "Patio Heater", "Fan Heater", "Radiant Heater"),
    ),
    Category(
        "Generators",
        "GEN",
        (500, 4000),
        0.70,
        2,
        0.3,
        WINTER,
        ("Inverter Generator", "Portable Generator", "Standby Generator"),
    ),
    Category(
        "Fasteners",
        "FST",
        (5, 80),
        0.40,
        60,
        0.9,
        FLAT,
        ("Screw Pack", "Bolt Kit", "Anchor Set", "Rivet Pack", "Cable Ties"),
    ),
)
CATEGORIES_BY_NAME = {category.name: category for category in CATEGORIES}

BRANDS = (
    "TrailPeak",
    "Southward",
    "Kea",
    "Bushcraft",
    "Ironbark",
    "Coastline",
    "Tuatara",
    "Harbour Pro",
    "Outback",
    "Tasman",
)

NAME_PREFIXES = (
    "Kauri",
    "Totara",
    "Harbour",
    "Southern",
    "Coastal",
    "Summit",
    "Ridgeline",
    "Bluegum",
    "Wattle",
    "Ironbark",
    "Tasman",
    "Pacific",
    "Alpine",
    "Outback",
    "Riverbend",
    "Bushline",
    "Red Earth",
    "Saltwater",
    "High Country",
    "Northern",
)
NAME_TRADES = (
    "Building",
    "Outdoor",
    "Hire",
    "Construction",
    "Safety",
    "Marine",
    "Farm",
    "Trade",
    "Adventure",
    "Industrial",
    "Civil",
    "Fencing",
    "Engineering",
    "Camping",
    "Electrical",
)
NAME_KINDS = ("Supplies", "Group", "Co", "Services", "Solutions", "Depot", "Partners")
INDUSTRIES = (
    "Construction",
    "Retail",
    "Agriculture",
    "Tourism",
    "Mining",
    "Local government",
    "Events",
)

FIRST_NAMES = (
    "Mia",
    "Liam",
    "Aroha",
    "Jack",
    "Olivia",
    "Noah",
    "Charlotte",
    "Oliver",
    "Isla",
    "Wiremu",
    "Amelia",
    "Lucas",
    "Grace",
    "Ethan",
    "Ruby",
    "Hemi",
    "Chloe",
    "Mason",
    "Zoe",
    "Leo",
    "Priya",
    "Arjun",
    "Mei",
    "Daniel",
    "Tom",
)
LAST_NAMES = (
    "Smith",
    "Wilson",
    "Brown",
    "Taylor",
    "Ngata",
    "Williams",
    "Jones",
    "Walker",
    "Thompson",
    "Kaur",
    "Nguyen",
    "Kelly",
    "Martin",
    "Clarke",
    "Hohepa",
    "Singh",
    "Wright",
    "Turner",
    "Robinson",
    "Fraser",
)

# Ticket SLAs in hours: (first response, resolution).
SLA_HOURS = {"P1": (1, 8), "P2": (4, 24), "P3": (8, 72), "P4": (24, 120)}
TICKET_PRIORITY_WEIGHTS = {"P1": 0.05, "P2": 0.20, "P3": 0.50, "P4": 0.25}
TICKET_CATEGORIES = {
    "Order query": ("Where is my order {order}?", "Customer {contact} asked for an update."),
    "Delivery": ("Delivery delayed to {city}", "Freight to {city} is late. Contact: {contact}."),
    "Product fault": ("Fault reported: {product}", "{contact} reports the {product} has failed."),
    "Returns": ("Return request: {product}", "{contact} wants to return {product}."),
    "Billing": ("Invoice question", "{contact} ({phone}) queried an invoice amount."),
    "Technical support": ("How to use {product}", "{contact} needs help setting up {product}."),
}
TICKET_CATEGORY_WEIGHTS = {
    "Order query": 0.30,
    "Delivery": 0.20,
    "Product fault": 0.15,
    "Returns": 0.10,
    "Billing": 0.15,
    "Technical support": 0.10,
}
RETURN_REASONS = ("Changed mind", "Wrong item ordered", "Damaged in transit", "Not as described")
