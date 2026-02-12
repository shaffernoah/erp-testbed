"""Margin analyzer -- examines gross margin performance across categories,
customers, and SKUs with actionable improvement recommendations.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from analysis.context_builder import ContextBuilder
from analysis.llm_client import LLMClient
from analysis.prompt_builder import PromptBuilder
from config.settings import ANALYSIS_DEFAULT_TEMPERATURE
from database.models import Invoice, InvoiceLineItem, MarginSummary, Product

logger = logging.getLogger(__name__)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_margin_pct": {"type": "number"},
        "period": {"type": "string", "description": "Analysis period description"},
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "insight": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "warning", "info"],
                    },
                    "affected_area": {"type": "string"},
                    "estimated_impact_dollars": {"type": "number"},
                },
                "required": ["insight", "severity", "affected_area"],
            },
        },
        "category_breakdown": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "margin_pct": {"type": "number"},
                    "revenue": {"type": "number"},
                    "trend": {
                        "type": "string",
                        "enum": ["improving", "stable", "declining"],
                    },
                },
                "required": ["category", "margin_pct", "revenue"],
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "expected_margin_lift_pct": {"type": "number"},
                },
                "required": ["action", "priority"],
            },
        },
    },
    "required": ["overall_margin_pct", "period", "insights", "recommendations"],
}


class MarginAnalyzer:
    """Analyse gross-margin performance and identify improvement areas.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session.
    llm_client : LLMClient
        Configured LLM client instance.
    """

    def __init__(self, session: Session, llm_client: LLMClient):
        self.session = session
        self.llm = llm_client
        self.context = ContextBuilder(session)
        self.prompts = PromptBuilder()

    # ------------------------------------------------------------------
    # Internal context enrichment
    # ------------------------------------------------------------------

    def _build_margin_context(
        self,
        customer_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict:
        """Assemble margin-specific context beyond the financial overview."""
        overview = self.context.get_financial_overview()

        # Per-SKU margin detail for the requested scope (last 60 days).
        cutoff = date.today() - timedelta(days=60)
        q = (
            self.session.query(
                InvoiceLineItem.sku_id,
                Product.name.label("product_name"),
                Product.category,
                func.sum(InvoiceLineItem.line_total).label("revenue"),
                func.sum(InvoiceLineItem.catch_weight_lbs).label("volume_lbs"),
                func.avg(InvoiceLineItem.price_per_unit).label("avg_price"),
            )
            .join(Product, InvoiceLineItem.sku_id == Product.sku_id)
            .join(Invoice, InvoiceLineItem.invoice_id == Invoice.invoice_id)
            .filter(Invoice.invoice_date >= cutoff)
        )
        if customer_id:
            q = q.filter(Invoice.customer_id == customer_id)
        if category:
            q = q.filter(Product.category == category)

        sku_rows = (
            q.group_by(InvoiceLineItem.sku_id, Product.name, Product.category)
            .order_by(func.sum(InvoiceLineItem.line_total).desc())
            .limit(30)
            .all()
        )
        sku_detail = [
            {
                "sku_id": r.sku_id,
                "product_name": r.product_name,
                "category": r.category,
                "revenue": r.revenue,
                "volume_lbs": r.volume_lbs,
                "avg_price_per_lb": round(r.avg_price, 4) if r.avg_price else None,
            }
            for r in sku_rows
        ]

        ctx = {
            "scope_customer_id": customer_id,
            "scope_category": category,
            **overview,
            "sku_detail": sku_detail,
        }

        # If a specific customer was requested, add their context.
        if customer_id:
            try:
                cust_ctx = self.context.get_customer_context(customer_id)
                ctx["customer"] = cust_ctx["customer"]
            except ValueError:
                pass

        return ctx

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        customer_id: Optional[str] = None,
        category: Optional[str] = None,
        question: Optional[str] = None,
    ) -> dict:
        """Run margin analysis.

        Parameters
        ----------
        customer_id : str | None
            Scope analysis to a single customer.
        category : str | None
            Scope analysis to a product category.
        question : str | None
            Override the default analysis question.

        Returns
        -------
        dict
            Structured margin insights matching ``OUTPUT_SCHEMA``.
        """
        scope_parts = []
        if customer_id:
            scope_parts.append(f"customer {customer_id}")
        if category:
            scope_parts.append(f"category {category}")
        scope_label = " and ".join(scope_parts) if scope_parts else "all business"
        logger.info("Running margin analysis for %s", scope_label)

        data = self._build_margin_context(customer_id=customer_id, category=category)

        default_question = (
            f"Analyse the gross-margin performance for {scope_label}.  "
            f"Identify the top margin headwinds and tailwinds, flag any "
            f"underperforming SKUs or categories, and recommend concrete "
            f"actions to improve blended margin.  Consider pricing, mix, "
            f"and volume effects."
        )

        messages = self.prompts.build_analysis_prompt(
            analyzer_type="margin_analysis",
            data_context=data,
            question=question or default_question,
            output_schema=OUTPUT_SCHEMA,
        )

        result = self.llm.complete_json(messages, temperature=ANALYSIS_DEFAULT_TEMPERATURE)
        logger.info("Margin analysis complete for %s", scope_label)
        return result
