"""Pricing benchmark analyzer -- compares pricing across customers for the
same products to identify inconsistencies and optimisation opportunities.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from analysis.context_builder import ContextBuilder
from analysis.llm_client import LLMClient
from analysis.prompt_builder import PromptBuilder
from config.settings import ANALYSIS_DEFAULT_TEMPERATURE

logger = logging.getLogger(__name__)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "object",
            "properties": {
                "sku_id": {"type": ["string", "null"]},
                "category": {"type": ["string", "null"]},
            },
        },
        "summary_stats": {
            "type": "object",
            "properties": {
                "num_skus_analysed": {"type": "integer"},
                "num_customers_analysed": {"type": "integer"},
                "avg_price_per_lb": {"type": "number"},
                "median_price_per_lb": {"type": "number"},
                "price_range_low": {"type": "number"},
                "price_range_high": {"type": "number"},
                "coefficient_of_variation_pct": {"type": "number"},
            },
        },
        "outliers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sku_id": {"type": "string"},
                    "customer_id": {"type": "string"},
                    "avg_price_per_lb": {"type": "number"},
                    "deviation_from_median_pct": {"type": "number"},
                    "direction": {
                        "type": "string",
                        "enum": ["above", "below"],
                    },
                    "volume_lbs": {"type": "number"},
                    "risk": {"type": "string"},
                },
                "required": [
                    "sku_id",
                    "customer_id",
                    "avg_price_per_lb",
                    "deviation_from_median_pct",
                    "direction",
                ],
            },
            "description": "Customers paying significantly above or below median.",
        },
        "pricing_tiers_observed": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tier_label": {"type": "string"},
                    "price_range": {"type": "string"},
                    "customer_count": {"type": "integer"},
                    "avg_volume_lbs": {"type": "number"},
                },
                "required": ["tier_label", "price_range", "customer_count"],
            },
            "description": "Natural pricing tiers identified in the data.",
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
                    "estimated_revenue_impact": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["action", "priority", "rationale"],
            },
        },
    },
    "required": ["scope", "summary_stats", "outliers", "recommendations"],
}


class PricingBenchmarkAnalyzer:
    """Compare pricing across customers and identify optimisation opportunities.

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

    def analyze(
        self,
        sku_id: Optional[str] = None,
        category: Optional[str] = None,
        question: Optional[str] = None,
    ) -> dict:
        """Run pricing benchmark analysis.

        Parameters
        ----------
        sku_id : str | None
            Benchmark a specific SKU across customers.
        category : str | None
            Benchmark all SKUs in a category.
        question : str | None
            Override the default analysis question.

        Returns
        -------
        dict
            Structured pricing analysis matching ``OUTPUT_SCHEMA``.
        """
        scope_label = sku_id or category or "all products"
        logger.info("Running pricing benchmark for %s", scope_label)

        data = self.context.get_pricing_context(sku_id=sku_id, category=category)

        default_question = (
            f"Analyse the pricing data for {scope_label}.  Compare prices "
            f"charged to different customers for the same products.  "
            f"Identify:\n"
            f"1. Customers paying significantly above or below the median "
            f"price (flag those beyond +/- 10%).\n"
            f"2. Any natural pricing tiers that emerge from the data.\n"
            f"3. Inconsistencies between contract prices and actual invoiced "
            f"prices.\n"
            f"4. Opportunities to adjust pricing -- either to capture margin "
            f"from underpriced accounts or to stay competitive with "
            f"overpriced ones at risk of switching.\n\n"
            f"Factor in customer tier and volume when assessing whether a "
            f"price deviation is justified."
        )

        messages = self.prompts.build_analysis_prompt(
            analyzer_type="pricing_benchmark",
            data_context=data,
            question=question or default_question,
            output_schema=OUTPUT_SCHEMA,
        )

        result = self.llm.complete_json(messages, temperature=ANALYSIS_DEFAULT_TEMPERATURE)
        logger.info("Pricing benchmark complete for %s", scope_label)
        return result
