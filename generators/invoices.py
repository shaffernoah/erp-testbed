"""Generate ~50,000 invoices with line items for Pat LaFrieda ERP testbed.

This is the most complex generator.  Each invoice is assigned to a customer
based on tier-weighted frequency, spread across 12 months using day-of-week
and seasonal multipliers, and populated with catch-weight line items that
reference the product catalog and lot inventory.

Performance note
----------------
All invoice / line-item dicts are built first, then bulk-converted to ORM
objects via ``session.add_all()`` to avoid per-row overhead on 50K+ rows.
"""

from __future__ import annotations

from datetime import date, timedelta
from collections import defaultdict
from typing import Optional

import numpy as np

from generators.base import (
    rng,
    make_sequential_id,
    make_id,
    catch_weight,
    random_date_between,
    weighted_choice,
    jitter,
)
from config.lafrieda_profile import (
    CUSTOMER_TIERS,
    SEASONAL_MULTIPLIERS,
    DOW_ORDER_WEIGHTS,
    TIER_DISCOUNT_RANGES,
    CARI_REWARD_TIERS,
)
from config.settings import TARGET_INVOICES, NUM_MONTHS
from database.models import Invoice, InvoiceLineItem


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAX_RATE = 0.08875  # NYC 8.875% sales tax
FREIGHT_MIN = 15.0
FREIGHT_MAX = 85.0

# Mapping from tier -> approximate orders per week (from CUSTOMER_TIERS)
# Used to compute each customer's share of the total invoice pool.
_TIER_FREQ = {
    "WHALE": 5,
    "ENTERPRISE": 3,
    "STANDARD": 2,
    "SMALL": 1,
}

# Zone prefix -> route zone mapping for matching customers to routes.
# Routes have a ``zone`` field like "MANHATTAN", "BROOKLYN", "NJ", etc.
# Customer ``delivery_zone`` is more specific (e.g. "MANHATTAN_MIDTOWN").
# We strip the suffix to match.
_ZONE_EXTRACT = {
    "MANHATTAN": "MANHATTAN",
    "BROOKLYN": "BROOKLYN",
    "QUEENS": "QUEENS",
    "BRONX": "BRONX",
    "NJ": "NJ",
    "WESTCHESTER": "WESTCHESTER",
    "CT": "CT",
    "LONG_ISLAND": "LI",
    "LI": "LI",
    "OTHER": None,
}


def _extract_zone(delivery_zone: str) -> Optional[str]:
    """Map a customer delivery_zone to a route zone prefix."""
    for prefix, zone in _ZONE_EXTRACT.items():
        if delivery_zone.startswith(prefix):
            return zone
    return None


def _build_route_index(routes: list) -> dict[str, list]:
    """Build a mapping from route zone -> list of route_ids."""
    idx: dict[str, list] = defaultdict(list)
    for r in routes:
        idx[r.zone].append(r.route_id)
    return idx


def _build_lot_index(lots: list) -> dict[str, list]:
    """Build a mapping from sku_id -> list of lot objects."""
    idx: dict[str, list] = defaultdict(list)
    for lot in lots:
        idx[lot.sku_id].append(lot)
    return idx


def _pick_route(customer, route_index: dict) -> Optional[str]:
    """Return a route_id that serves the customer's delivery zone, or None."""
    zone = _extract_zone(customer.delivery_zone or "")
    if zone and zone in route_index:
        candidates = route_index[zone]
        return candidates[int(rng.integers(0, len(candidates)))]
    return None


def _pick_lot(sku_id: str, lot_index: dict) -> Optional[str]:
    """Return a lot_id for the given product, or None."""
    candidates = lot_index.get(sku_id)
    if candidates:
        return candidates[int(rng.integers(0, len(candidates)))].lot_id
    return None


# ---------------------------------------------------------------------------
# Date generation helpers
# ---------------------------------------------------------------------------

def _generate_invoice_dates(n_invoices: int, num_months: int) -> list[date]:
    """Spread *n_invoices* dates over *num_months* months using seasonal and
    day-of-week weights.

    Algorithm:
      1. Divide invoices across months proportional to SEASONAL_MULTIPLIERS.
      2. Within each month, assign dates weighted by DOW_ORDER_WEIGHTS.

    Returns a shuffled list of dates (length == n_invoices).
    """
    today = date.today()
    start = today - timedelta(days=num_months * 30)

    # --- Step 1: allocate invoices per month ---
    month_keys = []
    month_multipliers = []
    for m_offset in range(num_months):
        d = start + timedelta(days=m_offset * 30)
        month_num = d.month  # 1-12
        month_keys.append(d.replace(day=1))
        month_multipliers.append(SEASONAL_MULTIPLIERS.get(month_num, 1.0))

    mult_arr = np.array(month_multipliers, dtype=float)
    mult_arr /= mult_arr.sum()
    per_month = np.round(mult_arr * n_invoices).astype(int)

    # Adjust rounding to exactly n_invoices
    diff = n_invoices - int(per_month.sum())
    if diff > 0:
        for _ in range(diff):
            idx = int(rng.integers(0, len(per_month)))
            per_month[idx] += 1
    elif diff < 0:
        for _ in range(-diff):
            idx = int(rng.integers(0, len(per_month)))
            if per_month[idx] > 1:
                per_month[idx] -= 1

    # --- Step 2: within each month, assign day-of-week weighted dates ---
    dow_w = np.array(DOW_ORDER_WEIGHTS, dtype=float)
    dow_w /= dow_w.sum()

    all_dates: list[date] = []

    for month_start, count in zip(month_keys, per_month):
        count = int(count)
        if count == 0:
            continue
        # Determine the last day of the month (or today if this is the current month)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
        month_end = min(month_end, today)

        # Build day-weight array for each day in the month
        days_in_month: list[date] = []
        day_weights: list[float] = []
        d = month_start
        while d <= month_end:
            days_in_month.append(d)
            day_weights.append(dow_w[d.weekday()])
            d += timedelta(days=1)

        if not days_in_month:
            continue

        w = np.array(day_weights, dtype=float)
        w /= w.sum()

        chosen_indices = rng.choice(len(days_in_month), size=count, p=w)
        for ci in chosen_indices:
            all_dates.append(days_in_month[int(ci)])

    rng.shuffle(all_dates)
    return all_dates


# ---------------------------------------------------------------------------
# Customer assignment
# ---------------------------------------------------------------------------

def _assign_customers_to_invoices(
    customers: list,
    n_invoices: int,
) -> list:
    """Return a list of Customer objects of length *n_invoices* where each
    customer appears proportional to their tier's order frequency.
    """
    # Build weight per customer based on tier frequency
    weights = np.array(
        [_TIER_FREQ.get(c.tier, 1) for c in customers],
        dtype=float,
    )
    weights /= weights.sum()

    indices = rng.choice(len(customers), size=n_invoices, p=weights)
    return [customers[int(i)] for i in indices]


# ---------------------------------------------------------------------------
# Invoice status computation
# ---------------------------------------------------------------------------

def _compute_status(invoice_date: date, due_date: date, today: date) -> str:
    """Determine invoice status based on age relative to today.

    - Past-due invoices (due_date < today) are mostly PAID (90%), some
      OVERDUE (7%), a few DISPUTED (3%).
    - Invoices due in the future or today are OPEN.
    """
    if due_date < today:
        roll = float(rng.random())
        if roll < 0.90:
            return "PAID"
        elif roll < 0.97:
            return "OVERDUE"
        else:
            return "DISPUTED"
    else:
        # Recent / future invoices
        return "OPEN"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_invoices(
    session,
    products: list,
    customers: list,
    lots: list,
    routes: list,
) -> list[Invoice]:
    """Generate TARGET_INVOICES invoices with line items.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session (caller commits).
    products : list[Product]
    customers : list[Customer]
    lots : list[Lot]
    routes : list[Route]

    Returns
    -------
    list[Invoice]
        The generated Invoice ORM instances.
    """
    today = date.today()
    n = TARGET_INVOICES

    # Pre-build lookup indices
    route_index = _build_route_index(routes)
    lot_index = _build_lot_index(lots)

    # Pre-compute per-product index for fast random picks
    product_indices = np.arange(len(products))

    # Generate dates and customer assignments in bulk
    invoice_dates = _generate_invoice_dates(n, NUM_MONTHS)
    assigned_customers = _assign_customers_to_invoices(customers, n)

    # Determine the year for invoice numbering based on the start of the window
    year = (today - timedelta(days=NUM_MONTHS * 30)).year

    # ------------------------------------------------------------------
    # Phase 1: build all invoice / line-item dicts
    # ------------------------------------------------------------------
    invoice_dicts: list[dict] = []
    line_item_dicts: list[dict] = []

    for i in range(n):
        inv_n = i + 1
        inv_id = make_sequential_id("INV", inv_n, 6)
        inv_number = f"INV-{year}-{inv_n:06d}"

        customer = assigned_customers[i]
        inv_date = invoice_dates[i]

        # Due date = invoice_date + credit_terms_days
        credit_days = customer.credit_terms_days or 30
        due_date = inv_date + timedelta(days=credit_days)

        # Ship / delivery dates
        ship_date = inv_date
        delivery_date = inv_date + timedelta(days=1)

        # Status
        status = _compute_status(inv_date, due_date, today)

        # Route
        route_id = _pick_route(customer, route_index)

        # Cari fields
        cari_eligible = bool(customer.cari_enrolled)
        cari_cashback_pct = None
        if cari_eligible and customer.cari_reward_tier:
            tier_info = CARI_REWARD_TIERS.get(customer.cari_reward_tier)
            if tier_info:
                cari_cashback_pct = tier_info["cashback_pct"]

        # Tier discount range
        disc_low, disc_high = TIER_DISCOUNT_RANGES.get(
            customer.tier, (0.0, 0.02)
        )

        # ---- Line items ----
        num_lines = int(rng.integers(3, 9))  # 3-8 line items
        line_subtotals: list[float] = []

        for line_num in range(1, num_lines + 1):
            # Pick a random product
            prod_idx = int(rng.integers(0, len(products)))
            product = products[prod_idx]

            # Catch weight from nominal weight
            cw = catch_weight(product.nominal_weight)

            # Discount for this customer's tier
            discount_pct = round(float(rng.uniform(disc_low, disc_high)), 4)

            # Price per unit (per lb)
            base_price = product.list_price_per_lb
            price_per_unit = round(base_price * (1.0 - discount_pct), 2)

            discount_amount = round(base_price * discount_pct * cw, 2)
            line_subtotal = round(cw * base_price, 2)
            line_total = round(cw * price_per_unit, 2)

            # Lot assignment
            lot_id = _pick_lot(product.sku_id, lot_index)

            # Line-level Cari
            li_cari_pct = cari_cashback_pct if cari_eligible else None
            li_cari_pts = round(line_total * (cari_cashback_pct / 100.0), 2) if cari_cashback_pct else 0.0

            line_item_dicts.append({
                "line_item_id": make_id("LI"),
                "invoice_id": inv_id,
                "line_number": line_num,
                "sku_id": product.sku_id,
                "description": product.name,
                "quantity": 1.0,
                "uom": product.base_uom,
                "catch_weight_lbs": cw,
                "price_per_unit": price_per_unit,
                "line_subtotal": line_subtotal,
                "line_tax": 0.0,          # computed at invoice level
                "discount_pct": discount_pct,
                "discount_amount": discount_amount,
                "line_total": line_total,
                "lot_id": lot_id,
                "cari_cashback_pct": li_cari_pct,
                "cari_points": li_cari_pts,
                "category": product.category,
                "gl_code": None,
            })
            line_subtotals.append(line_total)

        # Invoice totals
        subtotal = round(sum(line_subtotals), 2)
        tax_amount = round(subtotal * TAX_RATE, 2) if not customer.tax_exempt else 0.0
        freight_amount = round(float(rng.uniform(FREIGHT_MIN, FREIGHT_MAX)), 2)
        total_amount = round(subtotal + tax_amount + freight_amount, 2)

        # Amount paid / balance
        if status == "PAID":
            amount_paid = total_amount
            balance_due = 0.0
        elif status == "PARTIAL":
            amount_paid = round(total_amount * float(rng.uniform(0.3, 0.8)), 2)
            balance_due = round(total_amount - amount_paid, 2)
        else:
            amount_paid = 0.0
            balance_due = total_amount

        # Cari points at invoice level
        cari_points_earned = 0
        cari_payment_window = None
        cari_payment_method = None
        if cari_eligible and cari_cashback_pct:
            cari_points_earned = int(round(total_amount * cari_cashback_pct / 100.0))
            cari_payment_window = "NET7"
            cari_payment_method = "CARI_ACH"

        invoice_dicts.append({
            "invoice_id": inv_id,
            "invoice_number": inv_number,
            "customer_id": customer.customer_id,
            "invoice_date": inv_date,
            "due_date": due_date,
            "ship_date": ship_date,
            "delivery_date": delivery_date,
            "status": status,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "freight_amount": freight_amount,
            "total_amount": total_amount,
            "amount_paid": amount_paid,
            "balance_due": balance_due,
            "payment_terms": customer.credit_terms,
            "payment_terms_days": credit_days,
            "route_id": route_id,
            "delivery_address": customer.address_line1,
            "po_number": None,
            "cari_eligible": cari_eligible,
            "cari_cashback_pct": cari_cashback_pct,
            "cari_points_earned": cari_points_earned,
            "cari_payment_window": cari_payment_window,
            "cari_payment_method": cari_payment_method,
            "notes": None,
            "dispute_reason": "WEIGHT_DISCREPANCY" if status == "DISPUTED" else None,
        })

    # ------------------------------------------------------------------
    # Phase 2: bulk-create ORM objects
    # ------------------------------------------------------------------
    invoices = [Invoice(**d) for d in invoice_dicts]
    line_items = [InvoiceLineItem(**d) for d in line_item_dicts]

    session.add_all(invoices)
    session.add_all(line_items)

    return invoices
