"""Tool: check_alerts -- real-time operational alerting scanner.

Scans the ERP database for conditions that warrant attention:
  - Lots expiring within 7 days
  - Temperature anomalies in quality records
  - Payment anomalies (large overdue balances, sudden spikes)
  - Large order deviations (orders significantly above/below normal)

Returns a list of alerts with severity: INFO / WARNING / CRITICAL.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from database.models import (
    ARaging, Customer, Inventory, Invoice, InvoiceLineItem,
    Lot, Product, QualityRecord,
)
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def check_alerts(session: Session) -> dict:
    """Scan the ERP for actionable alerts.

    Returns
    -------
    dict with ``alerts`` list.  Each alert has:
        alert_type, severity, title, detail, entity_id, recommended_action
    """
    today = date.today()
    alerts: List[dict] = []

    # ------------------------------------------------------------------
    # 1. Expiring lots (within 7 days)
    # ------------------------------------------------------------------
    expiry_cutoff = today + timedelta(days=7)
    expiring_lots = (
        session.query(Lot)
        .filter(
            Lot.status.in_(["AVAILABLE", "RESERVED"]),
            Lot.expiration_date <= expiry_cutoff,
            Lot.expiration_date >= today,
            Lot.current_quantity_lbs > 0,
        )
        .order_by(Lot.expiration_date.asc())
        .all()
    )

    for lot in expiring_lots:
        days_left = (lot.expiration_date - today).days
        product = session.query(Product).get(lot.sku_id)
        product_name = product.name if product else lot.sku_id

        if days_left <= 2:
            severity = "CRITICAL"
        elif days_left <= 4:
            severity = "WARNING"
        else:
            severity = "INFO"

        alerts.append({
            "alert_type": "EXPIRING_LOT",
            "severity": severity,
            "title": f"Lot {lot.lot_number} expires in {days_left} day(s)",
            "detail": (
                f"{product_name} | {lot.current_quantity_lbs:.0f} lbs remaining | "
                f"Location: {lot.storage_location} | Expires: {lot.expiration_date}"
            ),
            "entity_id": lot.lot_id,
            "recommended_action": (
                "Prioritize for next delivery or mark for employee sale / donation."
                if days_left <= 2
                else "Schedule for upcoming orders. Consider promotional pricing."
            ),
        })

    # ------------------------------------------------------------------
    # 2. Temperature anomalies
    # ------------------------------------------------------------------
    recent_temp_cutoff = today - timedelta(days=3)
    temp_anomalies = (
        session.query(QualityRecord)
        .filter(
            QualityRecord.record_type == "TEMP_LOG",
            QualityRecord.temp_in_range == False,
            QualityRecord.check_datetime >= recent_temp_cutoff,
        )
        .order_by(QualityRecord.check_datetime.desc())
        .limit(20)
        .all()
    )

    for rec in temp_anomalies:
        temp_f = rec.temperature_f or 0
        # Freezer out of range is critical; cooler is warning
        if temp_f > 45 or temp_f < -15:
            severity = "CRITICAL"
        else:
            severity = "WARNING"

        alerts.append({
            "alert_type": "TEMPERATURE_ANOMALY",
            "severity": severity,
            "title": f"Temperature out of range at {rec.location}",
            "detail": (
                f"Recorded {temp_f:.1f}\u00b0F at {rec.check_datetime} | "
                f"Lot: {rec.lot_id or 'N/A'} | Status: {rec.status}"
            ),
            "entity_id": rec.record_id,
            "recommended_action": (
                "IMMEDIATE: Inspect affected product. Check refrigeration unit. "
                "Place lot on HOLD pending evaluation."
                if severity == "CRITICAL"
                else "Investigate and recalibrate sensor. Monitor next 24 hours."
            ),
        })

    # ------------------------------------------------------------------
    # 3. Payment anomalies (overdue > 60 days with large balances)
    # ------------------------------------------------------------------
    ar_records = (
        session.query(ARaging)
        .filter(
            or_(
                ARaging.days_61_90 > 5000,
                ARaging.days_over_90 > 0,
            )
        )
        .order_by(ARaging.total_outstanding.desc())
        .limit(15)
        .all()
    )

    for ar in ar_records:
        customer = session.query(Customer).get(ar.customer_id)
        biz_name = customer.business_name if customer else ar.customer_id
        over_90 = float(ar.days_over_90 or 0)
        d61_90 = float(ar.days_61_90 or 0)
        total = float(ar.total_outstanding or 0)

        if over_90 > 10000:
            severity = "CRITICAL"
        elif over_90 > 0 or d61_90 > 10000:
            severity = "WARNING"
        else:
            severity = "INFO"

        alerts.append({
            "alert_type": "PAYMENT_ANOMALY",
            "severity": severity,
            "title": f"Overdue balance for {biz_name}",
            "detail": (
                f"Total outstanding: ${total:,.2f} | "
                f"61-90 days: ${d61_90:,.2f} | >90 days: ${over_90:,.2f} | "
                f"Customer tier: {customer.tier if customer else 'N/A'}"
            ),
            "entity_id": ar.customer_id,
            "recommended_action": (
                "Escalate to collections. Consider credit hold."
                if severity == "CRITICAL"
                else "Contact customer AP department. Review credit terms."
            ),
        })

    # ------------------------------------------------------------------
    # 4. Large order deviations
    # ------------------------------------------------------------------
    # Find recent invoices where total deviates >3x from customer average
    recent_invoices = (
        session.query(Invoice)
        .filter(
            Invoice.invoice_date >= today - timedelta(days=7),
            Invoice.status.in_(["OPEN", "PARTIAL"]),
        )
        .all()
    )

    for inv in recent_invoices:
        customer = session.query(Customer).get(inv.customer_id)
        if not customer or not customer.avg_order_value:
            continue
        avg = float(customer.avg_order_value)
        total = float(inv.total_amount or 0)
        if avg <= 0:
            continue

        ratio = total / avg
        if ratio > 3.0:
            alerts.append({
                "alert_type": "ORDER_DEVIATION",
                "severity": "WARNING",
                "title": f"Unusually large order from {customer.business_name}",
                "detail": (
                    f"Invoice {inv.invoice_number}: ${total:,.2f} "
                    f"({ratio:.1f}x their avg of ${avg:,.2f})"
                ),
                "entity_id": inv.invoice_id,
                "recommended_action": "Verify order accuracy. Confirm with customer before shipment.",
            })
        elif ratio < 0.2 and total > 0:
            alerts.append({
                "alert_type": "ORDER_DEVIATION",
                "severity": "INFO",
                "title": f"Unusually small order from {customer.business_name}",
                "detail": (
                    f"Invoice {inv.invoice_number}: ${total:,.2f} "
                    f"({ratio:.1f}x their avg of ${avg:,.2f})"
                ),
                "entity_id": inv.invoice_id,
                "recommended_action": "Check if customer is scaling down. Proactive outreach recommended.",
            })

    # ------------------------------------------------------------------
    # Sort by severity
    # ------------------------------------------------------------------
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 3))

    return {
        "status": "success",
        "scan_date": str(today),
        "alert_count": len(alerts),
        "critical_count": sum(1 for a in alerts if a["severity"] == "CRITICAL"),
        "warning_count": sum(1 for a in alerts if a["severity"] == "WARNING"),
        "info_count": sum(1 for a in alerts if a["severity"] == "INFO"),
        "alerts": alerts,
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="check_alerts",
    description=(
        "Scan the ERP database for operational alerts: lots expiring within "
        "7 days, temperature anomalies, payment anomalies (overdue balances), "
        "and large order deviations. Returns alerts with severity levels "
        "(CRITICAL / WARNING / INFO) and recommended actions."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    function=check_alerts,
    requires_confirmation=False,
    tags=["ops", "sales", "alerts"],
)
