"""Context builder -- extracts structured data from SQLite for LLM prompts.

Each public method queries the database via SQLAlchemy and returns a plain
``dict`` whose values are lists-of-dicts (table rows), scalars, or nested
dicts.  The caller (typically ``PromptBuilder``) serialises these dicts into
Markdown tables that become part of the LLM context window.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    ARaging,
    Customer,
    Inventory,
    Invoice,
    InvoiceLineItem,
    Lot,
    MarginSummary,
    Payment,
    Pricing,
    Product,
)

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Query facade that turns ORM data into LLM-ready context dicts.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        An active SQLAlchemy session bound to the LaFrieda testbed database.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Customer context
    # ------------------------------------------------------------------

    def get_customer_context(self, customer_id: str) -> dict:
        """Build a rich context dict for a single customer.

        Returns
        -------
        dict
            Keys: ``customer``, ``recent_invoices``, ``payment_history``,
            ``ar_aging``.
        """
        customer = (
            self.session.query(Customer)
            .filter(Customer.customer_id == customer_id)
            .first()
        )
        if customer is None:
            raise ValueError(f"Customer '{customer_id}' not found.")

        customer_data = {
            "customer_id": customer.customer_id,
            "business_name": customer.business_name,
            "customer_type": customer.customer_type,
            "segment": customer.segment,
            "tier": customer.tier,
            "city": customer.city,
            "state": customer.state,
            "borough": customer.borough,
            "credit_limit": customer.credit_limit,
            "credit_terms": customer.credit_terms,
            "credit_rating": customer.credit_rating,
            "account_status": customer.account_status,
            "cari_enrolled": customer.cari_enrolled,
            "cari_reward_tier": customer.cari_reward_tier,
            "first_order_date": str(customer.first_order_date) if customer.first_order_date else None,
            "last_order_date": str(customer.last_order_date) if customer.last_order_date else None,
            "total_lifetime_orders": customer.total_lifetime_orders,
            "total_lifetime_revenue": customer.total_lifetime_revenue,
            "avg_order_value": customer.avg_order_value,
            "order_frequency_days": customer.order_frequency_days,
        }

        # Recent invoices (last 90 days, up to 50).
        cutoff = date.today() - timedelta(days=90)
        invoices = (
            self.session.query(Invoice)
            .filter(
                Invoice.customer_id == customer_id,
                Invoice.invoice_date >= cutoff,
            )
            .order_by(Invoice.invoice_date.desc())
            .limit(50)
            .all()
        )
        recent_invoices = [
            {
                "invoice_id": inv.invoice_id,
                "invoice_date": str(inv.invoice_date),
                "due_date": str(inv.due_date),
                "status": inv.status,
                "total_amount": inv.total_amount,
                "amount_paid": inv.amount_paid,
                "balance_due": inv.balance_due,
                "cari_eligible": inv.cari_eligible,
            }
            for inv in invoices
        ]

        # Payment history (last 90 days).
        payments = (
            self.session.query(Payment)
            .filter(
                Payment.customer_id == customer_id,
                Payment.payment_date >= cutoff,
            )
            .order_by(Payment.payment_date.desc())
            .limit(50)
            .all()
        )
        payment_history = [
            {
                "payment_date": str(p.payment_date),
                "amount": p.amount,
                "payment_method": p.payment_method,
                "is_cari_payment": p.is_cari_payment,
                "days_to_payment": p.days_to_payment,
            }
            for p in payments
        ]

        # Latest AR aging snapshot.
        ar_row = (
            self.session.query(ARaging)
            .filter(ARaging.customer_id == customer_id)
            .order_by(ARaging.snapshot_date.desc())
            .first()
        )
        ar_aging = None
        if ar_row:
            ar_aging = {
                "snapshot_date": str(ar_row.snapshot_date),
                "current_amount": ar_row.current_amount,
                "days_31_60": ar_row.days_31_60,
                "days_61_90": ar_row.days_61_90,
                "days_over_90": ar_row.days_over_90,
                "total_outstanding": ar_row.total_outstanding,
                "weighted_avg_days": ar_row.weighted_avg_days,
            }

        return {
            "customer": customer_data,
            "recent_invoices": recent_invoices,
            "payment_history": payment_history,
            "ar_aging": ar_aging,
        }

    # ------------------------------------------------------------------
    # Product context
    # ------------------------------------------------------------------

    def get_product_context(self, sku_id: str) -> dict:
        """Build context for a single product / SKU.

        Returns
        -------
        dict
            Keys: ``product``, ``demand_history``, ``inventory``, ``lots``.
        """
        product = (
            self.session.query(Product)
            .filter(Product.sku_id == sku_id)
            .first()
        )
        if product is None:
            raise ValueError(f"Product '{sku_id}' not found.")

        product_data = {
            "sku_id": product.sku_id,
            "name": product.name,
            "category": product.category,
            "subcategory": product.subcategory,
            "usda_grade": product.usda_grade,
            "primal_cut": product.primal_cut,
            "list_price_per_lb": product.list_price_per_lb,
            "cost_per_lb": product.cost_per_lb,
            "target_margin_pct": product.target_margin_pct,
            "shelf_life_days": product.shelf_life_days,
            "is_catch_weight": product.is_catch_weight,
            "base_uom": product.base_uom,
            "is_seasonal": product.is_seasonal,
        }

        # Demand history -- daily invoice line-item volume over last 90 days.
        cutoff = date.today() - timedelta(days=90)
        demand_rows = (
            self.session.query(
                Invoice.invoice_date,
                func.sum(InvoiceLineItem.catch_weight_lbs).label("total_lbs"),
                func.count(InvoiceLineItem.line_item_id).label("line_count"),
            )
            .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
            .filter(
                InvoiceLineItem.sku_id == sku_id,
                Invoice.invoice_date >= cutoff,
            )
            .group_by(Invoice.invoice_date)
            .order_by(Invoice.invoice_date)
            .all()
        )
        demand_history = [
            {
                "date": str(row.invoice_date),
                "total_lbs": row.total_lbs,
                "line_count": row.line_count,
            }
            for row in demand_rows
        ]

        # Current inventory snapshot (most recent per location).
        inventory_rows = (
            self.session.query(Inventory)
            .filter(Inventory.sku_id == sku_id)
            .order_by(Inventory.snapshot_date.desc())
            .limit(10)
            .all()
        )
        inventory = [
            {
                "location": inv.location,
                "quantity_on_hand": inv.quantity_on_hand,
                "weight_on_hand_lbs": inv.weight_on_hand_lbs,
                "quantity_available": inv.quantity_available,
                "days_in_inventory": inv.days_in_inventory,
                "days_until_expiry": inv.days_until_expiry,
                "snapshot_date": str(inv.snapshot_date),
            }
            for inv in inventory_rows
        ]

        # Active lots.
        lots = (
            self.session.query(Lot)
            .filter(
                Lot.sku_id == sku_id,
                Lot.status.in_(["AVAILABLE", "RESERVED"]),
            )
            .order_by(Lot.expiration_date)
            .limit(20)
            .all()
        )
        lots_data = [
            {
                "lot_id": lot.lot_id,
                "lot_number": lot.lot_number,
                "current_quantity_lbs": lot.current_quantity_lbs,
                "received_date": str(lot.received_date),
                "expiration_date": str(lot.expiration_date),
                "status": lot.status,
                "storage_location": lot.storage_location,
            }
            for lot in lots
        ]

        return {
            "product": product_data,
            "demand_history": demand_history,
            "inventory": inventory,
            "lots": lots_data,
        }

    # ------------------------------------------------------------------
    # Demand context (category-level)
    # ------------------------------------------------------------------

    def get_demand_context(
        self,
        category: str,
        lookback_days: int = 90,
    ) -> dict:
        """Aggregate daily order volumes for a product category.

        Returns
        -------
        dict
            Keys: ``category``, ``lookback_days``, ``daily_volumes``,
            ``top_skus``.
        """
        cutoff = date.today() - timedelta(days=lookback_days)

        # Daily aggregated volume.
        daily_rows = (
            self.session.query(
                Invoice.invoice_date,
                func.sum(InvoiceLineItem.catch_weight_lbs).label("total_lbs"),
                func.count(func.distinct(Invoice.invoice_id)).label("order_count"),
                func.sum(InvoiceLineItem.line_total).label("total_revenue"),
            )
            .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
            .filter(
                InvoiceLineItem.category == category,
                Invoice.invoice_date >= cutoff,
            )
            .group_by(Invoice.invoice_date)
            .order_by(Invoice.invoice_date)
            .all()
        )
        daily_volumes = [
            {
                "date": str(row.invoice_date),
                "total_lbs": row.total_lbs,
                "order_count": row.order_count,
                "total_revenue": row.total_revenue,
            }
            for row in daily_rows
        ]

        # Top SKUs by volume in the category.
        top_sku_rows = (
            self.session.query(
                InvoiceLineItem.sku_id,
                Product.name,
                func.sum(InvoiceLineItem.catch_weight_lbs).label("total_lbs"),
                func.sum(InvoiceLineItem.line_total).label("total_revenue"),
            )
            .join(Product, InvoiceLineItem.sku_id == Product.sku_id)
            .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
            .filter(
                InvoiceLineItem.category == category,
                Invoice.invoice_date >= cutoff,
            )
            .group_by(InvoiceLineItem.sku_id, Product.name)
            .order_by(func.sum(InvoiceLineItem.catch_weight_lbs).desc())
            .limit(15)
            .all()
        )
        top_skus = [
            {
                "sku_id": row.sku_id,
                "name": row.name,
                "total_lbs": row.total_lbs,
                "total_revenue": row.total_revenue,
            }
            for row in top_sku_rows
        ]

        return {
            "category": category,
            "lookback_days": lookback_days,
            "daily_volumes": daily_volumes,
            "top_skus": top_skus,
        }

    # ------------------------------------------------------------------
    # Financial overview
    # ------------------------------------------------------------------

    def get_financial_overview(self) -> dict:
        """High-level financial snapshot across all customers.

        Returns
        -------
        dict
            Keys: ``ar_aging_totals``, ``margin_by_category``, ``dso``.
        """
        # AR aging totals from the most recent snapshot date.
        latest_snapshot = (
            self.session.query(func.max(ARaging.snapshot_date)).scalar()
        )

        ar_totals: dict = {
            "snapshot_date": None,
            "current": 0,
            "days_31_60": 0,
            "days_61_90": 0,
            "over_90": 0,
            "total_outstanding": 0,
        }
        if latest_snapshot:
            agg = (
                self.session.query(
                    func.sum(ARaging.current_amount).label("current"),
                    func.sum(ARaging.days_31_60).label("d31_60"),
                    func.sum(ARaging.days_61_90).label("d61_90"),
                    func.sum(ARaging.days_over_90).label("d90"),
                    func.sum(ARaging.total_outstanding).label("total"),
                )
                .filter(ARaging.snapshot_date == latest_snapshot)
                .first()
            )
            ar_totals = {
                "snapshot_date": str(latest_snapshot),
                "current": agg.current or 0,
                "days_31_60": agg.d31_60 or 0,
                "days_61_90": agg.d61_90 or 0,
                "over_90": agg.d90 or 0,
                "total_outstanding": agg.total or 0,
            }

        # Margin by category (most recent period).
        latest_margin_date = (
            self.session.query(func.max(MarginSummary.period_date)).scalar()
        )
        margin_rows = []
        if latest_margin_date:
            margin_rows_raw = (
                self.session.query(
                    MarginSummary.category,
                    func.sum(MarginSummary.revenue).label("revenue"),
                    func.sum(MarginSummary.cogs).label("cogs"),
                    func.sum(MarginSummary.gross_margin).label("gross_margin"),
                    func.sum(MarginSummary.volume_lbs).label("volume_lbs"),
                )
                .filter(
                    MarginSummary.period_date == latest_margin_date,
                    MarginSummary.category.isnot(None),
                )
                .group_by(MarginSummary.category)
                .all()
            )
            margin_rows = [
                {
                    "category": row.category,
                    "revenue": row.revenue,
                    "cogs": row.cogs,
                    "gross_margin": row.gross_margin,
                    "gross_margin_pct": (
                        round(row.gross_margin / row.revenue * 100, 2)
                        if row.revenue
                        else 0
                    ),
                    "volume_lbs": row.volume_lbs,
                }
                for row in margin_rows_raw
            ]

        # Days Sales Outstanding (DSO) -- simple calculation.
        last_30 = date.today() - timedelta(days=30)
        rev_30 = (
            self.session.query(func.sum(Invoice.total_amount))
            .filter(Invoice.invoice_date >= last_30)
            .scalar()
        ) or 0
        total_ar = ar_totals["total_outstanding"]
        dso = round(total_ar / (rev_30 / 30), 1) if rev_30 > 0 else None

        return {
            "ar_aging_totals": ar_totals,
            "margin_by_category": margin_rows,
            "dso": dso,
        }

    # ------------------------------------------------------------------
    # Inventory / spoilage risk
    # ------------------------------------------------------------------

    def get_inventory_risk(self) -> dict:
        """Identify lots approaching expiry alongside demand velocity.

        Returns
        -------
        dict
            Keys: ``at_risk_lots``, ``demand_velocity``.
        """
        today = date.today()
        risk_horizon = today + timedelta(days=14)

        # Lots expiring within 14 days that still have quantity.
        lots = (
            self.session.query(Lot)
            .join(Product, Lot.sku_id == Product.sku_id)
            .filter(
                Lot.status.in_(["AVAILABLE", "RESERVED"]),
                Lot.expiration_date <= risk_horizon,
                Lot.current_quantity_lbs > 0,
            )
            .order_by(Lot.expiration_date)
            .limit(50)
            .all()
        )

        at_risk: list[dict] = []
        sku_ids_seen: set[str] = set()
        for lot in lots:
            days_left = (lot.expiration_date - today).days
            at_risk.append(
                {
                    "lot_id": lot.lot_id,
                    "lot_number": lot.lot_number,
                    "sku_id": lot.sku_id,
                    "product_name": lot.product.name if lot.product else None,
                    "category": lot.product.category if lot.product else None,
                    "current_quantity_lbs": lot.current_quantity_lbs,
                    "expiration_date": str(lot.expiration_date),
                    "days_until_expiry": days_left,
                    "storage_location": lot.storage_location,
                }
            )
            sku_ids_seen.add(lot.sku_id)

        # Demand velocity for the at-risk SKUs (avg daily lbs last 30 days).
        cutoff_30 = today - timedelta(days=30)
        velocity_rows = (
            self.session.query(
                InvoiceLineItem.sku_id,
                func.sum(InvoiceLineItem.catch_weight_lbs).label("total_lbs"),
                func.count(func.distinct(Invoice.invoice_date)).label("active_days"),
            )
            .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
            .filter(
                InvoiceLineItem.sku_id.in_(list(sku_ids_seen)),
                Invoice.invoice_date >= cutoff_30,
            )
            .group_by(InvoiceLineItem.sku_id)
            .all()
        )
        demand_velocity = {
            row.sku_id: {
                "total_lbs_30d": row.total_lbs,
                "active_days": row.active_days,
                "avg_daily_lbs": round(row.total_lbs / 30, 2) if row.total_lbs else 0,
            }
            for row in velocity_rows
        }

        return {
            "at_risk_lots": at_risk,
            "demand_velocity": demand_velocity,
        }

    # ------------------------------------------------------------------
    # Pricing context
    # ------------------------------------------------------------------

    def get_pricing_context(
        self,
        sku_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict:
        """Pricing records for benchmarking across customers.

        Returns
        -------
        dict
            Keys: ``pricing_records``, ``invoice_prices``.
        """
        today = date.today()

        # Active pricing records.
        q = self.session.query(Pricing).filter(Pricing.is_active.is_(True))
        if sku_id:
            q = q.filter(Pricing.sku_id == sku_id)
        if category:
            q = q.join(Product, Pricing.sku_id == Product.sku_id).filter(
                Product.category == category
            )
        pricing_records = [
            {
                "sku_id": p.sku_id,
                "customer_id": p.customer_id,
                "price_type": p.price_type,
                "price_per_lb": p.price_per_lb,
                "effective_date": str(p.effective_date),
                "min_quantity_lbs": p.min_quantity_lbs,
            }
            for p in q.limit(100).all()
        ]

        # Actual invoiced prices over last 60 days.
        cutoff = today - timedelta(days=60)
        inv_q = (
            self.session.query(
                InvoiceLineItem.sku_id,
                Invoice.customer_id,
                func.avg(InvoiceLineItem.price_per_unit).label("avg_price"),
                func.sum(InvoiceLineItem.catch_weight_lbs).label("total_lbs"),
            )
            .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
            .filter(Invoice.invoice_date >= cutoff)
        )
        if sku_id:
            inv_q = inv_q.filter(InvoiceLineItem.sku_id == sku_id)
        if category:
            inv_q = inv_q.filter(InvoiceLineItem.category == category)
        inv_q = (
            inv_q.group_by(InvoiceLineItem.sku_id, Invoice.customer_id)
            .order_by(func.sum(InvoiceLineItem.catch_weight_lbs).desc())
            .limit(100)
        )
        invoice_prices = [
            {
                "sku_id": row.sku_id,
                "customer_id": row.customer_id,
                "avg_price_per_lb": round(row.avg_price, 4) if row.avg_price else None,
                "total_lbs": row.total_lbs,
            }
            for row in inv_q.all()
        ]

        return {
            "pricing_records": pricing_records,
            "invoice_prices": invoice_prices,
        }

    # ------------------------------------------------------------------
    # Churn context
    # ------------------------------------------------------------------

    def get_churn_context(self, customer_id: str) -> dict:
        """Gather signals relevant to churn prediction for a customer.

        Returns
        -------
        dict
            Keys: ``customer``, ``order_trend``, ``payment_trend``,
            ``ar_aging``, ``category_mix``.
        """
        customer_ctx = self.get_customer_context(customer_id)

        # Order trend -- monthly order counts and revenue over last 6 months.
        cutoff = date.today() - timedelta(days=180)
        monthly = (
            self.session.query(
                func.strftime("%Y-%m", Invoice.invoice_date).label("month"),
                func.count(Invoice.invoice_id).label("order_count"),
                func.sum(Invoice.total_amount).label("revenue"),
            )
            .filter(
                Invoice.customer_id == customer_id,
                Invoice.invoice_date >= cutoff,
            )
            .group_by(func.strftime("%Y-%m", Invoice.invoice_date))
            .order_by(func.strftime("%Y-%m", Invoice.invoice_date))
            .all()
        )
        order_trend = [
            {
                "month": row.month,
                "order_count": row.order_count,
                "revenue": row.revenue,
            }
            for row in monthly
        ]

        # Payment trend -- average days_to_payment per month.
        pay_monthly = (
            self.session.query(
                func.strftime("%Y-%m", Payment.payment_date).label("month"),
                func.avg(Payment.days_to_payment).label("avg_days"),
                func.count(Payment.payment_id).label("payment_count"),
            )
            .filter(
                Payment.customer_id == customer_id,
                Payment.payment_date >= cutoff,
            )
            .group_by(func.strftime("%Y-%m", Payment.payment_date))
            .order_by(func.strftime("%Y-%m", Payment.payment_date))
            .all()
        )
        payment_trend = [
            {
                "month": row.month,
                "avg_days_to_payment": round(row.avg_days, 1) if row.avg_days else None,
                "payment_count": row.payment_count,
            }
            for row in pay_monthly
        ]

        # Category mix (last 90 days).
        cutoff_90 = date.today() - timedelta(days=90)
        cat_mix = (
            self.session.query(
                InvoiceLineItem.category,
                func.sum(InvoiceLineItem.line_total).label("total"),
                func.sum(InvoiceLineItem.catch_weight_lbs).label("lbs"),
            )
            .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
            .filter(
                Invoice.customer_id == customer_id,
                Invoice.invoice_date >= cutoff_90,
            )
            .group_by(InvoiceLineItem.category)
            .all()
        )
        category_mix = [
            {
                "category": row.category,
                "total_revenue": row.total,
                "total_lbs": row.lbs,
            }
            for row in cat_mix
        ]

        return {
            "customer": customer_ctx["customer"],
            "order_trend": order_trend,
            "payment_trend": payment_trend,
            "ar_aging": customer_ctx["ar_aging"],
            "category_mix": category_mix,
        }
