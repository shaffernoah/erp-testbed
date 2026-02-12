"""Tool: optimize_payments -- Cari reward-maximizing payment advisor.

Finds open invoices for a customer, analyses credit terms, Cari reward
tiers, and payment windows, then returns a prioritized payment schedule
that maximizes Cari cashback / points while maintaining good standing.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from database.models import Customer, Invoice, Payment
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cari payment-window reward multipliers
# (mirrors lafrieda_profile.py / Cari reward tiers)
# ---------------------------------------------------------------------------

CARI_WINDOW_REWARDS = {
    "INSTANT":  {"label": "Same-day / FedNow", "bonus_pct": 0.50, "max_days": 0},
    "EARLY":    {"label": "Before due date",    "bonus_pct": 0.25, "max_days": None},
    "ON_TIME":  {"label": "On due date",        "bonus_pct": 0.00, "max_days": None},
}

CARI_BASE_CASHBACK = {
    "1_STAR": 1.50,
    "2_STAR": 1.75,
    "3_STAR": 2.00,
}


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def optimize_payments(customer_id: str, session: Session) -> dict:
    """Calculate the optimal payment schedule for *customer_id*.

    Parameters
    ----------
    customer_id:
        Primary key in the ``customers`` table.
    session:
        Active SQLAlchemy session.

    Returns
    -------
    dict with ``schedule`` (list of invoice payment recommendations)
    and ``summary`` (totals, expected rewards).
    """
    customer = session.query(Customer).get(customer_id)
    if customer is None:
        return {"status": "error", "error": f"Customer '{customer_id}' not found."}

    open_invoices = (
        session.query(Invoice)
        .filter(
            Invoice.customer_id == customer_id,
            Invoice.status.in_(["OPEN", "PARTIAL", "OVERDUE"]),
        )
        .order_by(Invoice.due_date.asc())
        .all()
    )

    if not open_invoices:
        return {
            "status": "success",
            "customer_id": customer_id,
            "business_name": customer.business_name,
            "schedule": [],
            "summary": {"message": "No open invoices found."},
        }

    today = date.today()
    is_cari = customer.cari_enrolled or False
    reward_tier = customer.cari_reward_tier or "1_STAR"
    base_cashback_pct = CARI_BASE_CASHBACK.get(reward_tier, 1.5)

    schedule: List[dict] = []
    total_balance = 0.0
    total_reward = 0.0
    total_savings = 0.0

    for inv in open_invoices:
        balance = float(inv.balance_due or inv.total_amount or 0)
        if balance <= 0:
            continue

        due = inv.due_date
        days_until_due = (due - today).days if due else 0
        is_overdue = days_until_due < 0

        # Determine recommended payment strategy
        rec: Dict[str, Any] = {
            "invoice_id": inv.invoice_id,
            "invoice_number": inv.invoice_number,
            "invoice_date": str(inv.invoice_date),
            "due_date": str(due),
            "days_until_due": days_until_due,
            "balance_due": round(balance, 2),
            "status": inv.status,
            "is_overdue": is_overdue,
        }

        if not is_cari:
            # Non-Cari customer -- just prioritize overdue first
            rec.update({
                "recommended_pay_date": str(today) if is_overdue else str(due),
                "payment_method": "ACH",
                "cari_eligible": False,
                "expected_cashback_pct": 0.0,
                "expected_reward_amount": 0.0,
                "rationale": (
                    "Pay overdue immediately to avoid penalties."
                    if is_overdue
                    else "Pay on due date to preserve cash flow."
                ),
                "priority": "HIGH" if is_overdue else "NORMAL",
            })
        else:
            # Cari-enrolled -- maximize rewards
            if is_overdue:
                # Overdue: pay immediately, no bonus
                effective_pct = base_cashback_pct
                pay_date = today
                window = "ON_TIME"
                rationale = (
                    "Invoice is overdue. Pay immediately via Cari to at least "
                    f"earn base {base_cashback_pct}% cashback."
                )
                priority = "HIGH"
            elif days_until_due == 0:
                # Due today
                effective_pct = base_cashback_pct
                pay_date = today
                window = "ON_TIME"
                rationale = f"Due today. Pay now to earn {base_cashback_pct}% base cashback."
                priority = "HIGH"
            elif days_until_due <= 3:
                # Close to due -- early pay for small bonus
                effective_pct = base_cashback_pct + CARI_WINDOW_REWARDS["EARLY"]["bonus_pct"]
                pay_date = today
                window = "EARLY"
                rationale = (
                    f"Pay now ({days_until_due} days early) for "
                    f"{effective_pct}% cashback (base + early bonus)."
                )
                priority = "MEDIUM"
            else:
                # Well before due -- evaluate instant vs early
                instant_pct = base_cashback_pct + CARI_WINDOW_REWARDS["INSTANT"]["bonus_pct"]
                early_pct = base_cashback_pct + CARI_WINDOW_REWARDS["EARLY"]["bonus_pct"]

                # Recommend instant if the bonus justifies the cash flow cost
                instant_reward = balance * (instant_pct / 100)
                early_reward = balance * (early_pct / 100)
                marginal_gain = instant_reward - early_reward

                if marginal_gain > 10.0:
                    # Worth paying instantly
                    effective_pct = instant_pct
                    pay_date = today
                    window = "INSTANT"
                    rationale = (
                        f"Pay today via FedNow for {instant_pct}% cashback "
                        f"(${instant_reward:.2f} reward, ${marginal_gain:.2f} more "
                        f"than early pay)."
                    )
                    priority = "MEDIUM"
                else:
                    # Pay a few days before due for early bonus
                    pay_date = due - timedelta(days=2)
                    if pay_date <= today:
                        pay_date = today
                    effective_pct = early_pct
                    window = "EARLY"
                    rationale = (
                        f"Schedule for {pay_date} ({(due - pay_date).days} days early) "
                        f"for {early_pct}% cashback. Instant pay bonus too small "
                        f"to justify (${marginal_gain:.2f} difference)."
                    )
                    priority = "NORMAL"

            reward_amount = round(balance * (effective_pct / 100), 2)
            total_reward += reward_amount
            rec.update({
                "recommended_pay_date": str(pay_date),
                "payment_method": "CARI_FEDNOW" if window == "INSTANT" else "CARI_ACH",
                "cari_eligible": True,
                "cari_window": window,
                "expected_cashback_pct": round(effective_pct, 2),
                "expected_reward_amount": reward_amount,
                "rationale": rationale,
                "priority": priority,
            })

        total_balance += balance
        schedule.append(rec)

    # Sort: HIGH priority first, then by due date
    priority_order = {"HIGH": 0, "MEDIUM": 1, "NORMAL": 2}
    schedule.sort(key=lambda r: (priority_order.get(r.get("priority", "NORMAL"), 3), r["due_date"]))

    summary = {
        "customer_id": customer_id,
        "business_name": customer.business_name,
        "tier": customer.tier,
        "cari_enrolled": is_cari,
        "cari_reward_tier": reward_tier,
        "open_invoice_count": len(schedule),
        "total_balance_due": round(total_balance, 2),
        "total_expected_rewards": round(total_reward, 2),
    }

    return {
        "status": "success",
        "schedule": schedule,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="optimize_payments",
    description=(
        "Find open invoices for a customer and calculate the optimal payment "
        "timing to maximize Cari rewards (cashback / points). Returns a "
        "prioritized schedule with recommended pay dates, expected reward "
        "amounts, and rationale for each invoice."
    ),
    parameters={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "The customer_id primary key to look up open invoices for.",
            },
        },
        "required": ["customer_id"],
    },
    function=optimize_payments,
    requires_confirmation=False,
    tags=["restaurant", "payments"],
)
