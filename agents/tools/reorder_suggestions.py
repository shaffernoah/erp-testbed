"""Tool: get_reorder_suggestions -- inventory replenishment advisor.

Queries current inventory levels, compares them against recent demand
velocity and supplier lead times, and returns a prioritized list of SKUs
that should be reordered along with suggested quantities and urgency.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database.models import (
    Inventory, InvoiceLineItem, Invoice, Product, Supplier, Lot,
)
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def get_reorder_suggestions(
    session: Session,
    category: Optional[str] = None,
) -> dict:
    """Analyse inventory and demand to produce reorder recommendations.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.
    category:
        Optional product category filter (BEEF, PORK, POULTRY, LAMB_VEAL,
        BLEND, CHARCUTERIE).  ``None`` means all categories.

    Returns
    -------
    dict with ``suggestions`` list, each containing:
        sku_id, product_name, category, current_stock_lbs,
        avg_daily_demand_lbs, days_of_stock, reorder_qty_lbs,
        preferred_supplier, lead_time_days, urgency
    """
    today = date.today()
    lookback_start = today - timedelta(days=30)

    # -- 1. current stock by SKU --------------------------------------------
    stock_q = (
        session.query(
            Inventory.sku_id,
            func.sum(Inventory.weight_on_hand_lbs).label("total_lbs"),
        )
        .filter(Inventory.quantity_on_hand > 0)
        .group_by(Inventory.sku_id)
    )
    stock_by_sku: Dict[str, float] = {
        row.sku_id: float(row.total_lbs or 0) for row in stock_q.all()
    }

    # -- 2. demand velocity (last 30 days) ----------------------------------
    demand_q = (
        session.query(
            InvoiceLineItem.sku_id,
            func.sum(InvoiceLineItem.catch_weight_lbs).label("total_demand_lbs"),
        )
        .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
        .filter(Invoice.invoice_date >= lookback_start)
        .group_by(InvoiceLineItem.sku_id)
    )
    demand_by_sku: Dict[str, float] = {
        row.sku_id: float(row.total_demand_lbs or 0) for row in demand_q.all()
    }

    # -- 3. supplier lead times per primary product -------------------------
    # Build a mapping: sku_id -> preferred supplier info
    supplier_info: Dict[str, Dict] = {}
    suppliers = session.query(Supplier).filter(Supplier.is_active == True).all()
    for sup in suppliers:
        supplier_info[sup.supplier_id] = {
            "name": sup.name,
            "lead_time_days": sup.avg_lead_time_days or 7,
            "is_preferred": sup.is_preferred,
        }

    # Map SKU to its most common supplier from recent lots
    sku_supplier_q = (
        session.query(
            Lot.sku_id,
            Lot.supplier_id,
            func.count(Lot.lot_id).label("lot_count"),
        )
        .filter(Lot.supplier_id.isnot(None))
        .group_by(Lot.sku_id, Lot.supplier_id)
        .order_by(func.count(Lot.lot_id).desc())
    )
    sku_to_supplier: Dict[str, str] = {}
    for row in sku_supplier_q.all():
        if row.sku_id not in sku_to_supplier:
            sku_to_supplier[row.sku_id] = row.supplier_id

    # -- 4. products --------------------------------------------------------
    prod_q = session.query(Product).filter(Product.is_active == True)
    if category:
        prod_q = prod_q.filter(Product.category == category.upper())
    products = {p.sku_id: p for p in prod_q.all()}

    # -- 5. build suggestions -----------------------------------------------
    suggestions: List[dict] = []
    SAFETY_STOCK_DAYS = 3  # minimum buffer

    for sku_id, product in products.items():
        current_stock = stock_by_sku.get(sku_id, 0.0)
        total_demand_30d = demand_by_sku.get(sku_id, 0.0)
        avg_daily_demand = total_demand_30d / 30.0 if total_demand_30d > 0 else 0.0

        if avg_daily_demand <= 0:
            continue  # no recent demand -- skip

        days_of_stock = current_stock / avg_daily_demand if avg_daily_demand > 0 else 999

        # Supplier lead time
        sup_id = sku_to_supplier.get(sku_id)
        sup_data = supplier_info.get(sup_id, {}) if sup_id else {}
        lead_time = sup_data.get("lead_time_days", 7)

        # Reorder threshold: lead_time + safety stock
        reorder_point_days = lead_time + SAFETY_STOCK_DAYS

        if days_of_stock > reorder_point_days:
            continue  # sufficient stock

        # Target stock: enough for lead_time + 7 extra days
        target_days = lead_time + 7
        target_stock_lbs = avg_daily_demand * target_days
        reorder_qty = max(0, target_stock_lbs - current_stock)

        # Urgency
        if days_of_stock <= 1:
            urgency = "CRITICAL"
        elif days_of_stock <= SAFETY_STOCK_DAYS:
            urgency = "HIGH"
        elif days_of_stock <= lead_time:
            urgency = "MEDIUM"
        else:
            urgency = "LOW"

        suggestions.append({
            "sku_id": sku_id,
            "product_name": product.name,
            "category": product.category,
            "subcategory": product.subcategory,
            "current_stock_lbs": round(current_stock, 1),
            "avg_daily_demand_lbs": round(avg_daily_demand, 1),
            "days_of_stock": round(days_of_stock, 1),
            "reorder_qty_lbs": round(reorder_qty, 1),
            "preferred_supplier": sup_data.get("name", "N/A"),
            "preferred_supplier_id": sup_id,
            "lead_time_days": lead_time,
            "urgency": urgency,
        })

    # Sort by urgency (CRITICAL first) then days_of_stock ascending
    urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    suggestions.sort(key=lambda s: (urgency_order.get(s["urgency"], 4), s["days_of_stock"]))

    return {
        "status": "success",
        "category_filter": category,
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="get_reorder_suggestions",
    description=(
        "Analyze current inventory levels against recent demand velocity and "
        "supplier lead times to generate a prioritized list of SKUs that need "
        "reordering.  Returns recommended quantities, preferred suppliers, and "
        "urgency levels (CRITICAL / HIGH / MEDIUM / LOW)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": (
                    "Optional product category filter: BEEF, PORK, POULTRY, "
                    "LAMB_VEAL, BLEND, or CHARCUTERIE. Omit for all categories."
                ),
                "enum": ["BEEF", "PORK", "POULTRY", "LAMB_VEAL", "BLEND", "CHARCUTERIE"],
            },
        },
        "required": [],
    },
    function=get_reorder_suggestions,
    requires_confirmation=False,
    tags=["ops", "inventory"],
)
