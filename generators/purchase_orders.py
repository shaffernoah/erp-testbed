"""Generate inbound purchase orders from suppliers.

Creates ~500 POs over 12 months of history with realistic line items,
receiving statuses, and cost data tied to the product catalog.
"""

from datetime import date, timedelta

from generators.base import (
    rng,
    make_sequential_id,
    make_id,
    catch_weight,
    random_date_between,
    weighted_choice,
    jitter,
)
from config.lafrieda_profile import STORAGE_LOCATIONS
from config.settings import NUM_MONTHS
from database.models import PurchaseOrder, POLineItem


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUM_PURCHASE_ORDERS = 500

# Status distribution: most are CLOSED (received), some CONFIRMED (in
# transit), a few still DRAFT.
_STATUS_OPTIONS = ["CLOSED", "CONFIRMED", "DRAFT"]
_STATUS_WEIGHTS = [0.80, 0.15, 0.05]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_purchase_orders(
    session,
    products: list,
    suppliers: list,
) -> list[PurchaseOrder]:
    """Create ~500 PurchaseOrder + POLineItem rows and add them to *session*.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session (caller commits).
    products : list[Product]
        Product ORM objects to reference in line items.
    suppliers : list[Supplier]
        Supplier ORM objects to assign to POs.

    Returns
    -------
    list[PurchaseOrder]
        The generated PurchaseOrder instances.
    """
    today = date.today()
    start_date = today - timedelta(days=NUM_MONTHS * 30)

    purchase_orders: list[PurchaseOrder] = []
    all_line_items: list[POLineItem] = []

    for i in range(NUM_PURCHASE_ORDERS):
        n = i + 1
        po_id = make_sequential_id("PO", n)
        po_number = f"PO-2025-{n:05d}"

        # Pick a random supplier
        supplier = suppliers[int(rng.integers(0, len(suppliers)))]

        # Random order date spread across the window
        order_date = random_date_between(start_date, today)

        # Lead time: supplier's avg_lead_time_days +/- a few days
        lead_days = max(1, supplier.avg_lead_time_days + int(rng.integers(-2, 4)))
        expected_delivery = order_date + timedelta(days=lead_days)

        # Status
        status = weighted_choice(_STATUS_OPTIONS, _STATUS_WEIGHTS)

        # Actual delivery date (only for CLOSED POs)
        actual_delivery = None
        if status == "CLOSED":
            drift = int(rng.integers(-1, 3))  # -1 to +2 days from expected
            actual_delivery = expected_delivery + timedelta(days=drift)

        # Receiving location
        receiving_location = str(rng.choice(STORAGE_LOCATIONS))

        # ------ Line items ------
        num_lines = int(rng.integers(1, 6))  # 1-5 line items
        line_items: list[POLineItem] = []
        subtotal = 0.0

        for line_num in range(1, num_lines + 1):
            product = products[int(rng.integers(0, len(products)))]

            # Quantity ordered in lbs — realistic range per line
            qty_ordered = round(float(rng.integers(50, 501)), 2)

            # Cost per lb from product with jitter
            cost_lb = jitter(product.cost_per_lb, 0.05)

            # Catch weight ordered
            cw_ordered = round(qty_ordered * product.nominal_weight / product.nominal_weight, 2)
            cw_ordered = qty_ordered  # PO orders are in lbs directly

            # Quantity received depends on status
            if status == "CLOSED":
                qty_received = qty_ordered
                cw_received = cw_ordered
            elif status == "CONFIRMED":
                qty_received = 0.0
                cw_received = 0.0
            else:  # DRAFT
                qty_received = 0.0
                cw_received = 0.0

            line_total = round(qty_ordered * cost_lb, 2)
            subtotal += line_total

            li = POLineItem(
                po_line_id=make_id("POL"),
                po_id=po_id,
                line_number=line_num,
                sku_id=product.sku_id,
                quantity_ordered=qty_ordered,
                quantity_received=qty_received,
                uom=product.base_uom,
                catch_weight_ordered_lbs=cw_ordered,
                catch_weight_received_lbs=cw_received,
                cost_per_lb=cost_lb,
                line_total=line_total,
                lot_id=None,  # lots generated separately
            )
            line_items.append(li)

        # Freight — small charge
        freight = round(float(rng.uniform(50, 350)), 2)
        total_amount = round(subtotal + freight, 2)

        po = PurchaseOrder(
            po_id=po_id,
            po_number=po_number,
            supplier_id=supplier.supplier_id,
            status=status,
            order_date=order_date,
            expected_delivery_date=expected_delivery,
            actual_delivery_date=actual_delivery,
            subtotal=round(subtotal, 2),
            freight=freight,
            total_amount=total_amount,
            receiving_location=receiving_location,
            notes=None,
        )

        purchase_orders.append(po)
        all_line_items.extend(line_items)

    # Batch add for performance
    session.add_all(purchase_orders)
    session.add_all(all_line_items)

    return purchase_orders
