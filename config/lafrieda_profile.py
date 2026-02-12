"""Pat LaFrieda business profile constants.

Realistic seed data for products, geographies, pricing bands, and
customer archetypes based on Pat LaFrieda Meat Purveyors' actual
business model as a premium NYC-metro meat distributor.
"""

# ---------------------------------------------------------------------------
# Product catalog seeds
# ---------------------------------------------------------------------------

CATEGORIES = {
    "BEEF": 0.60,
    "PORK": 0.15,
    "POULTRY": 0.10,
    "LAMB_VEAL": 0.10,
    "BLEND": 0.03,
    "CHARCUTERIE": 0.02,
}

BEEF_SUBCATEGORIES = [
    "STEAK", "ROAST", "GROUND", "SHORT_RIB", "BRISKET",
    "STEW", "OSSO_BUCO", "OFFAL",
]

USDA_GRADES = ["PRIME", "CHOICE", "SELECT", "WAGYU"]

PRIMAL_CUTS = [
    "RIB", "LOIN", "CHUCK", "ROUND", "BRISKET",
    "SHORT_PLATE", "FLANK", "SIRLOIN", "TENDERLOIN",
]

AGING_TYPES = ["DRY", "WET", "FRESH"]

# Nominal weights and pricing by product archetype (per lb)
PRODUCT_ARCHETYPES = {
    # (category, subcategory): (nominal_weight_lb, cost_per_lb, list_price_per_lb, shelf_life_days)
    ("BEEF", "STEAK"): {
        "PRIME":  {"weight": 14.0, "cost": 20.0, "list": 30.0, "shelf": 18},
        "CHOICE": {"weight": 14.0, "cost": 14.0, "list": 22.0, "shelf": 18},
        "SELECT": {"weight": 14.0, "cost": 10.0, "list": 16.0, "shelf": 18},
        "WAGYU":  {"weight": 10.0, "cost": 55.0, "list": 85.0, "shelf": 14},
    },
    ("BEEF", "ROAST"): {
        "PRIME":  {"weight": 18.0, "cost": 16.0, "list": 24.0, "shelf": 21},
        "CHOICE": {"weight": 18.0, "cost": 11.0, "list": 18.0, "shelf": 21},
    },
    ("BEEF", "GROUND"): {
        "default": {"weight": 5.0, "cost": 4.5, "list": 8.0, "shelf": 7},
    },
    ("BEEF", "SHORT_RIB"): {
        "PRIME":  {"weight": 8.0, "cost": 12.0, "list": 20.0, "shelf": 14},
        "CHOICE": {"weight": 8.0, "cost": 8.0, "list": 14.0, "shelf": 14},
    },
    ("BEEF", "BRISKET"): {
        "PRIME":  {"weight": 14.0, "cost": 8.0, "list": 14.0, "shelf": 18},
        "CHOICE": {"weight": 14.0, "cost": 5.5, "list": 10.0, "shelf": 18},
    },
    ("PORK", "CHOP"): {
        "default": {"weight": 6.0, "cost": 4.0, "list": 8.5, "shelf": 14},
    },
    ("PORK", "BELLY"): {
        "default": {"weight": 12.0, "cost": 3.5, "list": 7.0, "shelf": 14},
    },
    ("PORK", "RIBS"): {
        "default": {"weight": 4.0, "cost": 3.0, "list": 7.5, "shelf": 14},
    },
    ("PORK", "SAUSAGE"): {
        "default": {"weight": 5.0, "cost": 3.0, "list": 7.0, "shelf": 10},
    },
    ("POULTRY", "BREAST"): {
        "default": {"weight": 6.0, "cost": 2.5, "list": 5.5, "shelf": 10},
    },
    ("POULTRY", "WHOLE"): {
        "default": {"weight": 4.5, "cost": 2.0, "list": 4.5, "shelf": 10},
    },
    ("POULTRY", "THIGH"): {
        "default": {"weight": 5.0, "cost": 1.8, "list": 4.0, "shelf": 10},
    },
    ("POULTRY", "WING"): {
        "default": {"weight": 10.0, "cost": 2.0, "list": 5.0, "shelf": 10},
    },
    ("POULTRY", "DUCK"): {
        "default": {"weight": 5.5, "cost": 6.0, "list": 12.0, "shelf": 10},
    },
    ("LAMB_VEAL", "RACK"): {
        "default": {"weight": 3.0, "cost": 18.0, "list": 32.0, "shelf": 14},
    },
    ("LAMB_VEAL", "CHOP"): {
        "default": {"weight": 4.0, "cost": 14.0, "list": 26.0, "shelf": 14},
    },
    ("LAMB_VEAL", "SHANK"): {
        "default": {"weight": 3.0, "cost": 6.0, "list": 12.0, "shelf": 14},
    },
    ("LAMB_VEAL", "VEAL_CHOP"): {
        "default": {"weight": 4.0, "cost": 16.0, "list": 28.0, "shelf": 12},
    },
    ("BLEND", "BURGER"): {
        "default": {"weight": 10.0, "cost": 5.0, "list": 9.0, "shelf": 5},
    },
    ("CHARCUTERIE", "BACON"): {
        "default": {"weight": 5.0, "cost": 5.0, "list": 10.0, "shelf": 30},
    },
    ("CHARCUTERIE", "PROSCIUTTO"): {
        "default": {"weight": 8.0, "cost": 12.0, "list": 22.0, "shelf": 60},
    },
}

# Specific product names for realistic SKU generation
BEEF_STEAK_NAMES = [
    "Bone-In Ribeye", "Boneless Ribeye", "NY Strip", "Filet Mignon",
    "Porterhouse", "T-Bone", "Hanger Steak", "Skirt Steak",
    "Flank Steak", "Flat Iron", "Tomahawk Ribeye", "Denver Steak",
    "Coulotte Steak", "Tri-Tip Steak",
]

BEEF_ROAST_NAMES = [
    "Prime Rib Roast", "Tenderloin Roast", "Sirloin Roast",
    "Chuck Roast", "Eye Round Roast", "Top Round Roast",
]

BEEF_GROUND_NAMES = [
    "Ground Beef 80/20", "Ground Beef 85/15", "Ground Beef 90/10",
    "Ground Chuck", "Ground Sirloin",
]

BEEF_SHORT_RIB_NAMES = ["Bone-In Short Ribs", "Boneless Short Ribs", "Flanken Short Ribs"]

BEEF_BRISKET_NAMES = ["Whole Packer Brisket", "Brisket Flat", "Brisket Point"]

PORK_NAMES = {
    "CHOP": ["Bone-In Pork Chop", "Boneless Pork Chop", "Double-Cut Pork Chop"],
    "BELLY": ["Pork Belly Slab", "Pork Belly Sliced"],
    "RIBS": ["Baby Back Ribs", "Spare Ribs", "St. Louis Ribs"],
    "SAUSAGE": ["Italian Sweet Sausage", "Italian Hot Sausage", "Bratwurst", "Chorizo", "Breakfast Sausage"],
}

POULTRY_NAMES = {
    "BREAST": ["Chicken Breast Boneless", "Chicken Breast Bone-In", "Turkey Breast"],
    "WHOLE": ["Whole Chicken", "Cornish Game Hen"],
    "THIGH": ["Chicken Thigh Boneless", "Chicken Thigh Bone-In"],
    "WING": ["Chicken Wings Whole", "Chicken Wings Split"],
    "DUCK": ["Whole Duck", "Duck Breast", "Duck Leg Confit"],
}

LAMB_VEAL_NAMES = {
    "RACK": ["Rack of Lamb", "Frenched Rack of Lamb"],
    "CHOP": ["Lamb Loin Chop", "Lamb Rib Chop"],
    "SHANK": ["Lamb Shank", "Lamb Osso Buco"],
    "VEAL_CHOP": ["Veal Rib Chop", "Veal Loin Chop", "Veal Scallopini"],
}

BLEND_NAMES = [
    "LaFrieda Original Blend", "LaFrieda Premium Blend",
    "Black Label Blend", "Short Rib Blend",
    "Brisket Blend", "Wagyu Blend",
    "Custom Blend A", "Custom Blend B",
]

CHARCUTERIE_NAMES = {
    "BACON": ["Applewood Smoked Bacon", "Black Pepper Bacon", "Maple Bacon"],
    "PROSCIUTTO": ["Prosciutto di Parma", "Bresaola", "Coppa", "Pancetta"],
}

# ---------------------------------------------------------------------------
# Customer archetypes
# ---------------------------------------------------------------------------

CUSTOMER_TIERS = {
    "WHALE":      {"pct": 0.02, "annual_min": 100_000, "annual_max": 2_000_000, "order_freq_per_week": 5},
    "ENTERPRISE":  {"pct": 0.08, "annual_min": 50_000,  "annual_max": 100_000,   "order_freq_per_week": 3},
    "STANDARD":    {"pct": 0.60, "annual_min": 10_000,  "annual_max": 50_000,    "order_freq_per_week": 2},
    "SMALL":       {"pct": 0.30, "annual_min": 1_000,   "annual_max": 10_000,    "order_freq_per_week": 1},
}

CUSTOMER_SEGMENTS = ["FINE_DINING", "CASUAL", "FAST_CASUAL", "QSR", "HOTEL_FB", "CATERING"]

CUISINE_TYPES = [
    "STEAKHOUSE", "ITALIAN", "AMERICAN", "FRENCH", "JAPANESE",
    "MEXICAN", "LATIN", "ASIAN_FUSION", "MEDITERRANEAN", "MULTI",
]

CREDIT_TERMS = ["NET15", "NET30", "NET45", "COD"]

# ---------------------------------------------------------------------------
# NYC metro geography
# ---------------------------------------------------------------------------

DELIVERY_ZONES = {
    "MANHATTAN_MIDTOWN":    {"pct": 0.12, "borough": "MANHATTAN"},
    "MANHATTAN_DOWNTOWN":   {"pct": 0.10, "borough": "MANHATTAN"},
    "MANHATTAN_UES":        {"pct": 0.06, "borough": "MANHATTAN"},
    "MANHATTAN_UWS":        {"pct": 0.05, "borough": "MANHATTAN"},
    "MANHATTAN_HARLEM":     {"pct": 0.02, "borough": "MANHATTAN"},
    "BROOKLYN_WILLIAMSBURG": {"pct": 0.06, "borough": "BROOKLYN"},
    "BROOKLYN_DUMBO":       {"pct": 0.04, "borough": "BROOKLYN"},
    "BROOKLYN_PARK_SLOPE":  {"pct": 0.04, "borough": "BROOKLYN"},
    "BROOKLYN_BUSHWICK":    {"pct": 0.04, "borough": "BROOKLYN"},
    "QUEENS_ASTORIA":       {"pct": 0.04, "borough": "QUEENS"},
    "QUEENS_LIC":           {"pct": 0.03, "borough": "QUEENS"},
    "QUEENS_FLUSHING":      {"pct": 0.03, "borough": "QUEENS"},
    "BRONX":                {"pct": 0.05, "borough": "BRONX"},
    "NJ_HOBOKEN":           {"pct": 0.05, "borough": "NJ"},
    "NJ_JERSEY_CITY":       {"pct": 0.05, "borough": "NJ"},
    "NJ_BERGEN":            {"pct": 0.05, "borough": "NJ"},
    "WESTCHESTER":          {"pct": 0.05, "borough": "WESTCHESTER"},
    "CT_FAIRFIELD":         {"pct": 0.03, "borough": "CT"},
    "LONG_ISLAND":          {"pct": 0.05, "borough": "LI"},
    "OTHER":                {"pct": 0.04, "borough": "OTHER"},
}

# ---------------------------------------------------------------------------
# Supplier regions
# ---------------------------------------------------------------------------

SUPPLIER_REGIONS = [
    "MIDWEST", "NORTHEAST", "SOUTHEAST", "WEST", "INTERNATIONAL",
]

SUPPLIER_TYPES = ["RANCH", "PACKER", "IMPORTER", "CO_OP"]

# ---------------------------------------------------------------------------
# Storage zones
# ---------------------------------------------------------------------------

STORAGE_LOCATIONS = [
    "NJ_COOLER_A", "NJ_COOLER_B", "NJ_COOLER_C",
    "NJ_AGING_ROOM_1", "NJ_AGING_ROOM_2",
    "NJ_FREEZER_1", "NJ_FREEZER_2",
    "NJ_STAGING",
]

TEMP_RANGES = {
    "COOLER":  (33.0, 38.0),   # Fahrenheit
    "AGING":   (34.0, 36.0),
    "FREEZER": (-5.0, 0.0),
    "STAGING": (35.0, 42.0),
}

# ---------------------------------------------------------------------------
# Cari integration constants
# ---------------------------------------------------------------------------

CARI_ENROLLMENT_RATE = 0.30  # 30% of customers enrolled in Cari
CARI_WHALE_ENROLLMENT_RATE = 0.60  # Whales enroll at higher rate

PAYMENT_TIMING_DISTRIBUTION = {
    "INSTANT": 0.15,
    "EARLY": 0.35,
    "ON_TIME": 0.40,
    "LATE": 0.10,
}

PAYMENT_METHODS_CARI = ["CARI_CARD", "CARI_ACH", "CARI_FEDNOW"]
PAYMENT_METHODS_TRADITIONAL = ["CHECK", "ACH", "WIRE"]

# Cari reward tiers
CARI_REWARD_TIERS = {
    "1_STAR": {"min_annual": 0,      "cashback_pct": 1.5},
    "2_STAR": {"min_annual": 50_000,  "cashback_pct": 1.75},
    "3_STAR": {"min_annual": 150_000, "cashback_pct": 2.0},
}

# Pricing discounts by customer tier (off list price)
TIER_DISCOUNT_RANGES = {
    "WHALE":      (0.08, 0.12),
    "ENTERPRISE":  (0.05, 0.08),
    "STANDARD":    (0.02, 0.05),
    "SMALL":       (0.00, 0.02),
}

# Seasonal demand multipliers by month (1-indexed)
SEASONAL_MULTIPLIERS = {
    1: 0.85,   # Jan - post-holiday slump
    2: 0.90,   # Feb
    3: 0.95,   # Mar
    4: 1.00,   # Apr
    5: 1.05,   # May - grilling starts
    6: 1.12,   # Jun - peak grilling
    7: 1.15,   # Jul - peak grilling
    8: 1.10,   # Aug
    9: 1.00,   # Sep
    10: 1.00,  # Oct
    11: 1.15,  # Nov - holidays
    12: 1.10,  # Dec - holidays
}

# Day-of-week order distribution (Mon=0, Sun=6)
DOW_ORDER_WEIGHTS = [0.20, 0.20, 0.18, 0.18, 0.15, 0.06, 0.03]
