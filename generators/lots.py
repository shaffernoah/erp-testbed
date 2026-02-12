"""Generate ~5,000 realistic lot/batch records for Pat LaFrieda ERP testbed.

Each lot ties to a product (sku_id) and supplier (supplier_id), with
receive dates, expiration tracking, aging metadata for dry-aged items,
USDA grade stamps, and storage location assignments.
"""

from datetime import date, timedelta

from generators.base import (
    rng,
    make_sequential_id,
    random_date_between,
    weighted_choice,
    to_json,
    jitter,
)
from config.lafrieda_profile import STORAGE_LOCATIONS, AGING_TYPES
from config.settings import TARGET_LOTS
from database.models import Lot


# ---------------------------------------------------------------------------
# Storage location assignment helpers
# ---------------------------------------------------------------------------

# Categorised storage locations from the profile
_COOLER_LOCATIONS = [loc for loc in STORAGE_LOCATIONS if "COOLER" in loc]
_AGING_LOCATIONS = [loc for loc in STORAGE_LOCATIONS if "AGING" in loc]
_FREEZER_LOCATIONS = [loc for loc in STORAGE_LOCATIONS if "FREEZER" in loc]


def _pick_storage_location(product) -> str:
    """Select an appropriate storage location based on product attributes.

    - DRY aging_type  -> aging room
    - requires_freezing -> freezer
    - everything else  -> cooler
    """
    if getattr(product, "aging_type", None) == "DRY":
        return str(rng.choice(_AGING_LOCATIONS))
    if getattr(product, "requires_freezing", False):
        return str(rng.choice(_FREEZER_LOCATIONS))
    return str(rng.choice(_COOLER_LOCATIONS))


def _storage_temp_for_location(location: str) -> float:
    """Return a realistic temperature reading for the given storage area."""
    if "AGING" in location:
        return round(float(rng.uniform(34.0, 36.0)), 1)
    if "FREEZER" in location:
        return round(float(rng.uniform(-5.0, 0.0)), 1)
    if "STAGING" in location:
        return round(float(rng.uniform(35.0, 42.0)), 1)
    # Default: cooler
    return round(float(rng.uniform(33.0, 38.0)), 1)


# ---------------------------------------------------------------------------
# Quantity helpers
# ---------------------------------------------------------------------------

# Initial quantity ranges (lbs) by product category
_QTY_RANGES = {
    "BEEF":        (2_000, 20_000),
    "PORK":        (1_000, 10_000),
    "POULTRY":     (1_000, 8_000),
    "LAMB_VEAL":   (500, 5_000),
    "BLEND":       (2_000, 15_000),  # burger blends are high-volume
    "CHARCUTERIE": (500, 3_000),
}

# Subcategory overrides for ground beef (higher volume)
_SUBCAT_QTY_OVERRIDES = {
    "GROUND": (5_000, 20_000),
}


def _initial_quantity(product) -> float:
    """Determine initial lot quantity in lbs based on product category/subcategory."""
    subcat = getattr(product, "subcategory", None)
    if subcat in _SUBCAT_QTY_OVERRIDES:
        low, high = _SUBCAT_QTY_OVERRIDES[subcat]
    else:
        cat = getattr(product, "category", "BEEF")
        low, high = _QTY_RANGES.get(cat, (500, 10_000))
    return round(float(rng.integers(low, high + 1)), 2)


# ---------------------------------------------------------------------------
# Hold / inspection failure helpers
# ---------------------------------------------------------------------------

_HOLD_REASONS = [
    "Temperature deviation during transit",
    "Mislabelled grade stamp",
    "Pending USDA re-inspection",
    "Customer complaint investigation",
    "Packaging damage on receipt",
    "Supplier quality audit pending",
]

_INSPECTION_FAIL_NOTES = [
    "Temperature above threshold at receiving",
    "Off-colour detected on surface",
    "Incorrect USDA grade stamp",
    "Weight discrepancy > tolerance",
    "Foreign material found in packaging",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_lots(session, products, suppliers) -> list[Lot]:
    """Create ~5,000 Lot ORM objects and add them to the session.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session.
    products : list[Product]
        Previously generated Product instances.
    suppliers : list[Supplier]
        Previously generated Supplier instances.

    Returns
    -------
    list[Lot]
        The generated Lot ORM objects.
    """
    today = date.today()
    one_year_ago = today - timedelta(days=365)

    # Pre-compute product and supplier index arrays for fast random selection
    num_products = len(products)
    num_suppliers = len(suppliers)

    # Status distribution: AVAILABLE 70%, DEPLETED 20%, EXPIRED 5%, HOLD 5%
    status_options = ["AVAILABLE", "DEPLETED", "EXPIRED", "HOLD"]
    status_weights = [0.70, 0.20, 0.05, 0.05]

    lots: list[Lot] = []

    for i in range(TARGET_LOTS):
        n = i + 1
        lot_id = make_sequential_id("LOT", n)

        # Lot number: LOT-2025-{letter}{4-digit seq}
        letter = chr(65 + n // 1000)           # A, B, C, D, E
        seq_part = str(n % 1000).zfill(4)
        lot_number = f"LOT-2025-{letter}{seq_part}"

        # Pick a random product and supplier
        prod_idx = int(rng.integers(0, num_products))
        supp_idx = int(rng.integers(0, num_suppliers))
        product = products[prod_idx]
        supplier = suppliers[supp_idx]

        # --- Dates ---
        received_date = random_date_between(one_year_ago, today)
        shelf_life = getattr(product, "shelf_life_days", 14)
        expiration_date = received_date + timedelta(days=shelf_life)
        sell_by_date = expiration_date - timedelta(days=max(1, shelf_life // 5))
        production_date = received_date - timedelta(
            days=int(rng.integers(1, 4))  # 1-3 days before receipt
        )

        # --- Quantities ---
        initial_qty = _initial_quantity(product)

        # Status
        status = weighted_choice(status_options, status_weights)

        # Current quantity depends on status
        if status == "DEPLETED":
            current_qty = 0.0
        elif status == "EXPIRED":
            # Expired lots may still have some remaining product
            current_qty = round(float(rng.uniform(0, initial_qty * 0.3)), 2)
        elif status == "HOLD":
            current_qty = round(float(rng.uniform(initial_qty * 0.5, initial_qty)), 2)
        else:
            # AVAILABLE — partially consumed
            current_qty = round(float(rng.uniform(initial_qty * 0.1, initial_qty)), 2)

        # --- Storage ---
        storage_location = _pick_storage_location(product)
        storage_temp = _storage_temp_for_location(storage_location)

        # --- USDA grade (from the product) ---
        usda_grade = getattr(product, "usda_grade", "N/A")
        grade_stamp_id = f"GS-{rng.integers(10000, 99999)}" if usda_grade not in ("N/A", None) else None

        # --- Country of origin ---
        supplier_country = getattr(supplier, "country", "US")
        country_of_origin = supplier_country if supplier_country else "US"

        # --- Aging fields (only for DRY aging products) ---
        aging_type = getattr(product, "aging_type", "FRESH")
        aging_start_date = None
        aging_target_days = None
        aging_actual_days = None

        if aging_type == "DRY":
            aging_start_date = received_date
            aging_days_min = getattr(product, "aging_days_min", 28) or 28
            aging_days_max = getattr(product, "aging_days_max", 60) or 60
            aging_target_days = int(rng.integers(aging_days_min, aging_days_max + 1))
            # Actual aging: within a few days of target
            days_since_received = (today - received_date).days
            aging_actual_days = min(days_since_received, aging_target_days + int(rng.integers(-3, 4)))
            aging_actual_days = max(0, aging_actual_days)

        # --- Inspection / hold logic ---
        # ~5% have inspection failures or hold reasons
        is_problem_lot = rng.random() < 0.05

        if is_problem_lot:
            inspection_status = "FAILED"
            inspection_notes = str(rng.choice(_INSPECTION_FAIL_NOTES))
            # Force status to HOLD for failed inspections if not already depleted
            if status not in ("DEPLETED",):
                status = "HOLD"
                hold_reason = str(rng.choice(_HOLD_REASONS))
            else:
                hold_reason = None
        elif status == "HOLD":
            inspection_status = "PASSED"
            hold_reason = str(rng.choice(_HOLD_REASONS))
            inspection_notes = None
        else:
            inspection_status = "PASSED"
            hold_reason = None
            inspection_notes = None

        inspection_date = received_date  # inspected on receipt

        # --- Units received (approximate integer count) ---
        nominal_weight = getattr(product, "nominal_weight", 10.0) or 10.0
        units_received = max(1, int(round(initial_qty / nominal_weight)))

        # --- Farm source from supplier name ---
        farm_source = getattr(supplier, "name", None)

        # --- Build the Lot ORM object ---
        lot = Lot(
            lot_id=lot_id,
            lot_number=lot_number,
            sku_id=product.sku_id,
            supplier_id=supplier.supplier_id,
            production_date=production_date,
            received_date=received_date,
            expiration_date=expiration_date,
            sell_by_date=sell_by_date,
            initial_quantity_lbs=initial_qty,
            current_quantity_lbs=current_qty,
            units_received=units_received,
            usda_grade=usda_grade,
            grade_stamp_id=grade_stamp_id,
            country_of_origin=country_of_origin,
            farm_source=farm_source,
            storage_location=storage_location,
            storage_temp_f=storage_temp,
            aging_start_date=aging_start_date,
            aging_target_days=aging_target_days,
            aging_actual_days=aging_actual_days,
            status=status,
            hold_reason=hold_reason,
            inspection_status=inspection_status,
            inspection_date=inspection_date,
            inspection_notes=inspection_notes,
        )

        session.add(lot)
        lots.append(lot)

    return lots
