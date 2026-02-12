"""Tool: optimize_inventory -- cross-zone stock transfer advisor.

Analyses inventory distribution across storage zones, demand patterns,
and expiry timelines to recommend stock transfers that minimise spoilage
and balance supply across locations.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database.models import (
    Inventory, Invoice, InvoiceLineItem, Lot, Product,
)
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zone-demand mapping heuristic
# ---------------------------------------------------------------------------
# In a real system this would map routes -> zones.  Here we use a simplified
# mapping from delivery_zone on the invoice to storage zone prefix.

_ZONE_ALIAS = {
    "COOLER": ["NJ_COOLER_A", "NJ_COOLER_B", "NJ_COOLER_C"],
    "AGING":  ["NJ_AGING_ROOM_1", "NJ_AGING_ROOM_2"],
    "FREEZER": ["NJ_FREEZER_1", "NJ_FREEZER_2"],
    "STAGING": ["NJ_STAGING"],
}


def _zone_group(location: str) -> str:
    """Map a specific storage location to its zone group."""
    if not location:
        return "UNKNOWN"
    loc_upper = location.upper()
    for group, locs in _ZONE_ALIAS.items():
        if any(loc_upper.startswith(l) or loc_upper == l for l in locs):
            return group
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def optimize_inventory(session: Session) -> dict:
    """Generate cross-zone transfer recommendations.

    The optimizer considers:
    1. **Expiry urgency** -- lots nearing expiry in low-demand zones should
       move to high-throughput zones or staging.
    2. **Zone imbalance** -- skus heavily stocked in one zone but depleted
       in another where demand exists.
    3. **Aging completion** -- lots whose dry/wet aging is complete and
       should be moved from aging rooms to coolers for sale.

    Returns
    -------
    dict with ``transfers`` list and ``summary`` stats.
    """
    today = date.today()
    lookback = today - timedelta(days=14)
    transfers: List[dict] = []

    # ------------------------------------------------------------------
    # 1. Gather current inventory grouped by (sku, location)
    # ------------------------------------------------------------------
    inv_rows = (
        session.query(Inventory)
        .filter(Inventory.quantity_on_hand > 0)
        .all()
    )

    # sku -> location -> inventory row(s)
    sku_loc: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))
    for row in inv_rows:
        sku_loc[row.sku_id][row.location].append(row)

    # ------------------------------------------------------------------
    # 2. Recent demand by SKU (last 14 days)
    # ------------------------------------------------------------------
    demand_q = (
        session.query(
            InvoiceLineItem.sku_id,
            func.sum(InvoiceLineItem.catch_weight_lbs).label("demand_lbs"),
        )
        .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
        .filter(Invoice.invoice_date >= lookback)
        .group_by(InvoiceLineItem.sku_id)
    )
    demand_by_sku: Dict[str, float] = {
        row.sku_id: float(row.demand_lbs or 0) for row in demand_q.all()
    }

    # ------------------------------------------------------------------
    # 3. Expiry-based transfers (lots expiring in <=7 days in non-staging)
    # ------------------------------------------------------------------
    expiry_cutoff = today + timedelta(days=7)
    expiring_lots = (
        session.query(Lot)
        .filter(
            Lot.status == "AVAILABLE",
            Lot.current_quantity_lbs > 0,
            Lot.expiration_date <= expiry_cutoff,
            Lot.expiration_date >= today,
        )
        .order_by(Lot.expiration_date.asc())
        .all()
    )

    for lot in expiring_lots:
        zone = _zone_group(lot.storage_location or "")
        if zone in ("STAGING", "UNKNOWN"):
            continue  # already in staging or untracked

        days_left = (lot.expiration_date - today).days
        product = session.query(Product).get(lot.sku_id)

        transfers.append({
            "transfer_type": "EXPIRY_URGENCY",
            "sku_id": lot.sku_id,
            "product_name": product.name if product else lot.sku_id,
            "lot_id": lot.lot_id,
            "lot_number": lot.lot_number,
            "from_location": lot.storage_location,
            "from_zone": zone,
            "to_location": "NJ_STAGING",
            "to_zone": "STAGING",
            "quantity_lbs": round(float(lot.current_quantity_lbs), 1),
            "days_until_expiry": days_left,
            "urgency": "CRITICAL" if days_left <= 2 else "HIGH",
            "rationale": (
                f"Lot expires in {days_left} day(s). Move to staging "
                f"for priority dispatch."
            ),
        })

    # ------------------------------------------------------------------
    # 4. Aging-complete transfers
    # ------------------------------------------------------------------
    aging_lots = (
        session.query(Lot)
        .filter(
            Lot.status == "AVAILABLE",
            Lot.current_quantity_lbs > 0,
            Lot.aging_target_days.isnot(None),
            Lot.aging_actual_days.isnot(None),
        )
        .all()
    )

    for lot in aging_lots:
        if (lot.aging_actual_days or 0) < (lot.aging_target_days or 999):
            continue  # not yet done aging
        zone = _zone_group(lot.storage_location or "")
        if zone != "AGING":
            continue  # already moved

        product = session.query(Product).get(lot.sku_id)
        transfers.append({
            "transfer_type": "AGING_COMPLETE",
            "sku_id": lot.sku_id,
            "product_name": product.name if product else lot.sku_id,
            "lot_id": lot.lot_id,
            "lot_number": lot.lot_number,
            "from_location": lot.storage_location,
            "from_zone": "AGING",
            "to_location": "NJ_COOLER_A",
            "to_zone": "COOLER",
            "quantity_lbs": round(float(lot.current_quantity_lbs), 1),
            "days_until_expiry": (lot.expiration_date - today).days if lot.expiration_date else None,
            "urgency": "MEDIUM",
            "rationale": (
                f"Aging complete ({lot.aging_actual_days} days of "
                f"{lot.aging_target_days} target). Ready for sale."
            ),
        })

    # ------------------------------------------------------------------
    # 5. Zone-imbalance transfers
    # ------------------------------------------------------------------
    # For each SKU, check if one cooler has >80% of stock while another
    # cooler has <20% and demand exists.
    cooler_locations = _ZONE_ALIAS["COOLER"]
    for sku_id, loc_dict in sku_loc.items():
        cooler_stock: Dict[str, float] = {}
        total_cooler = 0.0
        for loc in cooler_locations:
            weight = sum(float(r.weight_on_hand_lbs or 0) for r in loc_dict.get(loc, []))
            cooler_stock[loc] = weight
            total_cooler += weight

        if total_cooler < 50:  # not enough to worry about
            continue

        demand = demand_by_sku.get(sku_id, 0)
        if demand <= 0:
            continue

        # Find imbalanced pairs
        for loc_high, wt_high in cooler_stock.items():
            if wt_high / total_cooler < 0.70:
                continue
            for loc_low, wt_low in cooler_stock.items():
                if loc_high == loc_low:
                    continue
                if wt_low / total_cooler > 0.20:
                    continue
                # Transfer a portion to balance
                transfer_qty = round((wt_high - wt_low) / 3, 1)
                if transfer_qty < 20:
                    continue

                product = session.query(Product).get(sku_id)
                transfers.append({
                    "transfer_type": "ZONE_BALANCE",
                    "sku_id": sku_id,
                    "product_name": product.name if product else sku_id,
                    "lot_id": None,
                    "lot_number": None,
                    "from_location": loc_high,
                    "from_zone": "COOLER",
                    "to_location": loc_low,
                    "to_zone": "COOLER",
                    "quantity_lbs": transfer_qty,
                    "days_until_expiry": None,
                    "urgency": "LOW",
                    "rationale": (
                        f"{loc_high} has {wt_high:.0f} lbs vs {loc_low} "
                        f"has {wt_low:.0f} lbs. Rebalance for pick efficiency."
                    ),
                })

    # ------------------------------------------------------------------
    # Sort by urgency
    # ------------------------------------------------------------------
    urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    transfers.sort(key=lambda t: urgency_order.get(t["urgency"], 4))

    # Summary stats
    summary = {
        "total_transfers": len(transfers),
        "by_type": {},
        "by_urgency": {},
    }
    for t in transfers:
        summary["by_type"][t["transfer_type"]] = summary["by_type"].get(t["transfer_type"], 0) + 1
        summary["by_urgency"][t["urgency"]] = summary["by_urgency"].get(t["urgency"], 0) + 1

    return {
        "status": "success",
        "scan_date": str(today),
        "transfers": transfers,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="optimize_inventory",
    description=(
        "Analyze inventory distribution across storage zones and recommend "
        "stock transfers to minimize spoilage and balance supply. Considers "
        "expiry urgency, aging completion, and zone imbalances across coolers, "
        "aging rooms, freezers, and staging areas."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    function=optimize_inventory,
    requires_confirmation=False,
    tags=["ops", "inventory"],
)
