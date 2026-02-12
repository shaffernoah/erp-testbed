"""Tool: slow_mover_scanner -- stale inventory value recovery.

Identifies inventory sitting 3+ weeks without movement (but not yet at
critical expiry risk), cross-references with customers who have purchased
that product in the past, and generates a targeted Cari Points discount
campaign to move the stock and recover value.

Pattern: See stale stock -> Find past buyers -> Push targeted discount
         -> Lock in value + drive customer loyalty
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_, not_
from sqlalchemy.orm import Session

from database.models import (
    Customer, Inventory, Invoice, InvoiceLineItem, Product,
)
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_slow_movers(
    session: Session,
    min_days_static: int = 21,
) -> List[dict]:
    """Find SKUs with inventory sitting >= min_days_static days,
    that are NOT yet at critical expiry risk (>7 days until expiry)."""
    rows = (
        session.query(
            Inventory.sku_id,
            func.sum(Inventory.weight_on_hand_lbs).label("stock_lbs"),
            func.sum(Inventory.total_value).label("stock_value"),
            func.avg(Inventory.days_in_inventory).label("avg_days_static"),
            func.min(Inventory.days_until_expiry).label("min_days_to_expiry"),
            func.max(Inventory.last_movement_date).label("last_movement"),
        )
        .filter(
            Inventory.quantity_on_hand > 0,
            Inventory.days_in_inventory >= min_days_static,
            Inventory.days_until_expiry > 7,
        )
        .group_by(Inventory.sku_id)
        .order_by(func.sum(Inventory.total_value).desc())
        .limit(20)
        .all()
    )

    slow_movers = []
    for row in rows:
        product = session.query(Product).get(row.sku_id)
        if not product:
            continue
        slow_movers.append({
            "sku_id": row.sku_id,
            "name": product.name,
            "category": product.category,
            "stock_lbs": round(float(row.stock_lbs or 0), 1),
            "stock_value": round(float(row.stock_value or 0), 2),
            "avg_days_static": round(float(row.avg_days_static or 0), 0),
            "min_days_to_expiry": int(row.min_days_to_expiry or 0),
            "last_movement": str(row.last_movement) if row.last_movement else None,
            "cost_per_lb": product.cost_per_lb,
            "list_price_per_lb": product.list_price_per_lb,
        })
    return slow_movers


def _find_past_buyers(
    session: Session,
    sku_id: str,
    lookback_days: int = 180,
    recent_cutoff_days: int = 30,
    limit: int = 50,
) -> List[dict]:
    """Find Cari-enrolled customers who bought this SKU in the past
    lookback_days but NOT in the last recent_cutoff_days."""
    today = date.today()
    lookback_start = today - timedelta(days=lookback_days)
    recent_start = today - timedelta(days=recent_cutoff_days)

    # Customers who bought in full lookback window
    all_buyers_q = (
        session.query(
            Customer.customer_id,
            Customer.business_name,
            Customer.tier,
            Customer.segment,
            Customer.cari_enrolled,
            Customer.cari_reward_tier,
            func.sum(InvoiceLineItem.line_total).label("historical_spend"),
            func.max(Invoice.invoice_date).label("last_purchase_date"),
        )
        .join(Invoice, Customer.customer_id == Invoice.customer_id)
        .join(InvoiceLineItem, Invoice.invoice_id == InvoiceLineItem.invoice_id)
        .filter(
            InvoiceLineItem.sku_id == sku_id,
            Invoice.invoice_date >= lookback_start,
            Customer.account_status == "ACTIVE",
        )
        .group_by(Customer.customer_id)
    )

    # Filter to those who haven't bought recently
    results = []
    for row in all_buyers_q.all():
        if row.last_purchase_date and row.last_purchase_date >= recent_start:
            continue  # Bought recently, skip
        results.append({
            "customer_id": row.customer_id,
            "business_name": row.business_name,
            "tier": row.tier,
            "segment": row.segment,
            "cari_enrolled": bool(row.cari_enrolled),
            "cari_reward_tier": row.cari_reward_tier,
            "historical_spend": round(float(row.historical_spend or 0), 2),
            "last_purchase_date": str(row.last_purchase_date) if row.last_purchase_date else None,
        })

    # Sort by historical spend (highest first) and limit
    results.sort(key=lambda x: x["historical_spend"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def slow_mover_scan(
    session: Session,
    min_days_static: int = 21,
) -> dict:
    """Scan for slow-moving inventory and generate recovery campaigns.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.
    min_days_static:
        Minimum days inventory has been sitting without movement (default 21).

    Returns
    -------
    dict with ``slow_movers`` list, each containing stock details, past buyer
    list, and a draft Cari campaign for targeted recovery.
    """
    today = date.today()
    slow_movers = _find_slow_movers(session, min_days_static)

    if not slow_movers:
        return {
            "status": "success",
            "scan_date": str(today),
            "message": f"No inventory found sitting {min_days_static}+ days with >7 days to expiry.",
            "slow_movers": [],
            "total_value_at_risk": 0,
            "total_estimated_recovery": 0,
        }

    enriched = []
    total_value_at_risk = 0
    total_estimated_recovery = 0

    for item in slow_movers:
        past_buyers = _find_past_buyers(session, item["sku_id"])

        # Calculate recovery estimates
        stock_value = item["stock_value"]
        total_value_at_risk += stock_value
        # Assume 4% Cari discount, 60% conversion of targeted buyers
        discount_pct = 4.0
        estimated_conversion = 0.6
        estimated_recovery = stock_value * (1 - discount_pct / 100) * estimated_conversion
        total_estimated_recovery += estimated_recovery

        # Build targeted campaign
        cari_customer_ids = [b["customer_id"] for b in past_buyers if b["cari_enrolled"]]
        all_customer_ids = [b["customer_id"] for b in past_buyers]

        campaign = {
            "campaign_id": f"CMP-SM-{uuid.uuid4().hex[:8].upper()}",
            "name": f"Move Slow Stock: {item['name']}",
            "campaign_type": "CLEARANCE",
            "condition_type": "SKU_PURCHASE",
            "condition_value": json.dumps({"sku_ids": [item["sku_id"]]}),
            "reward_type": "PERCENTAGE_OF_ITEMS",
            "reward_value": json.dumps({"pct": discount_pct}),
            "participant_type": "CUSTOM_LIST",
            "eligible_customers": json.dumps(cari_customer_ids if cari_customer_ids else all_customer_ids),
            "eligible_skus": json.dumps([item["sku_id"]]),
            "validity_days": 14,
            "start_date": str(today),
            "end_date": str(today + timedelta(days=14)),
            "budget_total": round(stock_value * 0.05, 2),
            "status": "DRAFT",
        }

        enriched.append({
            "sku_id": item["sku_id"],
            "name": item["name"],
            "category": item["category"],
            "stock_lbs": item["stock_lbs"],
            "stock_value": stock_value,
            "avg_days_static": item["avg_days_static"],
            "min_days_to_expiry": item["min_days_to_expiry"],
            "past_buyers_total": len(past_buyers),
            "past_buyers_cari_enrolled": len(cari_customer_ids),
            "top_past_buyers": past_buyers[:5],
            "estimated_recovery": round(estimated_recovery, 2),
            "campaign": campaign,
        })

    return {
        "status": "success",
        "scan_date": str(today),
        "min_days_static": min_days_static,
        "slow_mover_count": len(enriched),
        "total_value_at_risk": round(total_value_at_risk, 2),
        "total_estimated_recovery": round(total_estimated_recovery, 2),
        "slow_movers": enriched,
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="slow_mover_scanner",
    description=(
        "Scan for inventory sitting 3+ weeks without movement that is not yet "
        "at critical expiry risk. For each slow-moving SKU, identifies customers "
        "who have purchased it in the past 6 months but not recently, then "
        "generates a targeted Cari Points discount campaign to recover value. "
        "Returns slow movers with stock value at risk, past buyer lists, and "
        "draft campaigns. Use this to proactively prevent value erosion."
    ),
    parameters={
        "type": "object",
        "properties": {
            "min_days_static": {
                "type": "integer",
                "description": (
                    "Minimum number of days inventory has been sitting without "
                    "movement. Default is 21 (3 weeks)."
                ),
            },
        },
        "required": [],
    },
    function=slow_mover_scan,
    requires_confirmation=False,
    tags=["ops", "inventory", "sales", "campaigns"],
)
