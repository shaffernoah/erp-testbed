"""Generate AR-aging snapshots and margin summaries for Pat LaFrieda ERP testbed.

Produces two sets of financial rollups:

1. **AR Aging** -- monthly snapshots (last 12 months) per customer showing
   current / 31-60 / 61-90 / 90+ aging buckets derived from invoice dates
   and payment status.

2. **Margin Summary** -- monthly summaries by customer and product category
   with revenue, COGS, gross margin, and volume metrics computed from
   invoice line items and product cost data.
"""

from collections import defaultdict
from datetime import date, timedelta

from generators.base import (
    rng,
    make_id,
)
from config.settings import NUM_MONTHS
from database.models import ARaging, MarginSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_starts(num_months: int) -> list[date]:
    """Return a list of first-of-month dates for the last *num_months* months.

    The list is ordered oldest first, ending with the current month.
    """
    today = date.today()
    starts: list[date] = []
    for m in range(num_months - 1, -1, -1):
        # Walk backwards m months from today
        year = today.year
        month = today.month - m
        while month <= 0:
            month += 12
            year -= 1
        starts.append(date(year, month, 1))
    return starts


def _end_of_month(d: date) -> date:
    """Return the last day of the month containing *d*."""
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


# ---------------------------------------------------------------------------
# AR Aging
# ---------------------------------------------------------------------------

def _generate_ar_aging(session, invoices, payments, customers) -> list[ARaging]:
    """Build per-customer monthly AR aging snapshots.

    For each snapshot month we look at invoices that were outstanding as of
    the snapshot date and bucket the balance by days past due.
    """
    # Build payment lookup: invoice_id -> total amount paid before/on a date
    payment_by_invoice: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for pay in payments:
        payment_by_invoice[pay.invoice_id].append((pay.payment_date, pay.amount))

    # Customer set
    customer_ids = {c.customer_id for c in customers}

    month_starts = _month_starts(NUM_MONTHS)
    records: list[ARaging] = []

    for snap_start in month_starts:
        snap_date = _end_of_month(snap_start)

        # Accumulate buckets per customer
        buckets: dict[str, dict[str, float]] = {}
        for cid in customer_ids:
            buckets[cid] = {
                "current": 0.0,
                "31_60": 0.0,
                "61_90": 0.0,
                "over_90": 0.0,
            }

        for inv in invoices:
            # Only consider invoices issued on or before the snapshot date
            if inv.invoice_date > snap_date:
                continue
            if inv.customer_id not in customer_ids:
                continue

            # Determine how much was paid by snapshot date
            paid_by_snap = sum(
                amt for pay_date, amt in payment_by_invoice.get(inv.invoice_id, [])
                if pay_date <= snap_date
            )
            balance = inv.total_amount - paid_by_snap
            if balance <= 0.01:
                continue  # fully paid

            days_outstanding = (snap_date - inv.invoice_date).days

            cid = inv.customer_id
            if days_outstanding <= 30:
                buckets[cid]["current"] += balance
            elif days_outstanding <= 60:
                buckets[cid]["31_60"] += balance
            elif days_outstanding <= 90:
                buckets[cid]["61_90"] += balance
            else:
                buckets[cid]["over_90"] += balance

        # Emit a record for each customer that has any outstanding balance
        for cid, b in buckets.items():
            total = b["current"] + b["31_60"] + b["61_90"] + b["over_90"]
            if total < 0.01:
                continue

            # Weighted average days outstanding (approximate)
            weighted = (
                b["current"] * 15
                + b["31_60"] * 45
                + b["61_90"] * 75
                + b["over_90"] * 120
            )
            wavg = round(weighted / total, 1) if total > 0 else 0.0

            record = ARaging(
                snapshot_id=make_id("ARA"),
                snapshot_date=snap_date,
                customer_id=cid,
                current_amount=round(b["current"], 2),
                days_31_60=round(b["31_60"], 2),
                days_61_90=round(b["61_90"], 2),
                days_over_90=round(b["over_90"], 2),
                total_outstanding=round(total, 2),
                weighted_avg_days=wavg,
            )
            records.append(record)

    session.add_all(records)
    return records


# ---------------------------------------------------------------------------
# Margin Summary
# ---------------------------------------------------------------------------

def _generate_margin_summaries(session, invoices, payments, customers) -> list[MarginSummary]:
    """Build monthly margin summaries by customer and product category.

    Revenue comes from invoice line totals; COGS is estimated from
    product.cost_per_lb * volume in pounds.
    """
    # Build product cost lookup: sku_id -> cost_per_lb
    # We collect this from line items' associated products via the relationship.
    # Since we may not have eager-loaded products we build a sku -> cost map
    # from the line items themselves (each line_item has a .product relationship).
    sku_cost_cache: dict[str, float] = {}

    # Aggregate: (month_start, customer_id, category) -> metrics
    AggKey = tuple  # (date, str, str)
    agg: dict[AggKey, dict] = defaultdict(lambda: {
        "revenue": 0.0,
        "cogs": 0.0,
        "volume_lbs": 0.0,
        "num_invoices": set(),
    })

    for inv in invoices:
        if not hasattr(inv, "line_items"):
            continue
        inv_month = date(inv.invoice_date.year, inv.invoice_date.month, 1)

        for li in inv.line_items:
            category = li.category or "UNKNOWN"
            key: AggKey = (inv_month, inv.customer_id, category)

            revenue = li.line_total or 0.0
            volume = li.catch_weight_lbs or li.quantity or 0.0

            # Resolve COGS from product cost_per_lb
            cost_per_lb = sku_cost_cache.get(li.sku_id)
            if cost_per_lb is None and li.product is not None:
                cost_per_lb = li.product.cost_per_lb or 0.0
                sku_cost_cache[li.sku_id] = cost_per_lb
            if cost_per_lb is None:
                cost_per_lb = 0.0

            cogs = cost_per_lb * volume

            agg[key]["revenue"] += revenue
            agg[key]["cogs"] += cogs
            agg[key]["volume_lbs"] += volume
            agg[key]["num_invoices"].add(inv.invoice_id)

    # Convert aggregates to ORM objects
    summaries: list[MarginSummary] = []

    for (period_date, customer_id, category), metrics in agg.items():
        revenue = round(metrics["revenue"], 2)
        cogs = round(metrics["cogs"], 2)
        gross_margin = round(revenue - cogs, 2)
        gross_margin_pct = round(gross_margin / revenue, 4) if revenue > 0 else 0.0
        volume = round(metrics["volume_lbs"], 2)
        num_inv = len(metrics["num_invoices"])
        avg_price = round(revenue / volume, 2) if volume > 0 else 0.0
        avg_cost = round(cogs / volume, 2) if volume > 0 else 0.0

        summary = MarginSummary(
            summary_id=make_id("MS"),
            period_date=period_date,
            customer_id=customer_id,
            category=category,
            sku_id=None,
            revenue=revenue,
            cogs=cogs,
            gross_margin=gross_margin,
            gross_margin_pct=gross_margin_pct,
            volume_lbs=volume,
            num_invoices=num_inv,
            avg_price_per_lb=avg_price,
            avg_cost_per_lb=avg_cost,
        )
        summaries.append(summary)

    session.add_all(summaries)
    return summaries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_financial_summaries(session, invoices, payments, customers) -> dict:
    """Generate all financial summary tables.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session; generated objects are added but not committed.
    invoices : list[Invoice]
        Previously generated Invoice ORM objects (with line_items loaded).
    payments : list[Payment]
        Previously generated Payment ORM objects.
    customers : list[Customer]
        Previously generated Customer ORM objects.

    Returns
    -------
    dict
        ``{"ar_aging": list[ARaging], "margin_summaries": list[MarginSummary]}``
    """
    ar_records = _generate_ar_aging(session, invoices, payments, customers)
    margin_records = _generate_margin_summaries(session, invoices, payments, customers)

    return {
        "ar_aging": ar_records,
        "margin_summaries": margin_records,
    }
