"""Generate realistic restaurant customer data for Pat LaFrieda ERP testbed.

Creates 1,000 customers distributed across tiers (WHALE, ENTERPRISE,
STANDARD, SMALL) with NYC-metro geography, credit profiles, and
optional Cari enrollment.
"""

from datetime import date, timedelta

from generators.base import (
    rng,
    make_sequential_id,
    fake,
    random_phone,
    random_zip_for_borough,
    random_date_between,
    weighted_choice,
)
from config.lafrieda_profile import (
    CUSTOMER_TIERS,
    CUSTOMER_SEGMENTS,
    CUISINE_TYPES,
    CREDIT_TERMS,
    DELIVERY_ZONES,
    CARI_ENROLLMENT_RATE,
    CARI_WHALE_ENROLLMENT_RATE,
    CARI_REWARD_TIERS,
    TIER_DISCOUNT_RANGES,
)
from config.settings import NUM_CUSTOMERS
from database.models import Customer


# ── Helpers ───────────────────────────────────────────────────────────────────

_CUISINE_SUFFIXES = [
    "Grill", "Kitchen", "Bistro", "Trattoria", "Steakhouse",
    "Tavern", "Brasserie", "Eatery", "Table", "House",
    "Chophouse", "Bar & Grill", "Cantina", "Osteria", "Cafe",
]

_CITY_FOR_BOROUGH = {
    "MANHATTAN": "New York",
    "BROOKLYN": "New York",
    "QUEENS": "New York",
    "BRONX": "New York",
    "NJ": None,         # derived per zone
    "WESTCHESTER": None,
    "CT": None,
    "LI": None,
    "OTHER": None,
}

_NJ_CITIES = {
    "NJ_HOBOKEN": "Hoboken",
    "NJ_JERSEY_CITY": "Jersey City",
    "NJ_BERGEN": "Hackensack",
}

_STATE_FOR_BOROUGH = {
    "MANHATTAN": "NY",
    "BROOKLYN": "NY",
    "QUEENS": "NY",
    "BRONX": "NY",
    "NJ": "NJ",
    "WESTCHESTER": "NY",
    "CT": "CT",
    "LI": "NY",
    "OTHER": "NY",
}

_MISC_CITIES = {
    "WESTCHESTER": "White Plains",
    "CT": "Stamford",
    "LI": "Garden City",
    "OTHER": "Yonkers",
}

_CREDIT_TERMS_DAYS = {
    "NET15": 15,
    "NET30": 30,
    "NET45": 45,
    "COD": 0,
}


def _generate_business_name() -> str:
    """Create a realistic restaurant-style business name.

    ~50 % get a cuisine suffix appended to a fake company stem,
    ~50 % use a pure faker company name.
    """
    if rng.random() < 0.50:
        stem = fake.last_name()
        suffix = rng.choice(_CUISINE_SUFFIXES)
        return f"{stem}'s {suffix}"
    return fake.company()


def _pick_delivery_zone() -> str:
    """Choose a delivery zone weighted by its distribution percentage."""
    zones = list(DELIVERY_ZONES.keys())
    weights = [DELIVERY_ZONES[z]["pct"] for z in zones]
    return weighted_choice(zones, weights)


def _derive_city(zone: str, borough: str) -> str:
    """Return the city name for a given zone/borough combination."""
    # NYC boroughs
    city = _CITY_FOR_BOROUGH.get(borough)
    if city is not None:
        return city
    # NJ zones
    if borough == "NJ":
        return _NJ_CITIES.get(zone, "Newark")
    # Other regions
    return _MISC_CITIES.get(borough, "New York")


def _assign_credit(tier: str):
    """Return (credit_limit, credit_terms, credit_rating) for a tier."""
    if tier == "WHALE":
        limit = round(float(rng.integers(100_000, 500_001)), 2)
        terms = rng.choice(["NET30", "NET45"])
        rating = "A"
    elif tier == "ENTERPRISE":
        limit = round(float(rng.integers(50_000, 100_001)), 2)
        terms = "NET30"
        rating = rng.choice(["A", "B"])
    elif tier == "STANDARD":
        limit = round(float(rng.integers(10_000, 50_001)), 2)
        terms = "NET30"
        rating = rng.choice(["B", "C"])
    else:  # SMALL
        limit = round(float(rng.integers(2_000, 10_001)), 2)
        terms = rng.choice(["NET15", "NET30", "COD"])
        rating = rng.choice(["B", "C", "D"])
    return limit, str(terms), rating


def _determine_cari_reward_tier(annual_volume: float) -> str:
    """Map annual volume to the appropriate Cari reward tier."""
    # Walk tiers from highest threshold downward
    sorted_tiers = sorted(
        CARI_REWARD_TIERS.items(),
        key=lambda t: t[1]["min_annual"],
        reverse=True,
    )
    for tier_name, info in sorted_tiers:
        if annual_volume >= info["min_annual"]:
            return tier_name
    # Fallback (should not happen since 1_STAR starts at 0)
    return "1_STAR"


# ── Main generator ────────────────────────────────────────────────────────────

def generate_customers(session) -> list[Customer]:
    """Generate NUM_CUSTOMERS realistic restaurant customers.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session; generated Customer objects are added to
        the session but **not** committed (caller is responsible for that).

    Returns
    -------
    list[Customer]
        The full list of generated Customer ORM objects.
    """
    today = date.today()
    six_months_ago = today - timedelta(days=180)

    # ── Build the tier assignment list ────────────────────────────────
    tier_assignments: list[str] = []
    for tier_name, info in CUSTOMER_TIERS.items():
        count = int(round(info["pct"] * NUM_CUSTOMERS))
        tier_assignments.extend([tier_name] * count)

    # Pad or trim to exactly NUM_CUSTOMERS (handles rounding drift)
    while len(tier_assignments) < NUM_CUSTOMERS:
        tier_assignments.append("STANDARD")
    tier_assignments = tier_assignments[:NUM_CUSTOMERS]

    # Shuffle so tiers aren't grouped sequentially
    rng.shuffle(tier_assignments)

    # ── Customer type distribution ────────────────────────────────────
    customer_types = ["RESTAURANT", "HOTEL", "CATERING", "RETAIL"]
    customer_type_weights = [0.85, 0.05, 0.05, 0.05]

    # ── Account status distribution ───────────────────────────────────
    status_options = ["ACTIVE", "INACTIVE", "SUSPENDED"]
    status_weights = [0.95, 0.03, 0.02]

    customers: list[Customer] = []

    for idx in range(NUM_CUSTOMERS):
        n = idx + 1
        customer_id = make_sequential_id("CUST", n)
        tier = tier_assignments[idx]
        tier_info = CUSTOMER_TIERS[tier]

        # ── Basic info ────────────────────────────────────────────────
        business_name = _generate_business_name()
        owner_name = fake.name()
        contact_name = fake.name()
        contact_email = fake.email()
        contact_phone = random_phone()

        customer_type = weighted_choice(customer_types, customer_type_weights)
        cuisine_type = str(rng.choice(CUISINE_TYPES))
        segment = str(rng.choice(CUSTOMER_SEGMENTS))

        # ── Geography ─────────────────────────────────────────────────
        zone = _pick_delivery_zone()
        borough = DELIVERY_ZONES[zone]["borough"]
        city = _derive_city(zone, borough)
        state = _STATE_FOR_BOROUGH.get(borough, "NY")
        zip_code = random_zip_for_borough(borough)
        address_line1 = fake.street_address()

        # ── Credit ────────────────────────────────────────────────────
        credit_limit, credit_terms, credit_rating = _assign_credit(tier)
        credit_terms_days = _CREDIT_TERMS_DAYS.get(credit_terms, 30)

        # ── Annual volume ─────────────────────────────────────────────
        annual_volume_estimate = round(
            float(rng.integers(tier_info["annual_min"], tier_info["annual_max"] + 1)),
            2,
        )

        # ── Cari enrollment ───────────────────────────────────────────
        enrollment_rate = (
            CARI_WHALE_ENROLLMENT_RATE if tier == "WHALE"
            else CARI_ENROLLMENT_RATE
        )
        cari_enrolled = bool(rng.random() < enrollment_rate)
        cari_enrollment_date = None
        cari_reward_tier = None
        cari_points_balance = 0

        if cari_enrolled:
            cari_enrollment_date = random_date_between(six_months_ago, today)
            cari_reward_tier = _determine_cari_reward_tier(annual_volume_estimate)
            cari_points_balance = int(rng.integers(0, 5001))

        # ── First order date ──────────────────────────────────────────
        if tier == "SMALL":
            # Newer accounts: 1-12 months ago
            earliest = today - timedelta(days=365)
            latest = today - timedelta(days=30)
        else:
            # Established accounts: 6-24 months ago
            earliest = today - timedelta(days=730)
            latest = today - timedelta(days=180)
        first_order_date = random_date_between(earliest, latest)

        # ── Account status ────────────────────────────────────────────
        account_status = weighted_choice(status_options, status_weights)

        # ── Number of locations ───────────────────────────────────────
        if tier == "WHALE":
            num_locations = int(rng.integers(2, 15))
        elif tier == "ENTERPRISE":
            num_locations = int(rng.integers(1, 6))
        else:
            num_locations = 1

        # ── Assemble the Customer ORM object ──────────────────────────
        customer = Customer(
            customer_id=customer_id,
            business_name=business_name,
            dba_name=business_name if rng.random() < 0.15 else None,
            customer_type=customer_type,
            cuisine_type=cuisine_type,
            segment=segment,
            tier=tier,
            annual_volume_estimate=annual_volume_estimate,
            account_status=account_status,
            address_line1=address_line1,
            address_line2=None,
            city=city,
            state=state,
            zip_code=zip_code,
            borough=borough,
            delivery_zone=zone,
            latitude=None,
            longitude=None,
            num_locations=num_locations,
            owner_name=owner_name,
            primary_contact_name=contact_name,
            primary_contact_email=contact_email,
            primary_contact_phone=contact_phone,
            credit_limit=credit_limit,
            credit_terms=credit_terms,
            credit_terms_days=credit_terms_days,
            credit_rating=credit_rating,
            tax_exempt=bool(rng.random() < 0.05),
            tax_id=fake.bothify("##-#######") if rng.random() < 0.80 else None,
            cari_enrolled=cari_enrolled,
            cari_enrollment_date=cari_enrollment_date,
            cari_reward_tier=cari_reward_tier,
            cari_points_balance=cari_points_balance,
            first_order_date=first_order_date,
            last_order_date=None,
            total_lifetime_orders=0,
            total_lifetime_revenue=0.0,
            avg_order_value=None,
            order_frequency_days=None,
        )

        session.add(customer)
        customers.append(customer)

    return customers
