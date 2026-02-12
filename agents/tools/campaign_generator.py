"""Tool: generate_campaign -- Cari Reward campaign builder.

Takes a high-level campaign goal (e.g. "move excess pork belly",
"win back declining accounts") and queries the ERP for relevant context
(inventory levels, customer segments, margin data), then produces a
fully-formed campaign JSON that matches the Cari Reward API schema.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database.models import (
    Campaign, Customer, Inventory, Invoice, InvoiceLineItem,
    MarginSummary, Product,
)
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Condition / reward type enums (must match Campaign model)
# ---------------------------------------------------------------------------

VALID_CONDITION_TYPES = [
    "ANY",                   # no condition -- all qualifying purchases
    "INVOICE_TOTAL_OVER",    # invoice total > X
    "CATEGORY_PURCHASE",     # purchase in a specific category
    "SKU_PURCHASE",          # purchase of specific SKU(s)
    "DAYS_BEFORE_DUE",       # pay X days before due date
    "REPEAT_PURCHASE",       # Nth purchase in period
    "VOLUME_OVER_LBS",       # single-line weight > X lbs
]

VALID_REWARD_TYPES = [
    "FIXED",                 # flat dollar reward
    "PERCENTAGE",            # percentage of invoice total
    "PERCENTAGE_OF_ITEMS",   # percentage of qualifying line items only
    "POINTS_MULTIPLIER",     # Cari points multiplier
]

VALID_PARTICIPANT_TYPES = [
    "ALL_CUSTOMERS",
    "TIER",         # by customer tier
    "SEGMENT",      # by customer segment
    "CUSTOM_LIST",  # explicit customer_id list
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_excess_inventory(session: Session, category: Optional[str] = None) -> List[dict]:
    """Identify SKUs with excess inventory (>14 days of stock)."""
    q = (
        session.query(
            Inventory.sku_id,
            func.sum(Inventory.weight_on_hand_lbs).label("stock_lbs"),
        )
        .filter(Inventory.quantity_on_hand > 0)
        .group_by(Inventory.sku_id)
    )
    results = []
    for row in q.all():
        prod = session.query(Product).get(row.sku_id)
        if prod and (category is None or prod.category == category.upper()):
            results.append({
                "sku_id": row.sku_id,
                "name": prod.name,
                "category": prod.category,
                "stock_lbs": float(row.stock_lbs or 0),
            })
    results.sort(key=lambda x: x["stock_lbs"], reverse=True)
    return results[:10]


def _find_declining_customers(session: Session, limit: int = 20) -> List[dict]:
    """Find customers whose recent order frequency or volume is declining."""
    today = date.today()
    cutoff_90 = today - timedelta(days=90)

    customers = (
        session.query(Customer)
        .filter(
            Customer.account_status == "ACTIVE",
            Customer.last_order_date < cutoff_90,
            Customer.total_lifetime_orders > 3,
        )
        .order_by(Customer.total_lifetime_revenue.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "customer_id": c.customer_id,
            "business_name": c.business_name,
            "tier": c.tier,
            "segment": c.segment,
            "last_order_date": str(c.last_order_date),
            "lifetime_revenue": c.total_lifetime_revenue,
        }
        for c in customers
    ]


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def generate_campaign(goal: str, session: Session) -> dict:
    """Build a Cari Reward campaign JSON for the given *goal*.

    The function analyses the goal text and queries relevant ERP data to
    populate condition/reward parameters that match the Campaign schema.

    Parameters
    ----------
    goal:
        Natural-language description of the campaign objective.
    session:
        Active SQLAlchemy session.

    Returns
    -------
    dict with ``campaign`` key containing the full campaign payload.
    """
    goal_lower = goal.lower()
    today = date.today()
    campaign_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"

    # Default shell
    campaign: Dict[str, Any] = {
        "campaign_id": campaign_id,
        "name": "",
        "campaign_type": "PROMOTIONAL",
        "condition_type": "ANY",
        "condition_value": json.dumps({}),
        "reward_type": "PERCENTAGE",
        "reward_value": json.dumps({"pct": 2.0}),
        "participant_type": "ALL_CUSTOMERS",
        "eligible_customers": json.dumps([]),
        "eligible_skus": json.dumps([]),
        "tiered": False,
        "tiers": json.dumps(None),
        "stackable": True,
        "validity_days": 30,
        "start_date": str(today),
        "end_date": str(today + timedelta(days=30)),
        "budget_total": 5000.0,
        "budget_spent": 0.0,
        "budget_remaining": 5000.0,
        "status": "DRAFT",
    }

    # ------------------------------------------------------------------
    # Goal-based campaign logic
    # ------------------------------------------------------------------

    if any(kw in goal_lower for kw in ["excess", "move", "clear", "overstock", "surplus"]):
        # Inventory clearance campaign
        # Detect category hint
        cat_hint = None
        for cat in ["beef", "pork", "poultry", "lamb", "veal", "blend", "charcuterie"]:
            if cat in goal_lower:
                cat_hint = cat.upper()
                if cat_hint == "LAMB" or cat_hint == "VEAL":
                    cat_hint = "LAMB_VEAL"
                break

        excess = _find_excess_inventory(session, category=cat_hint)
        sku_ids = [e["sku_id"] for e in excess]
        cat_label = cat_hint or "ALL"

        campaign.update({
            "name": f"Clear Excess {cat_label} Inventory",
            "campaign_type": "CLEARANCE",
            "condition_type": "SKU_PURCHASE",
            "condition_value": json.dumps({"sku_ids": sku_ids}),
            "reward_type": "PERCENTAGE_OF_ITEMS",
            "reward_value": json.dumps({"pct": 3.5}),
            "eligible_skus": json.dumps(sku_ids),
            "participant_type": "ALL_CUSTOMERS",
            "validity_days": 14,
            "end_date": str(today + timedelta(days=14)),
            "budget_total": 10000.0,
            "budget_remaining": 10000.0,
        })

    elif any(kw in goal_lower for kw in ["win back", "lapsed", "declining", "churn", "re-engage", "reengage"]):
        # Win-back campaign for declining accounts
        declining = _find_declining_customers(session)
        customer_ids = [c["customer_id"] for c in declining]

        campaign.update({
            "name": "Win Back Lapsed Accounts",
            "campaign_type": "RETENTION",
            "condition_type": "INVOICE_TOTAL_OVER",
            "condition_value": json.dumps({"min_total": 500.0}),
            "reward_type": "FIXED",
            "reward_value": json.dumps({"amount": 50.0}),
            "participant_type": "CUSTOM_LIST",
            "eligible_customers": json.dumps(customer_ids),
            "validity_days": 30,
            "budget_total": 15000.0,
            "budget_remaining": 15000.0,
        })

    elif any(kw in goal_lower for kw in ["early pay", "payment", "accelerate", "cash flow"]):
        # Early-payment incentive
        campaign.update({
            "name": "Early Payment Bonus",
            "campaign_type": "PAYMENT_INCENTIVE",
            "condition_type": "DAYS_BEFORE_DUE",
            "condition_value": json.dumps({"days_before": 10}),
            "reward_type": "PERCENTAGE",
            "reward_value": json.dumps({"pct": 1.5}),
            "participant_type": "ALL_CUSTOMERS",
            "validity_days": 60,
            "end_date": str(today + timedelta(days=60)),
            "budget_total": 8000.0,
            "budget_remaining": 8000.0,
        })

    elif any(kw in goal_lower for kw in ["volume", "upsell", "increase order", "bigger order"]):
        # Volume-based upsell
        campaign.update({
            "name": "Volume Upsell Bonus",
            "campaign_type": "VOLUME_INCENTIVE",
            "condition_type": "VOLUME_OVER_LBS",
            "condition_value": json.dumps({"min_lbs": 100.0}),
            "reward_type": "PERCENTAGE_OF_ITEMS",
            "reward_value": json.dumps({"pct": 2.0}),
            "participant_type": "ALL_CUSTOMERS",
            "tiered": True,
            "tiers": json.dumps([
                {"min_lbs": 100, "pct": 2.0},
                {"min_lbs": 250, "pct": 2.5},
                {"min_lbs": 500, "pct": 3.0},
            ]),
            "validity_days": 30,
            "budget_total": 12000.0,
            "budget_remaining": 12000.0,
        })

    elif any(kw in goal_lower for kw in ["loyalty", "reward", "retain", "repeat"]):
        # Loyalty / repeat-purchase campaign
        campaign.update({
            "name": "Loyalty Repeat Purchase Reward",
            "campaign_type": "LOYALTY",
            "condition_type": "REPEAT_PURCHASE",
            "condition_value": json.dumps({"nth_order_in_period": 4, "period_days": 30}),
            "reward_type": "POINTS_MULTIPLIER",
            "reward_value": json.dumps({"multiplier": 2.0}),
            "participant_type": "ALL_CUSTOMERS",
            "validity_days": 30,
            "budget_total": 6000.0,
            "budget_remaining": 6000.0,
        })

    elif any(kw in goal_lower for kw in ["category", "beef", "pork", "poultry", "lamb", "charcuterie"]):
        # Category-specific promotion
        cat_hint = None
        for cat in ["beef", "pork", "poultry", "lamb_veal", "lamb", "veal", "blend", "charcuterie"]:
            if cat in goal_lower:
                cat_hint = cat.upper()
                if cat_hint in ("LAMB", "VEAL"):
                    cat_hint = "LAMB_VEAL"
                break
        cat_hint = cat_hint or "BEEF"

        campaign.update({
            "name": f"{cat_hint.replace('_', ' ').title()} Category Promotion",
            "campaign_type": "CATEGORY_PUSH",
            "condition_type": "CATEGORY_PURCHASE",
            "condition_value": json.dumps({"category": cat_hint}),
            "reward_type": "PERCENTAGE_OF_ITEMS",
            "reward_value": json.dumps({"pct": 2.5}),
            "participant_type": "ALL_CUSTOMERS",
            "validity_days": 21,
            "end_date": str(today + timedelta(days=21)),
            "budget_total": 8000.0,
            "budget_remaining": 8000.0,
        })

    else:
        # Generic promotional campaign
        campaign.update({
            "name": f"Promotion: {goal[:60]}",
            "campaign_type": "PROMOTIONAL",
            "condition_type": "INVOICE_TOTAL_OVER",
            "condition_value": json.dumps({"min_total": 250.0}),
            "reward_type": "PERCENTAGE",
            "reward_value": json.dumps({"pct": 2.0}),
            "participant_type": "ALL_CUSTOMERS",
            "validity_days": 30,
        })

    return {
        "status": "success",
        "goal": goal,
        "campaign": campaign,
        "notes": (
            "Campaign created in DRAFT status. Review condition_type, "
            "condition_value, reward_type, and reward_value before activating "
            "via the Cari Reward API."
        ),
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="generate_campaign",
    description=(
        "Generate a Cari Reward campaign JSON from a high-level goal. "
        "Examples: 'move excess pork belly', 'win back declining accounts', "
        "'early payment incentive', 'volume upsell'. The campaign output "
        "matches the Cari Reward API schema with condition_type, condition_value, "
        "reward_type, and reward_value fields."
    ),
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "Natural-language description of the campaign objective, "
                    "e.g. 'move excess pork belly' or 'win back declining accounts'."
                ),
            },
        },
        "required": ["goal"],
    },
    function=generate_campaign,
    requires_confirmation=True,
    tags=["sales", "campaigns"],
)
