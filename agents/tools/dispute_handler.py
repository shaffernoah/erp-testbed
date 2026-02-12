"""Tool: handle_dispute -- invoice dispute analysis and resolution.

Looks up an invoice, analyses the reported issue against line items
and lot data, calculates a fair credit amount, and generates a
structured dispute summary ready for resolution.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.models import (
    Customer, Invoice, InvoiceLineItem, Lot, Product, QualityRecord,
)
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Issue classification
# ---------------------------------------------------------------------------

ISSUE_CATEGORIES = {
    "short_weight":   {"label": "Short Weight",         "default_credit_pct": 1.0},
    "wrong_product":  {"label": "Wrong Product",        "default_credit_pct": 1.0},
    "quality":        {"label": "Quality Issue",        "default_credit_pct": 0.5},
    "temperature":    {"label": "Temperature Abuse",    "default_credit_pct": 1.0},
    "late_delivery":  {"label": "Late Delivery",        "default_credit_pct": 0.10},
    "pricing":        {"label": "Pricing Discrepancy",  "default_credit_pct": None},
    "missing_items":  {"label": "Missing Items",        "default_credit_pct": 1.0},
    "damaged":        {"label": "Damaged Product",      "default_credit_pct": 0.75},
    "grade_mismatch": {"label": "Grade Mismatch",       "default_credit_pct": 0.30},
    "other":          {"label": "Other",                "default_credit_pct": None},
}


def _classify_issue(issue_text: str) -> str:
    """Classify free-text issue into a category key."""
    lower = issue_text.lower()
    keyword_map = {
        "short_weight":   ["short weight", "underweight", "weight", "less than", "lighter"],
        "wrong_product":  ["wrong product", "wrong item", "wrong sku", "incorrect product", "mixed up"],
        "quality":        ["quality", "spoiled", "off smell", "discolored", "slimy", "bad"],
        "temperature":    ["temperature", "warm", "thawed", "frozen", "cold chain", "temp"],
        "late_delivery":  ["late", "delayed", "not on time", "delivery time"],
        "pricing":        ["price", "pricing", "overcharged", "charged more", "cost"],
        "missing_items":  ["missing", "not included", "short shipped", "incomplete"],
        "damaged":        ["damaged", "torn", "crushed", "packaging", "broken"],
        "grade_mismatch": ["grade", "usda", "not prime", "not choice", "mislabeled"],
    }
    for cat, keywords in keyword_map.items():
        if any(kw in lower for kw in keywords):
            return cat
    return "other"


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def handle_dispute(invoice_id: str, issue: str, session: Session) -> dict:
    """Analyse an invoice dispute and generate a resolution summary.

    Parameters
    ----------
    invoice_id:
        The ``invoice_id`` primary key.
    issue:
        Free-text description of the dispute from the customer.
    session:
        Active SQLAlchemy session.

    Returns
    -------
    dict with dispute analysis, credit recommendation, and resolution steps.
    """
    invoice = session.query(Invoice).get(invoice_id)
    if invoice is None:
        return {"status": "error", "error": f"Invoice '{invoice_id}' not found."}

    customer = session.query(Customer).get(invoice.customer_id)
    biz_name = customer.business_name if customer else "Unknown"

    # Classify the issue
    issue_cat = _classify_issue(issue)
    cat_info = ISSUE_CATEGORIES.get(issue_cat, ISSUE_CATEGORIES["other"])

    # Gather line items
    line_items = (
        session.query(InvoiceLineItem)
        .filter(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_number)
        .all()
    )

    line_summaries = []
    total_invoice = float(invoice.total_amount or 0)

    for li in line_items:
        product = session.query(Product).get(li.sku_id) if li.sku_id else None
        lot = session.query(Lot).get(li.lot_id) if li.lot_id else None

        line_summaries.append({
            "line_number": li.line_number,
            "sku_id": li.sku_id,
            "product_name": product.name if product else li.description,
            "quantity": li.quantity,
            "catch_weight_lbs": li.catch_weight_lbs,
            "line_total": float(li.line_total or 0),
            "lot_number": lot.lot_number if lot else None,
            "lot_status": lot.status if lot else None,
            "lot_expiration": str(lot.expiration_date) if lot and lot.expiration_date else None,
        })

    # Check for related quality records on the lots in this invoice
    lot_ids = [li.lot_id for li in line_items if li.lot_id]
    quality_flags = []
    if lot_ids:
        qr = (
            session.query(QualityRecord)
            .filter(
                QualityRecord.lot_id.in_(lot_ids),
                QualityRecord.status == "FAIL",
            )
            .all()
        )
        for rec in qr:
            quality_flags.append({
                "record_id": rec.record_id,
                "record_type": rec.record_type,
                "lot_id": rec.lot_id,
                "temperature_f": rec.temperature_f,
                "notes": rec.notes,
            })

    # ------------------------------------------------------------------
    # Calculate credit amount
    # ------------------------------------------------------------------
    credit_amount = 0.0
    credit_rationale = ""

    if cat_info["default_credit_pct"] is not None:
        pct = cat_info["default_credit_pct"]
        credit_amount = round(total_invoice * pct, 2)
        credit_rationale = (
            f"{cat_info['label']} issue: standard credit of "
            f"{pct * 100:.0f}% of invoice total (${total_invoice:,.2f})."
        )
    else:
        # Pricing or other -- cannot auto-calculate, flag for manual review
        credit_amount = 0.0
        credit_rationale = (
            f"{cat_info['label']} issue requires manual review to determine "
            f"the appropriate credit amount."
        )

    # If quality records corroborate the issue, increase confidence
    corroborated = len(quality_flags) > 0
    if corroborated and cat_info["default_credit_pct"] is not None:
        credit_rationale += (
            f" Quality records corroborate the claim ({len(quality_flags)} "
            f"failed inspection(s) found on related lots)."
        )

    # ------------------------------------------------------------------
    # Build resolution summary
    # ------------------------------------------------------------------
    dispute_ref = f"DSP-{uuid.uuid4().hex[:8].upper()}"

    resolution = {
        "dispute_reference": dispute_ref,
        "invoice_id": invoice_id,
        "invoice_number": invoice.invoice_number,
        "invoice_date": str(invoice.invoice_date),
        "invoice_total": total_invoice,
        "customer_id": invoice.customer_id,
        "business_name": biz_name,
        "customer_tier": customer.tier if customer else None,

        "reported_issue": issue,
        "issue_category": issue_cat,
        "issue_label": cat_info["label"],

        "line_items": line_summaries,
        "quality_flags": quality_flags,
        "corroborated_by_quality_data": corroborated,

        "credit_amount": credit_amount,
        "credit_rationale": credit_rationale,
        "requires_manual_review": cat_info["default_credit_pct"] is None,

        "recommended_steps": _get_recommended_steps(issue_cat, corroborated),
    }

    return {
        "status": "success",
        "dispute": resolution,
    }


def _get_recommended_steps(issue_cat: str, corroborated: bool) -> List[str]:
    """Return a list of recommended resolution steps."""
    steps = []

    if issue_cat == "short_weight":
        steps = [
            "Verify catch weights against packing slip and scale records.",
            "Issue credit for the weight difference if confirmed.",
            "Review packing station for calibration issues.",
        ]
    elif issue_cat == "wrong_product":
        steps = [
            "Arrange pickup of incorrect product on next delivery run.",
            "Ship correct product with expedited delivery.",
            "Issue full credit for the incorrect line items.",
        ]
    elif issue_cat in ("quality", "temperature", "damaged"):
        steps = [
            "Request photos from customer if not already provided.",
            "Place affected lot(s) on HOLD pending investigation.",
            "Issue credit per policy.",
            "File supplier quality report if lot defect confirmed.",
        ]
    elif issue_cat == "late_delivery":
        steps = [
            "Confirm delivery timestamp against route log.",
            "Issue goodwill credit if late delivery is confirmed.",
            "Review route scheduling for systemic issues.",
        ]
    elif issue_cat == "pricing":
        steps = [
            "Compare invoice pricing to contract/pricing table.",
            "Identify discrepancy source (contract expired, wrong tier, etc.).",
            "Issue credit for the overcharge amount.",
            "Update pricing records if needed.",
        ]
    elif issue_cat == "missing_items":
        steps = [
            "Cross-reference packing slip against invoice line items.",
            "Check warehouse pick records for the order.",
            "Ship missing items or issue credit.",
        ]
    elif issue_cat == "grade_mismatch":
        steps = [
            "Review lot grade stamp and inspection records.",
            "Verify against customer contract grade requirements.",
            "Issue credit for grade differential if confirmed.",
        ]
    else:
        steps = [
            "Document the issue details thoroughly.",
            "Escalate to operations manager for review.",
            "Follow up with customer within 24 hours.",
        ]

    if corroborated:
        steps.insert(0, "NOTE: Quality data corroborates the customer's claim.")

    return steps


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="handle_dispute",
    description=(
        "Analyse an invoice dispute: look up the invoice and its line items, "
        "classify the issue, check for corroborating quality records, calculate "
        "a recommended credit amount, and generate a structured dispute "
        "resolution summary with recommended next steps."
    ),
    parameters={
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "string",
                "description": "The invoice_id to investigate.",
            },
            "issue": {
                "type": "string",
                "description": (
                    "Free-text description of the dispute/issue from the customer, "
                    "e.g. 'received underweight ribeyes' or 'product was warm on arrival'."
                ),
            },
        },
        "required": ["invoice_id", "issue"],
    },
    function=handle_dispute,
    requires_confirmation=False,
    tags=["restaurant", "disputes"],
)
