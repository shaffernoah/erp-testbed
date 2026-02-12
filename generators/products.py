"""Generate ~300 realistic meat product SKUs for Pat LaFrieda Meat Purveyors.

Each product gets a deterministic SKU, pricing from the archetype tables,
catch-weight metadata, aging and storage attributes, and allergen info.
"""

from generators.base import rng, make_sequential_id, to_json, jitter
from config.lafrieda_profile import (
    CATEGORIES,
    USDA_GRADES,
    PRODUCT_ARCHETYPES,
    BEEF_STEAK_NAMES,
    BEEF_ROAST_NAMES,
    BEEF_GROUND_NAMES,
    BEEF_SHORT_RIB_NAMES,
    BEEF_BRISKET_NAMES,
    PORK_NAMES,
    POULTRY_NAMES,
    LAMB_VEAL_NAMES,
    BLEND_NAMES,
    CHARCUTERIE_NAMES,
)
from database.models import Product

# Total target product count
TARGET_COUNT = 300

# Grades to apply to most beef steaks/roasts/short ribs/brisket
STANDARD_GRADES = ["PRIME", "CHOICE", "SELECT"]

# Premium cuts that also get a WAGYU variant
WAGYU_ELIGIBLE_STEAKS = [
    "Bone-In Ribeye", "Boneless Ribeye", "NY Strip", "Filet Mignon",
    "Tomahawk Ribeye",
]


def _sku(category: str, subcategory: str, grade: str, seq: int) -> str:
    """Build a PLF-prefixed SKU string.

    Format: PLF-{CAT[:4]}-{SUBCAT[:4]}-{GRADE[:3]}-{seq:03d}
    """
    cat_part = category[:4].upper()
    sub_part = subcategory[:4].upper()
    grd_part = grade[:3].upper()
    return f"PLF-{cat_part}-{sub_part}-{grd_part}-{str(seq).zfill(3)}"


def _archetype(category: str, subcategory: str, grade: str) -> dict:
    """Look up archetype pricing/weight data, falling back to 'default' grade."""
    key = (category, subcategory)
    bucket = PRODUCT_ARCHETYPES.get(key, {})
    return bucket.get(grade, bucket.get("default", {
        "weight": 10.0, "cost": 5.0, "list": 10.0, "shelf": 14,
    }))


def _aging_attrs(category: str, subcategory: str) -> dict:
    """Return aging_type, aging_days_min, aging_days_max for a product."""
    if category == "BEEF" and subcategory == "STEAK":
        # Steaks: randomly assign DRY, WET, or FRESH
        choice = rng.choice(["DRY", "WET", "FRESH"])
        if choice == "DRY":
            return {"aging_type": "DRY", "aging_days_min": 28, "aging_days_max": 60}
        elif choice == "WET":
            return {"aging_type": "WET", "aging_days_min": 14, "aging_days_max": 28}
        else:
            return {"aging_type": "FRESH", "aging_days_min": None, "aging_days_max": None}
    elif category == "BEEF" and subcategory in ("ROAST", "SHORT_RIB", "BRISKET"):
        choice = rng.choice(["WET", "FRESH"])
        if choice == "WET":
            return {"aging_type": "WET", "aging_days_min": 14, "aging_days_max": 28}
        return {"aging_type": "FRESH", "aging_days_min": None, "aging_days_max": None}
    return {"aging_type": "FRESH", "aging_days_min": None, "aging_days_max": None}


def _storage_temps(category: str, subcategory: str) -> dict:
    """Return storage temp range (Fahrenheit) and requires_freezing flag."""
    # Frozen items: some sausage packs and certain charcuterie
    if subcategory == "SAUSAGE" and rng.random() < 0.3:
        return {"storage_temp_min_f": -5.0, "storage_temp_max_f": 0.0, "requires_freezing": True}
    if category == "CHARCUTERIE":
        return {"storage_temp_min_f": 33.0, "storage_temp_max_f": 38.0, "requires_freezing": False}
    # Default: cooler temps
    return {"storage_temp_min_f": 33.0, "storage_temp_max_f": 38.0, "requires_freezing": False}


def _allergens(category: str, subcategory: str) -> list:
    """Return allergen list. Sausages may contain SOY and WHEAT."""
    if subcategory == "SAUSAGE":
        return ["SOY", "WHEAT"]
    if subcategory in ("BACON", "PROSCIUTTO"):
        # Some charcuterie may have trace allergens
        if rng.random() < 0.2:
            return ["SOY"]
    return []


def _uom_and_catch(category: str, subcategory: str, name: str) -> dict:
    """Determine base_uom, is_catch_weight, and related fields."""
    # Whole birds sold by EACH
    if subcategory == "WHOLE" or name in ("Whole Duck", "Cornish Game Hen"):
        return {"base_uom": "EACH", "is_catch_weight": True, "catch_weight_uom": "LB"}
    # Some sausage packs sold by CASE
    if subcategory == "SAUSAGE":
        return {"base_uom": "CASE", "is_catch_weight": False, "catch_weight_uom": None}
    # Default: LB, catch-weight
    return {"base_uom": "LB", "is_catch_weight": True, "catch_weight_uom": "LB"}


# ---------------------------------------------------------------------------
# Beef product builders
# ---------------------------------------------------------------------------

def _generate_beef_steaks(seq: int) -> tuple[list[dict], int]:
    """Generate all beef steak products across grades. Returns (rows, next_seq)."""
    rows = []
    for name in BEEF_STEAK_NAMES:
        grades = list(STANDARD_GRADES)
        if name in WAGYU_ELIGIBLE_STEAKS:
            grades.append("WAGYU")
        for grade in grades:
            arch = _archetype("BEEF", "STEAK", grade)
            aging = _aging_attrs("BEEF", "STEAK")
            storage = _storage_temps("BEEF", "STEAK")
            allergens = _allergens("BEEF", "STEAK")
            uom = _uom_and_catch("BEEF", "STEAK", name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("BEEF", "STEAK", grade, seq),
                "name": f"{name} ({grade})",
                "short_description": f"{grade} grade {name.lower()}, Pat LaFrieda",
                "category": "BEEF",
                "subcategory": "STEAK",
                "usda_grade": grade,
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                **aging,
                **storage,
                "allergens": to_json(allergens),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


def _generate_beef_roasts(seq: int) -> tuple[list[dict], int]:
    rows = []
    for name in BEEF_ROAST_NAMES:
        for grade in ["PRIME", "CHOICE"]:
            arch = _archetype("BEEF", "ROAST", grade)
            aging = _aging_attrs("BEEF", "ROAST")
            storage = _storage_temps("BEEF", "ROAST")
            uom = _uom_and_catch("BEEF", "ROAST", name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("BEEF", "ROAST", grade, seq),
                "name": f"{name} ({grade})",
                "short_description": f"{grade} {name.lower()}",
                "category": "BEEF",
                "subcategory": "ROAST",
                "usda_grade": grade,
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                **aging,
                **storage,
                "allergens": to_json([]),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


def _generate_beef_ground(seq: int) -> tuple[list[dict], int]:
    rows = []
    for name in BEEF_GROUND_NAMES:
        arch = _archetype("BEEF", "GROUND", "default")
        storage = _storage_temps("BEEF", "GROUND")
        uom = _uom_and_catch("BEEF", "GROUND", name)

        cost = jitter(arch["cost"], 0.05)
        list_price = jitter(arch["list"], 0.05)
        margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

        rows.append({
            "sku_id": _sku("BEEF", "GROU", "DEF", seq),
            "name": name,
            "short_description": name.lower(),
            "category": "BEEF",
            "subcategory": "GROUND",
            "usda_grade": "N/A",
            "primal_cut": None,
            "nominal_weight": arch["weight"],
            "cost_per_lb": cost,
            "list_price_per_lb": list_price,
            "target_margin_pct": margin,
            "shelf_life_days": arch["shelf"],
            "aging_type": "FRESH",
            "aging_days_min": None,
            "aging_days_max": None,
            **storage,
            "allergens": to_json([]),
            **uom,
            "weight_tolerance_pct": 0.10,
        })
        seq += 1
    return rows, seq


def _generate_beef_short_ribs(seq: int) -> tuple[list[dict], int]:
    rows = []
    for name in BEEF_SHORT_RIB_NAMES:
        for grade in ["PRIME", "CHOICE"]:
            arch = _archetype("BEEF", "SHORT_RIB", grade)
            aging = _aging_attrs("BEEF", "SHORT_RIB")
            storage = _storage_temps("BEEF", "SHORT_RIB")
            uom = _uom_and_catch("BEEF", "SHORT_RIB", name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("BEEF", "SHOR", grade, seq),
                "name": f"{name} ({grade})",
                "short_description": f"{grade} {name.lower()}",
                "category": "BEEF",
                "subcategory": "SHORT_RIB",
                "usda_grade": grade,
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                **aging,
                **storage,
                "allergens": to_json([]),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


def _generate_beef_brisket(seq: int) -> tuple[list[dict], int]:
    rows = []
    for name in BEEF_BRISKET_NAMES:
        for grade in ["PRIME", "CHOICE"]:
            arch = _archetype("BEEF", "BRISKET", grade)
            aging = _aging_attrs("BEEF", "BRISKET")
            storage = _storage_temps("BEEF", "BRISKET")
            uom = _uom_and_catch("BEEF", "BRISKET", name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("BEEF", "BRIS", grade, seq),
                "name": f"{name} ({grade})",
                "short_description": f"{grade} {name.lower()}",
                "category": "BEEF",
                "subcategory": "BRISKET",
                "usda_grade": grade,
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                **aging,
                **storage,
                "allergens": to_json([]),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


# ---------------------------------------------------------------------------
# Non-beef product builders
# ---------------------------------------------------------------------------

def _generate_pork(seq: int) -> tuple[list[dict], int]:
    rows = []
    for subcat, names in PORK_NAMES.items():
        for name in names:
            arch = _archetype("PORK", subcat, "default")
            storage = _storage_temps("PORK", subcat)
            allergens = _allergens("PORK", subcat)
            uom = _uom_and_catch("PORK", subcat, name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("PORK", subcat, "DEF", seq),
                "name": name,
                "short_description": name.lower(),
                "category": "PORK",
                "subcategory": subcat,
                "usda_grade": "N/A",
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                "aging_type": "FRESH",
                "aging_days_min": None,
                "aging_days_max": None,
                **storage,
                "allergens": to_json(allergens),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


def _generate_poultry(seq: int) -> tuple[list[dict], int]:
    rows = []
    for subcat, names in POULTRY_NAMES.items():
        for name in names:
            arch = _archetype("POULTRY", subcat, "default")
            storage = _storage_temps("POULTRY", subcat)
            uom = _uom_and_catch("POULTRY", subcat, name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("POUL", subcat, "DEF", seq),
                "name": name,
                "short_description": name.lower(),
                "category": "POULTRY",
                "subcategory": subcat,
                "usda_grade": "N/A",
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                "aging_type": "FRESH",
                "aging_days_min": None,
                "aging_days_max": None,
                **storage,
                "allergens": to_json([]),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


def _generate_lamb_veal(seq: int) -> tuple[list[dict], int]:
    rows = []
    for subcat, names in LAMB_VEAL_NAMES.items():
        for name in names:
            arch = _archetype("LAMB_VEAL", subcat, "default")
            storage = _storage_temps("LAMB_VEAL", subcat)
            uom = _uom_and_catch("LAMB_VEAL", subcat, name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("LAMB", subcat, "DEF", seq),
                "name": name,
                "short_description": name.lower(),
                "category": "LAMB_VEAL",
                "subcategory": subcat,
                "usda_grade": "N/A",
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                "aging_type": "FRESH",
                "aging_days_min": None,
                "aging_days_max": None,
                **storage,
                "allergens": to_json([]),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


def _generate_blends(seq: int) -> tuple[list[dict], int]:
    rows = []
    for name in BLEND_NAMES:
        arch = _archetype("BLEND", "BURGER", "default")
        storage = _storage_temps("BLEND", "BURGER")
        uom = _uom_and_catch("BLEND", "BURGER", name)

        cost = jitter(arch["cost"], 0.05)
        list_price = jitter(arch["list"], 0.05)
        margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

        rows.append({
            "sku_id": _sku("BLEN", "BURG", "DEF", seq),
            "name": name,
            "short_description": name.lower(),
            "category": "BLEND",
            "subcategory": "BURGER",
            "usda_grade": "N/A",
            "primal_cut": None,
            "nominal_weight": arch["weight"],
            "cost_per_lb": cost,
            "list_price_per_lb": list_price,
            "target_margin_pct": margin,
            "shelf_life_days": arch["shelf"],
            "aging_type": "FRESH",
            "aging_days_min": None,
            "aging_days_max": None,
            **storage,
            "allergens": to_json([]),
            **uom,
            "weight_tolerance_pct": 0.10,
        })
        seq += 1
    return rows, seq


def _generate_charcuterie(seq: int) -> tuple[list[dict], int]:
    rows = []
    for subcat, names in CHARCUTERIE_NAMES.items():
        for name in names:
            arch = _archetype("CHARCUTERIE", subcat, "default")
            storage = _storage_temps("CHARCUTERIE", subcat)
            allergens = _allergens("CHARCUTERIE", subcat)
            uom = _uom_and_catch("CHARCUTERIE", subcat, name)

            cost = jitter(arch["cost"], 0.05)
            list_price = jitter(arch["list"], 0.05)
            margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

            rows.append({
                "sku_id": _sku("CHAR", subcat, "DEF", seq),
                "name": name,
                "short_description": name.lower(),
                "category": "CHARCUTERIE",
                "subcategory": subcat,
                "usda_grade": "N/A",
                "primal_cut": None,
                "nominal_weight": arch["weight"],
                "cost_per_lb": cost,
                "list_price_per_lb": list_price,
                "target_margin_pct": margin,
                "shelf_life_days": arch["shelf"],
                "aging_type": "FRESH",
                "aging_days_min": None,
                "aging_days_max": None,
                **storage,
                "allergens": to_json(allergens),
                **uom,
                "weight_tolerance_pct": 0.10,
            })
            seq += 1
    return rows, seq


# ---------------------------------------------------------------------------
# Padding to hit ~300 products
# ---------------------------------------------------------------------------

def _pad_to_target(existing: list[dict], seq: int) -> tuple[list[dict], int]:
    """If we have fewer than TARGET_COUNT products, duplicate popular beef
    steaks with slight price variants to fill the gap.  This is realistic:
    LaFrieda lists the same cut at different pack sizes / trim levels.
    """
    extra = []
    deficit = TARGET_COUNT - len(existing)
    if deficit <= 0:
        return extra, seq

    # Cycle through steak names and grades to create variants
    variant_idx = 0
    steak_grades = list(STANDARD_GRADES)
    while len(extra) < deficit:
        name = BEEF_STEAK_NAMES[variant_idx % len(BEEF_STEAK_NAMES)]
        grade = steak_grades[variant_idx % len(steak_grades)]
        arch = _archetype("BEEF", "STEAK", grade)
        aging = _aging_attrs("BEEF", "STEAK")
        storage = _storage_temps("BEEF", "STEAK")
        uom = _uom_and_catch("BEEF", "STEAK", name)

        # Different pack weight to distinguish from original
        weight = round(arch["weight"] * rng.choice([0.5, 0.75, 1.5, 2.0]), 1)
        cost = jitter(arch["cost"], 0.05)
        list_price = jitter(arch["list"], 0.05)
        margin = round((list_price - cost) / list_price, 4) if list_price else 0.0

        pack_label = f"{weight:.0f}lb Pack"

        extra.append({
            "sku_id": _sku("BEEF", "STEA", grade, seq),
            "name": f"{name} ({grade}) - {pack_label}",
            "short_description": f"{grade} {name.lower()}, {pack_label}",
            "category": "BEEF",
            "subcategory": "STEAK",
            "usda_grade": grade,
            "primal_cut": None,
            "nominal_weight": weight,
            "cost_per_lb": cost,
            "list_price_per_lb": list_price,
            "target_margin_pct": margin,
            "shelf_life_days": arch["shelf"],
            **aging,
            **storage,
            "allergens": to_json([]),
            **uom,
            "weight_tolerance_pct": 0.10,
        })
        seq += 1
        variant_idx += 1

    return extra, seq


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_products(session) -> list[Product]:
    """Create ~300 Product ORM objects and add them to the SQLAlchemy session.

    Returns the list of Product instances created.
    """
    seq = 1
    all_rows: list[dict] = []

    # --- Beef (60% of catalog) ---
    steaks, seq = _generate_beef_steaks(seq)
    all_rows.extend(steaks)

    roasts, seq = _generate_beef_roasts(seq)
    all_rows.extend(roasts)

    ground, seq = _generate_beef_ground(seq)
    all_rows.extend(ground)

    short_ribs, seq = _generate_beef_short_ribs(seq)
    all_rows.extend(short_ribs)

    brisket, seq = _generate_beef_brisket(seq)
    all_rows.extend(brisket)

    # --- Pork (15%) ---
    pork, seq = _generate_pork(seq)
    all_rows.extend(pork)

    # --- Poultry (10%) ---
    poultry, seq = _generate_poultry(seq)
    all_rows.extend(poultry)

    # --- Lamb & Veal (10%) ---
    lv, seq = _generate_lamb_veal(seq)
    all_rows.extend(lv)

    # --- Blends (3%) ---
    blends, seq = _generate_blends(seq)
    all_rows.extend(blends)

    # --- Charcuterie (2%) ---
    charc, seq = _generate_charcuterie(seq)
    all_rows.extend(charc)

    # --- Pad up to TARGET_COUNT ---
    padding, seq = _pad_to_target(all_rows, seq)
    all_rows.extend(padding)

    # Build ORM objects
    products: list[Product] = []
    for row in all_rows:
        p = Product(
            sku_id=row["sku_id"],
            name=row["name"],
            short_description=row["short_description"],
            category=row["category"],
            subcategory=row["subcategory"],
            usda_grade=row["usda_grade"],
            primal_cut=row.get("primal_cut"),
            is_catch_weight=row["is_catch_weight"],
            base_uom=row["base_uom"],
            catch_weight_uom=row.get("catch_weight_uom"),
            nominal_weight=row["nominal_weight"],
            weight_tolerance_pct=row["weight_tolerance_pct"],
            list_price_per_lb=row["list_price_per_lb"],
            cost_per_lb=row["cost_per_lb"],
            target_margin_pct=row["target_margin_pct"],
            aging_type=row["aging_type"],
            aging_days_min=row.get("aging_days_min"),
            aging_days_max=row.get("aging_days_max"),
            shelf_life_days=row["shelf_life_days"],
            storage_temp_min_f=row["storage_temp_min_f"],
            storage_temp_max_f=row["storage_temp_max_f"],
            requires_freezing=row["requires_freezing"],
            allergens=row["allergens"],
            is_active=True,
            is_seasonal=False,
            min_order_qty=1.0,
        )
        products.append(p)

    session.add_all(products)
    return products
