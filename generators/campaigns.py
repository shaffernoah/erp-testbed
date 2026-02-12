"""Generate Cari reward campaigns for Pat LaFrieda ERP testbed.

Creates 10 campaigns matching the Cari Reward API schema.  Condition and
reward values are stored as JSON strings so they round-trip correctly
through the SQLite text columns on the Campaign model.
"""

import json
from datetime import date, timedelta

from generators.base import (
    rng,
    make_id,
    to_json,
    random_date_between,
)
from config.settings import NUM_CAMPAIGNS
from database.models import Campaign


# ---------------------------------------------------------------------------
# Campaign definitions
# ---------------------------------------------------------------------------

def _build_campaign_defs(products, customers):
    """Return the list of 10 hard-coded campaign definition dicts.

    Parameters
    ----------
    products : list[Product]
        Full product catalog -- used to pick beef SKUs for item-level promos.
    customers : list[Customer]
        Full customer list -- used to select participants for targeted promos.
    """
    today = date.today()
    six_months_ago = today - timedelta(days=180)
    three_months_ahead = today + timedelta(days=90)
    six_months_ahead = today + timedelta(days=180)

    # Collect beef SKUs for item-specific campaigns
    beef_skus = [p.sku_id for p in products if p.category == "BEEF"]
    beef_sku_sample = beef_skus[:20] if len(beef_skus) >= 20 else beef_skus

    # Select a handful of enrolled customers for targeted promos
    enrolled = [c.customer_id for c in customers if c.cari_enrolled]
    select_customers = enrolled[:25] if len(enrolled) >= 25 else enrolled

    defs = [
        # ── 1. Early Payment Bonus ────────────────────────────────────
        {
            "name": "Early Payment Bonus",
            "campaign_type": "EARLY_PAYMENT",
            "condition_type": "DAYS_BEFORE",
            "condition_value": to_json({"days_before_due": 10}),
            "reward_type": "PERCENTAGE",
            "reward_value": to_json({"percentage": 1.0}),
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": None,
            "tiered": False,
            "tiers": None,
            "stackable": True,
            "validity_days": 90,
            "start_date": six_months_ago,
            "end_date": three_months_ahead,
            "budget_total": 25_000.00,
        },
        # ── 2. Spend $500 Get 500 Points ──────────────────────────────
        {
            "name": "Spend $500 Get 500 Points",
            "campaign_type": "SPEND_THRESHOLD",
            "condition_type": "INVOICE_TOTAL_OVER",
            "condition_value": to_json({"min_total": 500.00}),
            "reward_type": "FIXED",
            "reward_value": to_json({"points": 500}),
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": None,
            "tiered": False,
            "tiers": None,
            "stackable": True,
            "validity_days": 180,
            "start_date": six_months_ago,
            "end_date": six_months_ahead,
            "budget_total": 50_000.00,
        },
        # ── 3. Welcome Bonus ──────────────────────────────────────────
        {
            "name": "Welcome Bonus",
            "campaign_type": "ONBOARDING",
            "condition_type": "FIRST_INVOICES",
            "condition_value": to_json({"count": 5}),
            "reward_type": "FIXED",
            "reward_value": to_json({"points": 1000}),
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": None,
            "tiered": False,
            "tiers": None,
            "stackable": False,
            "validity_days": 60,
            "start_date": six_months_ago,
            "end_date": six_months_ahead,
            "budget_total": 20_000.00,
        },
        # ── 4. Beef Week Promo ────────────────────────────────────────
        {
            "name": "Beef Week Promo",
            "campaign_type": "ITEM_PROMO",
            "condition_type": "INVOICE_INCLUDES_ITEMS",
            "condition_value": to_json({"sku_ids": beef_sku_sample}),
            "reward_type": "PERCENTAGE_OF_ITEMS",
            "reward_value": to_json({"percentage": 3.0}),
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": to_json(beef_sku_sample),
            "tiered": False,
            "tiers": None,
            "stackable": True,
            "validity_days": 7,
            "start_date": today - timedelta(days=30),
            "end_date": today + timedelta(days=30),
            "budget_total": 15_000.00,
        },
        # ── 5. Tiered Spender ─────────────────────────────────────────
        {
            "name": "Tiered Spender",
            "campaign_type": "TIERED_SPEND",
            "condition_type": "INVOICE_TOTAL_OVER",
            "condition_value": to_json({"min_total": 250.00}),
            "reward_type": "PERCENTAGE",
            "reward_value": to_json({"percentage": 1.0}),  # base tier
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": None,
            "tiered": True,
            "tiers": to_json([
                {"min_total": 250.00,  "percentage": 1.0, "label": "Bronze"},
                {"min_total": 1000.00, "percentage": 1.5, "label": "Silver"},
                {"min_total": 5000.00, "percentage": 2.5, "label": "Gold"},
            ]),
            "stackable": False,
            "validity_days": 180,
            "start_date": six_months_ago,
            "end_date": six_months_ahead,
            "budget_total": 40_000.00,
        },
        # ── 6. Double Points Weekend ──────────────────────────────────
        {
            "name": "Double Points Weekend",
            "campaign_type": "MULTIPLIER",
            "condition_type": "INVOICE_TOTAL_OVER",
            "condition_value": to_json({"min_total": 100.00}),
            "reward_type": "PERCENTAGE",
            "reward_value": to_json({"percentage": 2.0}),
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": None,
            "tiered": False,
            "tiers": None,
            "stackable": True,
            "validity_days": 3,
            "start_date": today - timedelta(days=14),
            "end_date": today + timedelta(days=14),
            "budget_total": 10_000.00,
        },
        # ── 7. Loyalty Milestone ──────────────────────────────────────
        {
            "name": "Loyalty Milestone",
            "campaign_type": "MILESTONE",
            "condition_type": "FIRST_INVOICES",
            "condition_value": to_json({"count": 50}),
            "reward_type": "FIXED",
            "reward_value": to_json({"points": 5000}),
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": None,
            "tiered": False,
            "tiers": None,
            "stackable": False,
            "validity_days": 365,
            "start_date": six_months_ago,
            "end_date": six_months_ahead,
            "budget_total": 30_000.00,
        },
        # ── 8. Premium Cut Cashback ───────────────────────────────────
        {
            "name": "Premium Cut Cashback",
            "campaign_type": "ITEM_PROMO",
            "condition_type": "INVOICE_INCLUDES_ITEMS",
            "condition_value": to_json({"sku_ids": beef_sku_sample[:10]}),
            "reward_type": "PERCENTAGE_OF_ITEMS",
            "reward_value": to_json({"percentage": 2.0}),
            "participant_type": "SELECT_CUSTOMERS",
            "eligible_customers": to_json(select_customers),
            "eligible_skus": to_json(beef_sku_sample[:10]),
            "tiered": False,
            "tiers": None,
            "stackable": True,
            "validity_days": 30,
            "start_date": today - timedelta(days=15),
            "end_date": today + timedelta(days=45),
            "budget_total": 12_000.00,
        },
        # ── 9. Flash $1K Bonus ────────────────────────────────────────
        {
            "name": "Flash $1K Bonus",
            "campaign_type": "SPEND_THRESHOLD",
            "condition_type": "INVOICE_TOTAL_OVER",
            "condition_value": to_json({"min_total": 1000.00}),
            "reward_type": "FIXED",
            "reward_value": to_json({"points": 750}),
            "participant_type": "SELECT_CUSTOMERS",
            "eligible_customers": to_json(select_customers[:15]),
            "eligible_skus": None,
            "tiered": False,
            "tiers": None,
            "stackable": True,
            "validity_days": 14,
            "start_date": today - timedelta(days=7),
            "end_date": today + timedelta(days=7),
            "budget_total": 8_000.00,
        },
        # ── 10. Quick Pay Accelerator ─────────────────────────────────
        {
            "name": "Quick Pay Accelerator",
            "campaign_type": "EARLY_PAYMENT",
            "condition_type": "DAYS_BEFORE",
            "condition_value": to_json({"days_before_due": 5}),
            "reward_type": "PERCENTAGE",
            "reward_value": to_json({"percentage": 1.5}),
            "participant_type": "ALL_CUSTOMERS",
            "eligible_customers": None,
            "eligible_skus": None,
            "tiered": False,
            "tiers": None,
            "stackable": False,
            "validity_days": 90,
            "start_date": today - timedelta(days=60),
            "end_date": today + timedelta(days=60),
            "budget_total": 20_000.00,
        },
    ]

    return defs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_campaigns(session, products, customers) -> list[Campaign]:
    """Create NUM_CAMPAIGNS Campaign ORM objects matching the Cari Reward API.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session; generated objects are added but not committed.
    products : list[Product]
        Previously generated Product ORM objects.
    customers : list[Customer]
        Previously generated Customer ORM objects.

    Returns
    -------
    list[Campaign]
        The list of generated Campaign ORM objects.
    """
    campaign_defs = _build_campaign_defs(products, customers)

    campaigns: list[Campaign] = []

    for defn in campaign_defs[:NUM_CAMPAIGNS]:
        budget_total = defn["budget_total"]
        budget_spent = round(float(rng.uniform(0.0, budget_total * 0.80)), 2)
        budget_remaining = round(budget_total - budget_spent, 2)

        campaign = Campaign(
            campaign_id=make_id("CMP"),
            name=defn["name"],
            campaign_type=defn["campaign_type"],
            condition_type=defn["condition_type"],
            condition_value=defn["condition_value"],
            reward_type=defn["reward_type"],
            reward_value=defn["reward_value"],
            participant_type=defn["participant_type"],
            eligible_customers=defn.get("eligible_customers"),
            eligible_skus=defn.get("eligible_skus"),
            tiered=defn["tiered"],
            tiers=defn.get("tiers"),
            stackable=defn["stackable"],
            validity_days=defn["validity_days"],
            start_date=defn["start_date"],
            end_date=defn.get("end_date"),
            budget_total=budget_total,
            budget_spent=budget_spent,
            budget_remaining=budget_remaining,
            status="ACTIVE",
        )

        session.add(campaign)
        campaigns.append(campaign)

    return campaigns
