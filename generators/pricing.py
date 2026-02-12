"""Generate pricing records for Pat LaFrieda ERP testbed.

Creates LIST prices for every product, CONTRACT prices for WHALE and
ENTERPRISE customers (discounted per TIER_DISCOUNT_RANGES), and VOLUME
pricing entries for high-demand products.
"""

from datetime import date, timedelta

from generators.base import rng, make_id, random_date_between, jitter
from config.lafrieda_profile import TIER_DISCOUNT_RANGES
from database.models import Pricing


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Categories considered "popular" and eligible for volume pricing
_VOLUME_ELIGIBLE_CATEGORIES = {"BEEF", "BLEND"}
_VOLUME_ELIGIBLE_SUBCATEGORIES = {"STEAK", "GROUND", "BURGER", "SHORT_RIB"}

# Probability that a volume-eligible product gets a VOLUME price record
_VOLUME_PRICE_PROBABILITY = 0.30

# Volume tier definitions: (min_lbs, max_lbs, extra_discount_pct)
_VOLUME_TIERS = [
    (500,  1_000, 0.02),
    (1_000, 5_000, 0.04),
    (5_000, None,  0.06),
]


def _is_volume_eligible(product) -> bool:
    """Return True if the product should receive VOLUME pricing entries."""
    cat = getattr(product, "category", "")
    subcat = getattr(product, "subcategory", "")
    return cat in _VOLUME_ELIGIBLE_CATEGORIES or subcat in _VOLUME_ELIGIBLE_SUBCATEGORIES


def _random_effective_window() -> tuple[date, date]:
    """Return (effective_date, expiration_date) for a pricing record.

    effective_date : 6-12 months ago
    expiration_date: 6-12 months in the future
    """
    today = date.today()
    eff_start = today - timedelta(days=365)
    eff_end = today - timedelta(days=180)
    effective_date = random_date_between(eff_start, eff_end)

    exp_start = today + timedelta(days=180)
    exp_end = today + timedelta(days=365)
    expiration_date = random_date_between(exp_start, exp_end)

    return effective_date, expiration_date


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pricing(session, products, customers) -> list[Pricing]:
    """Create pricing records and add them to the session.

    Record types
    -------------
    LIST       One per product (customer_id=None). Price = product.list_price_per_lb.
    CONTRACT   One per (WHALE | ENTERPRISE customer, product) pair, discounted
               according to TIER_DISCOUNT_RANGES.
    VOLUME     For popular products, tiered pricing at high quantities.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session.
    products : list[Product]
        Previously generated Product instances.
    customers : list[Customer]
        Previously generated Customer instances.

    Returns
    -------
    list[Pricing]
        The generated Pricing ORM objects.
    """
    # Separate out WHALE and ENTERPRISE customers for contract pricing
    contract_customers = [
        c for c in customers
        if getattr(c, "tier", "") in ("WHALE", "ENTERPRISE")
    ]

    pricing_records: list[Pricing] = []

    for product in products:
        list_price = getattr(product, "list_price_per_lb", None)
        if list_price is None or list_price <= 0:
            continue

        sku_id = product.sku_id
        effective_date, expiration_date = _random_effective_window()

        # ── LIST price (one per product, no customer) ────────────────
        list_record = Pricing(
            pricing_id=make_id("PRC"),
            sku_id=sku_id,
            customer_id=None,
            price_type="LIST",
            price_per_lb=list_price,
            effective_date=effective_date,
            expiration_date=expiration_date,
            min_quantity_lbs=None,
            max_quantity_lbs=None,
            market_basis=None,
            basis_adjustment=None,
            notes=None,
            is_active=True,
        )
        pricing_records.append(list_record)

        # ── CONTRACT prices for WHALE / ENTERPRISE customers ─────────
        for customer in contract_customers:
            tier = getattr(customer, "tier", "STANDARD")
            discount_range = TIER_DISCOUNT_RANGES.get(tier)
            if discount_range is None:
                continue

            disc_low, disc_high = discount_range
            discount_pct = float(rng.uniform(disc_low, disc_high))
            contract_price = round(list_price * (1.0 - discount_pct), 2)

            # Use a slightly different window per customer for realism
            c_eff, c_exp = _random_effective_window()

            contract_record = Pricing(
                pricing_id=make_id("PRC"),
                sku_id=sku_id,
                customer_id=customer.customer_id,
                price_type="CONTRACT",
                price_per_lb=contract_price,
                effective_date=c_eff,
                expiration_date=c_exp,
                min_quantity_lbs=None,
                max_quantity_lbs=None,
                market_basis="LIST",
                basis_adjustment=round(-discount_pct, 4),
                notes=f"{tier} contract discount {discount_pct:.1%}",
                is_active=True,
            )
            pricing_records.append(contract_record)

        # ── VOLUME prices for popular products ───────────────────────
        if _is_volume_eligible(product) and rng.random() < _VOLUME_PRICE_PROBABILITY:
            for min_lbs, max_lbs, extra_disc in _VOLUME_TIERS:
                vol_price = round(list_price * (1.0 - extra_disc), 2)
                vol_eff, vol_exp = _random_effective_window()

                volume_record = Pricing(
                    pricing_id=make_id("PRC"),
                    sku_id=sku_id,
                    customer_id=None,
                    price_type="VOLUME",
                    price_per_lb=vol_price,
                    effective_date=vol_eff,
                    expiration_date=vol_exp,
                    min_quantity_lbs=float(min_lbs),
                    max_quantity_lbs=float(max_lbs) if max_lbs else None,
                    market_basis="LIST",
                    basis_adjustment=round(-extra_disc, 4),
                    notes=f"Volume tier {min_lbs}+ lbs",
                    is_active=True,
                )
                pricing_records.append(volume_record)

    # Bulk add for performance
    session.add_all(pricing_records)
    return pricing_records
