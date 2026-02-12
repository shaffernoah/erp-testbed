"""Generate realistic payment records for Pat LaFrieda ERP testbed.

For each PAID invoice, creates a payment record with timing behavior
driven by PAYMENT_TIMING_DISTRIBUTION, Cari enrollment status, and
customer credit terms.  Settlement follows T+2 convention.
"""

from datetime import date, timedelta

from generators.base import (
    rng,
    make_id,
    fake,
    weighted_choice,
    to_json,
)
from config.lafrieda_profile import (
    PAYMENT_TIMING_DISTRIBUTION,
    PAYMENT_METHODS_CARI,
    PAYMENT_METHODS_TRADITIONAL,
    CARI_REWARD_TIERS,
)
from database.models import Payment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_payment_timing() -> str:
    """Choose a payment timing bucket weighted by distribution."""
    options = list(PAYMENT_TIMING_DISTRIBUTION.keys())
    weights = [PAYMENT_TIMING_DISTRIBUTION[o] for o in options]
    return weighted_choice(options, weights)


def _days_to_payment(timing: str, credit_terms_days: int) -> int:
    """Return the number of days from invoice date to payment date.

    Parameters
    ----------
    timing : str
        One of INSTANT, EARLY, ON_TIME, LATE.
    credit_terms_days : int
        The customer's credit terms in days (e.g. 30 for NET30).
    """
    if timing == "INSTANT":
        return 0
    elif timing == "EARLY":
        # 1-5 days after invoice
        return int(rng.integers(1, 6))
    elif timing == "ON_TIME":
        # Somewhere within the credit terms window
        if credit_terms_days <= 0:
            return 0
        return int(rng.integers(1, credit_terms_days + 1))
    else:  # LATE
        # terms + 1 to terms + 30
        return credit_terms_days + int(rng.integers(1, 31))


def _cari_payment_window(days: int) -> str:
    """Return a human-readable Cari payment window label."""
    if days <= 5:
        return "INSTANT"
    elif days <= 15:
        return "NET15"
    elif days <= 30:
        return "NET30"
    else:
        return "NET45"


def _cari_reward_pct_for_tier(tier_name: str) -> float:
    """Look up the cashback percentage for a Cari reward tier."""
    info = CARI_REWARD_TIERS.get(tier_name)
    if info is None:
        return 1.5  # default to 1_STAR
    return info["cashback_pct"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_payments(session, invoices, customers) -> list[Payment]:
    """Create a Payment for every invoice with status == 'PAID'.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session; generated objects are added but not committed.
    invoices : list[Invoice]
        Previously generated Invoice ORM objects.
    customers : list[Customer]
        Previously generated Customer ORM objects.

    Returns
    -------
    list[Payment]
        The list of generated Payment ORM objects.
    """
    # Build a lookup of customers by customer_id for fast access
    customer_map = {c.customer_id: c for c in customers}

    payments: list[Payment] = []

    for inv in invoices:
        if inv.status != "PAID":
            continue

        customer = customer_map.get(inv.customer_id)
        if customer is None:
            continue

        # ── Timing ────────────────────────────────────────────────────
        timing = _pick_payment_timing()
        credit_terms_days = customer.credit_terms_days or 30
        days = _days_to_payment(timing, credit_terms_days)
        payment_date = inv.invoice_date + timedelta(days=days)

        # Don't let payment_date drift into the future
        today = date.today()
        if payment_date > today:
            payment_date = today

        # ── Settlement: T+2 ───────────────────────────────────────────
        settlement_date = payment_date + timedelta(days=2)

        # ── Cari vs. traditional ──────────────────────────────────────
        is_cari = False
        cari_window = None
        cari_reward = None
        cari_points = 0
        cari_fee = None
        payment_method = str(rng.choice(PAYMENT_METHODS_TRADITIONAL))

        if customer.cari_enrolled and rng.random() < 0.60:
            is_cari = True
            payment_method = str(rng.choice(PAYMENT_METHODS_CARI))
            cari_window = _cari_payment_window(days)
            tier_name = customer.cari_reward_tier or "1_STAR"
            cari_reward = _cari_reward_pct_for_tier(tier_name)
            cari_points = int(round(inv.total_amount * cari_reward / 100.0))
            cari_fee = round(cari_reward * 0.5, 2)  # platform fee ~ half of reward

        # ── Reference number ──────────────────────────────────────────
        ref_prefix = "CARI" if is_cari else payment_method[:3].upper()
        reference_number = f"{ref_prefix}-{fake.bothify('########')}"

        # ── Build ORM object ──────────────────────────────────────────
        payment = Payment(
            payment_id=make_id("PAY"),
            invoice_id=inv.invoice_id,
            customer_id=inv.customer_id,
            payment_date=payment_date,
            amount=inv.total_amount,
            payment_method=payment_method,
            is_cari_payment=is_cari,
            cari_payment_window=cari_window,
            cari_reward_pct=cari_reward,
            cari_points_earned=cari_points,
            cari_fee_pct=cari_fee,
            days_to_payment=days,
            settlement_date=settlement_date,
            settlement_amount=inv.total_amount,
            reference_number=reference_number,
            notes=None,
        )

        session.add(payment)
        payments.append(payment)

    return payments
