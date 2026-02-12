"""Generate realistic supplier data for Pat LaFrieda meat distribution.

Creates ~20 farm, ranch, packer, and importer suppliers with
realistic names, regions, certifications, and quality metrics.
"""

from datetime import date, timedelta

from generators.base import rng, make_sequential_id, to_json, fake, random_date_between
from config.lafrieda_profile import SUPPLIER_REGIONS, SUPPLIER_TYPES
from config.settings import NUM_SUPPLIERS
from database.models import Supplier


# ---------------------------------------------------------------------------
# Realistic supplier name pools
# ---------------------------------------------------------------------------

# Well-known real-world-style ranch/farm/packer names for the meat industry
_PRESET_NAMES = [
    "Creekstone Farms",
    "Snake River Farms",
    "Brandt Beef",
    "Double R Ranch",
    "Niman Ranch",
    "Strauss Meats",
    "Lone Mountain Wagyu",
    "Mishima Reserve",
    "Morgan Ranch",
    "Painted Hills Natural Beef",
    "Flannery Beef",
    "DeBragga & Spitler",
    "Meats by Linz",
]

# Fragments for generating additional plausible names with Faker
_NAME_PREFIXES = [
    "Golden", "Prairie", "Heritage", "Summit", "Iron Ridge",
    "Cedar Creek", "Tallgrass", "Blue Valley", "Stonewall", "High Plains",
]

_NAME_SUFFIXES = [
    "Ranch", "Farms", "Beef Co.", "Meats", "Cattle Co.",
    "Provisions", "Livestock", "Packers",
]

# Region-to-state/country mapping for realistic addresses
_REGION_LOCATIONS = {
    "MIDWEST": [
        ("Omaha", "NE", "US"),
        ("Kansas City", "KS", "US"),
        ("Des Moines", "IA", "US"),
        ("Sioux Falls", "SD", "US"),
        ("Dodge City", "KS", "US"),
        ("Lincoln", "NE", "US"),
        ("Springfield", "IL", "US"),
        ("Columbus", "OH", "US"),
    ],
    "NORTHEAST": [
        ("Lancaster", "PA", "US"),
        ("Harrisburg", "PA", "US"),
        ("Burlington", "VT", "US"),
        ("Albany", "NY", "US"),
    ],
    "SOUTHEAST": [
        ("Augusta", "GA", "US"),
        ("Lexington", "KY", "US"),
    ],
    "WEST": [
        ("Boise", "ID", "US"),
        ("Twin Falls", "ID", "US"),
        ("Greeley", "CO", "US"),
    ],
    "INTERNATIONAL": [
        ("Kobe", "Hyogo", "JP"),
        ("Melbourne", "VIC", "AU"),
    ],
}

# Product mixes by supplier type
_PRODUCTS_BY_TYPE = {
    "RANCH":    [["BEEF"], ["BEEF", "VEAL"], ["BEEF", "LAMB"]],
    "PACKER":   [["BEEF", "PORK"], ["BEEF", "PORK", "VEAL"], ["BEEF"]],
    "IMPORTER": [["BEEF", "WAGYU"], ["BEEF", "LAMB", "VEAL"], ["CHARCUTERIE", "BEEF"]],
    "CO_OP":    [["BEEF", "PORK", "POULTRY"], ["BEEF", "PORK", "LAMB"]],
}

# Breed pools by supplier type
_BREEDS_BY_TYPE = {
    "RANCH":    [["Angus"], ["Angus", "Hereford"], ["Angus", "Wagyu-Cross"]],
    "PACKER":   [["Angus", "Hereford", "Charolais"], ["Mixed"]],
    "IMPORTER": [["Japanese Black", "Australian Wagyu"], ["Merino", "Dorper"]],
    "CO_OP":    [["Angus", "Hereford"], ["Mixed"]],
}


def _generate_supplier_name(index: int) -> str:
    """Return a supplier name — preset names first, then generated ones."""
    if index < len(_PRESET_NAMES):
        return _PRESET_NAMES[index]
    prefix = rng.choice(_NAME_PREFIXES)
    suffix = rng.choice(_NAME_SUFFIXES)
    return f"{prefix} {suffix}"


def generate_suppliers(session) -> list[Supplier]:
    """Create NUM_SUPPLIERS Supplier ORM objects and add them to the session.

    Distribution:
        RANCH       50%
        PACKER      25%
        IMPORTER    15%
        CO_OP       10%

    Region distribution:
        MIDWEST         50%
        NORTHEAST       20%
        SOUTHEAST       10%
        WEST            15%
        INTERNATIONAL    5%

    Returns the list of Supplier instances.
    """
    # --- Weighted type distribution ---
    type_weights = {"RANCH": 0.50, "PACKER": 0.25, "IMPORTER": 0.15, "CO_OP": 0.10}
    type_options = list(type_weights.keys())
    type_probs = [type_weights[t] for t in type_options]

    # --- Weighted region distribution ---
    region_weights = {
        "MIDWEST": 0.50,
        "NORTHEAST": 0.20,
        "SOUTHEAST": 0.10,
        "WEST": 0.15,
        "INTERNATIONAL": 0.05,
    }
    region_options = list(region_weights.keys())
    region_probs = [region_weights[r] for r in region_options]

    # Pre-assign types and regions for all suppliers at once (vectorised)
    types_arr = rng.choice(type_options, size=NUM_SUPPLIERS, p=type_probs)
    regions_arr = rng.choice(region_options, size=NUM_SUPPLIERS, p=region_probs)

    # Choose which indices are preferred (pick 5 randomly)
    preferred_indices = set(rng.choice(NUM_SUPPLIERS, size=5, replace=False))

    # Reference dates for audit window (last 12 months)
    today = date.today()
    one_year_ago = today - timedelta(days=365)

    # Contract end dates: 6-24 months from now
    contract_start = today + timedelta(days=180)
    contract_end = today + timedelta(days=730)

    suppliers: list[Supplier] = []

    for i in range(NUM_SUPPLIERS):
        n = i + 1
        supplier_id = make_sequential_id("SUPP", n, 3)
        name = _generate_supplier_name(i)

        supplier_type = str(types_arr[i])
        region = str(regions_arr[i])

        # Pick a realistic city/state/country for the region
        location_pool = _REGION_LOCATIONS.get(region, _REGION_LOCATIONS["MIDWEST"])
        loc_idx = int(rng.integers(0, len(location_pool)))
        city, state, country = location_pool[loc_idx]

        # Primary products
        product_pool = _PRODUCTS_BY_TYPE.get(supplier_type, [["BEEF"]])
        products = list(product_pool[int(rng.integers(0, len(product_pool)))])

        # Breeds available
        breed_pool = _BREEDS_BY_TYPE.get(supplier_type, [["Angus"]])
        breeds = list(breed_pool[int(rng.integers(0, len(breed_pool)))])

        # Certifications — premium / preferred suppliers get more certs
        is_preferred = i in preferred_indices
        if is_preferred:
            certifications = ["USDA", "ORGANIC", "GAP_CERTIFIED"]
        elif rng.random() < 0.30:
            certifications = ["USDA", "ORGANIC"]
        else:
            certifications = ["USDA"]

        # USDA grades available
        if is_preferred or rng.random() < 0.35:
            usda_grades = ["PRIME", "CHOICE"]
        else:
            usda_grades = ["CHOICE", "SELECT"]

        # If importer with wagyu products, add WAGYU grade
        if supplier_type == "IMPORTER" and "WAGYU" in products:
            if "PRIME" not in usda_grades:
                usda_grades = ["PRIME", "CHOICE"]
            usda_grades.append("WAGYU")

        # Quality metrics
        if is_preferred:
            quality_rating = round(float(rng.uniform(4.5, 5.0)), 2)
            delivery_reliability_pct = round(float(rng.uniform(95.0, 99.0)), 1)
            audit_score = round(float(rng.uniform(92.0, 100.0)), 1)
        else:
            quality_rating = round(float(rng.uniform(3.5, 4.8)), 2)
            delivery_reliability_pct = round(float(rng.uniform(85.0, 97.0)), 1)
            audit_score = round(float(rng.uniform(80.0, 98.0)), 1)

        avg_lead_time_days = int(rng.integers(3, 11))  # 3-10 days
        min_order_lbs = float(int(rng.integers(1, 11)) * 500)  # 500-5000 in 500-lb steps

        # Payment terms — mostly NET30
        payment_terms = "NET15" if rng.random() < 0.20 else "NET30"

        # Audit date within last 12 months
        last_audit_date = random_date_between(one_year_ago, today)

        # Contract end date
        contract_end_date = random_date_between(contract_start, contract_end)

        supplier = Supplier(
            supplier_id=supplier_id,
            name=name,
            supplier_type=supplier_type,
            city=city,
            state=state,
            country=country,
            region=region,
            primary_products=to_json(products),
            certifications=to_json(certifications),
            usda_grades_available=to_json(usda_grades),
            breeds_available=to_json(breeds),
            quality_rating=quality_rating,
            delivery_reliability_pct=delivery_reliability_pct,
            avg_lead_time_days=avg_lead_time_days,
            min_order_lbs=min_order_lbs,
            payment_terms=payment_terms,
            is_preferred=is_preferred,
            contract_end_date=contract_end_date,
            lot_tracking_capable=True,
            haccp_compliant=True,
            last_audit_date=last_audit_date,
            audit_score=audit_score,
            is_active=True,
        )

        session.add(supplier)
        suppliers.append(supplier)

    return suppliers
