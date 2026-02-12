"""Tool: profit_opportunity_scanner -- margin-driven product push.

Analyses 6-month margin data to find high-margin products that are undersold,
identifies customers who buy heavily in the same category but haven't purchased
the specific SKU, then generates a targeted Cari campaign to drive incremental
margin.

Pattern: Find high-margin undersold item -> Identify category buyers who
         don't buy it -> Create targeted campaign -> Quantify margin upside
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
    Customer, Invoice, InvoiceLineItem, MarginSummary, Product,
)
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_high_margin_undersold(
    session: Session,
    min_margin_pct: float = 35.0,
    lookback_days: int = 180,
    limit: int = 15,
) -> List[dict]:
    """Find SKUs with high gross margin but relatively low sales volume.

    Uses InvoiceLineItem + Product.cost_per_lb to compute actual margins
    at the SKU level (MarginSummary is aggregated at customer+category level).
    """
    cutoff = date.today() - timedelta(days=lookback_days)

    # Compute per-SKU revenue and volume from line items
    rows = (
        session.query(
            InvoiceLineItem.sku_id,
            func.sum(InvoiceLineItem.line_total).label("total_revenue"),
            func.sum(InvoiceLineItem.catch_weight_lbs).label("total_volume_lbs"),
            func.avg(InvoiceLineItem.price_per_unit).label("avg_price"),
            func.count(InvoiceLineItem.line_item_id).label("line_count"),
        )
        .join(Invoice, Invoice.invoice_id == InvoiceLineItem.invoice_id)
        .filter(
            Invoice.invoice_date >= cutoff,
            InvoiceLineItem.sku_id.isnot(None),
        )
        .group_by(InvoiceLineItem.sku_id)
        .having(func.sum(InvoiceLineItem.line_total) > 500)
        .all()
    )

    # Enrich with Product cost data and compute margin
    category_volumes: Dict[str, List[float]] = defaultdict(list)
    sku_data: List[dict] = []

    for row in rows:
        product = session.query(Product).get(row.sku_id)
        if not product or not product.is_active or not product.cost_per_lb:
            continue

        avg_price = float(row.avg_price or 0)
        cost = float(product.cost_per_lb)
        if avg_price <= 0:
            continue

        margin_pct = ((avg_price - cost) / avg_price) * 100
        if margin_pct < min_margin_pct:
            continue

        vol = float(row.total_volume_lbs or 0)
        total_revenue = float(row.total_revenue or 0)
        total_margin = total_revenue * (margin_pct / 100)
        category_volumes[product.category].append(vol)

        sku_data.append({
            "sku_id": row.sku_id,
            "name": product.name,
            "category": product.category,
            "subcategory": product.subcategory,
            "avg_margin_pct": round(margin_pct, 1),
            "total_volume_lbs": round(vol, 1),
            "total_revenue": round(total_revenue, 2),
            "total_margin": round(total_margin, 2),
            "avg_price_per_lb": round(avg_price, 2),
            "avg_cost_per_lb": round(cost, 2),
        })

    # Filter to undersold: volume in bottom half for their category
    results = []
    for item in sku_data:
        cat_vols = category_volumes.get(item["category"], [])
        if not cat_vols:
            continue
        cat_vols_sorted = sorted(cat_vols)
        median_idx = len(cat_vols_sorted) // 2
        median_vol = cat_vols_sorted[median_idx] if cat_vols_sorted else 0

        if item["total_volume_lbs"] <= median_vol:
            item["category_median_volume"] = round(median_vol, 1)
            item["volume_vs_median_pct"] = (
                round(item["total_volume_lbs"] / median_vol * 100, 1)
                if median_vol > 0 else 0
            )
            results.append(item)

    results.sort(key=lambda x: x["avg_margin_pct"], reverse=True)
    return results[:limit]


def _find_category_buyers_without_sku(
    session: Session,
    sku_id: str,
    category: str,
    lookback_days: int = 180,
    limit: int = 30,
) -> List[dict]:
    """Find customers who buy heavily in the given category but have NOT
    purchased the specific SKU."""
    cutoff = date.today() - timedelta(days=lookback_days)

    # Get all buyers of this specific SKU in the period
    sku_buyers = (
        session.query(Invoice.customer_id)
        .join(InvoiceLineItem, Invoice.invoice_id == InvoiceLineItem.invoice_id)
        .filter(
            InvoiceLineItem.sku_id == sku_id,
            Invoice.invoice_date >= cutoff,
        )
        .distinct()
    )

    # Find category buyers who are NOT in the sku_buyers set
    results = (
        session.query(
            Customer.customer_id,
            Customer.business_name,
            Customer.tier,
            Customer.segment,
            Customer.cuisine_type,
            Customer.cari_enrolled,
            Customer.cari_reward_tier,
            func.sum(InvoiceLineItem.line_total).label("category_spend"),
            func.count(func.distinct(Invoice.invoice_id)).label("category_orders"),
        )
        .join(Invoice, Customer.customer_id == Invoice.customer_id)
        .join(InvoiceLineItem, Invoice.invoice_id == InvoiceLineItem.invoice_id)
        .filter(
            InvoiceLineItem.category == category,
            Invoice.invoice_date >= cutoff,
            Customer.account_status == "ACTIVE",
            Customer.tier.in_(["WHALE", "ENTERPRISE", "STANDARD"]),
            Customer.customer_id.notin_(sku_buyers.subquery().select()),
        )
        .group_by(Customer.customer_id)
        .having(func.sum(InvoiceLineItem.line_total) > 1000)
        .order_by(func.sum(InvoiceLineItem.line_total).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "customer_id": row.customer_id,
            "business_name": row.business_name,
            "tier": row.tier,
            "segment": row.segment,
            "cuisine_type": row.cuisine_type,
            "cari_enrolled": bool(row.cari_enrolled),
            "cari_reward_tier": row.cari_reward_tier,
            "category_spend_6mo": round(float(row.category_spend or 0), 2),
            "category_orders_6mo": int(row.category_orders or 0),
        }
        for row in results
    ]


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def profit_opportunity_scan(
    session: Session,
    min_margin_pct: float = 35.0,
) -> dict:
    """Scan for high-margin undersold products and generate push campaigns.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.
    min_margin_pct:
        Minimum gross margin percentage to qualify (default 35%).

    Returns
    -------
    dict with ``opportunities`` list, each containing the high-margin SKU,
    target customer list, opportunity value, and a draft Cari campaign.
    """
    today = date.today()
    high_margin_skus = _find_high_margin_undersold(session, min_margin_pct)

    if not high_margin_skus:
        return {
            "status": "success",
            "scan_date": str(today),
            "message": f"No undersold products found with margin >= {min_margin_pct}%.",
            "opportunities": [],
            "total_margin_opportunity": 0,
        }

    opportunities = []
    total_margin_opportunity = 0

    for item in high_margin_skus:
        target_customers = _find_category_buyers_without_sku(
            session, item["sku_id"], item["category"]
        )

        if not target_customers:
            continue

        # Calculate opportunity value
        # Assume 10% conversion: target customers would allocate 10% of
        # their category spend to this SKU
        total_addressable_spend = sum(c["category_spend_6mo"] for c in target_customers)
        conversion_rate = 0.10
        projected_revenue = total_addressable_spend * conversion_rate
        projected_margin = projected_revenue * (item["avg_margin_pct"] / 100)
        total_margin_opportunity += projected_margin

        # Priority score: margin% * opportunity / current revenue
        priority = (
            item["avg_margin_pct"] * projected_margin / max(item["total_revenue"], 1)
        )

        # Build targeted campaign
        cari_customers = [c["customer_id"] for c in target_customers if c["cari_enrolled"]]
        all_target_ids = [c["customer_id"] for c in target_customers]

        # Use gentler discount for high-margin items (2.5%)
        discount_pct = 2.5

        campaign = {
            "campaign_id": f"CMP-PO-{uuid.uuid4().hex[:8].upper()}",
            "name": f"Push High-Margin: {item['name']}",
            "campaign_type": "CATEGORY_PUSH",
            "condition_type": "SKU_PURCHASE",
            "condition_value": json.dumps({"sku_ids": [item["sku_id"]]}),
            "reward_type": "PERCENTAGE_OF_ITEMS",
            "reward_value": json.dumps({"pct": discount_pct}),
            "participant_type": "CUSTOM_LIST",
            "eligible_customers": json.dumps(cari_customers if cari_customers else all_target_ids),
            "eligible_skus": json.dumps([item["sku_id"]]),
            "validity_days": 21,
            "start_date": str(today),
            "end_date": str(today + timedelta(days=21)),
            "budget_total": round(projected_revenue * 0.03, 2),
            "status": "DRAFT",
        }

        opportunities.append({
            "sku_id": item["sku_id"],
            "name": item["name"],
            "category": item["category"],
            "subcategory": item["subcategory"],
            "avg_margin_pct": item["avg_margin_pct"],
            "current_6mo_revenue": item["total_revenue"],
            "current_6mo_margin": item["total_margin"],
            "current_6mo_volume_lbs": item["total_volume_lbs"],
            "volume_vs_category_median_pct": item.get("volume_vs_median_pct", 0),
            "target_customers_count": len(target_customers),
            "target_customers_cari_enrolled": len(cari_customers),
            "total_addressable_spend": round(total_addressable_spend, 2),
            "projected_incremental_revenue": round(projected_revenue, 2),
            "projected_incremental_margin": round(projected_margin, 2),
            "priority_score": round(priority, 2),
            "top_targets": target_customers[:5],
            "campaign": campaign,
        })

    # Sort by priority score
    opportunities.sort(key=lambda x: x["priority_score"], reverse=True)

    return {
        "status": "success",
        "scan_date": str(today),
        "min_margin_pct": min_margin_pct,
        "opportunity_count": len(opportunities),
        "total_margin_opportunity_6mo": round(total_margin_opportunity, 2),
        "opportunities": opportunities,
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="profit_opportunity_scanner",
    description=(
        "Scan 6-month margin data to identify high-margin products (35%+ gross "
        "margin) that are undersold relative to their category. For each "
        "opportunity, finds customers who buy heavily in the same category but "
        "haven't purchased this specific SKU, then generates a targeted Cari "
        "campaign to drive incremental margin. Focuses on WHALE/ENTERPRISE "
        "tiers for maximum revenue impact. Returns opportunities with projected "
        "margin upside and draft campaigns."
    ),
    parameters={
        "type": "object",
        "properties": {
            "min_margin_pct": {
                "type": "number",
                "description": (
                    "Minimum gross margin percentage threshold. "
                    "Default is 35.0."
                ),
            },
        },
        "required": [],
    },
    function=profit_opportunity_scan,
    requires_confirmation=False,
    tags=["sales", "margin", "campaigns"],
)
