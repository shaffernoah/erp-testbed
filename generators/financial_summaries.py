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

    Uses a single SQL aggregation query to avoid N+1 ORM lazy-loading.
    """
    from sqlalchemy import text

    rows = session.execute(text("""
        SELECT
            i.customer_id,
            li.category,
            strftime('%Y-%m-01', i.invoice_date) AS period,
            SUM(COALESCE(li.line_total, 0))      AS revenue,
            SUM(COALESCE(p.cost_per_lb, 0)
                * COALESCE(li.catch_weight_lbs, li.quantity, 0)) AS cogs,
            SUM(COALESCE(li.catch_weight_lbs, li.quantity, 0))   AS volume_lbs,
            COUNT(DISTINCT i.invoice_id)          AS num_invoices
        FROM invoice_line_items li
        JOIN invoices i  ON i.invoice_id = li.invoice_id
        LEFT JOIN products p ON p.sku_id = li.sku_id
        GROUP BY i.customer_id, li.category, period
    """)).fetchall()

    summaries: list[MarginSummary] = []
    for row in rows:
        customer_id, category, period_str, revenue, cogs, volume, num_inv = row
        category = category or "UNKNOWN"
        revenue = round(revenue or 0, 2)
        cogs = round(cogs or 0, 2)
        volume = round(volume or 0, 2)
        gross_margin = round(revenue - cogs, 2)
        gross_margin_pct = round(gross_margin / revenue, 4) if revenue > 0 else 0.0
        avg_price = round(revenue / volume, 2) if volume > 0 else 0.0
        avg_cost = round(cogs / volume, 2) if volume > 0 else 0.0
        period_date = date.fromisoformat(period_str)

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
